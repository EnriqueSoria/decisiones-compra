import json
import re
import sys
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from http.client import HTTPException
from html.parser import HTMLParser
from time import monotonic
from typing import NamedTuple
from urllib.error import HTTPError
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen


PREVIEW_TAGS = ("og:image:secure_url", "og:image", "og:image:url", "twitter:image", "twitter:image:src")
PRICE_TAG_PAIRS = (
    ("product:price:amount", "product:price:currency"),
    ("og:price:amount", "og:price:currency"),
)
PRICE_TAGS = {tag for pair in PRICE_TAG_PAIRS for tag in pair}
retry_at = {}


class PageMetadata(NamedTuple):
    title: str
    icons: list[str]
    image: str = ""
    product_name: str = ""
    price: str = ""


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_title = False
        self.title_parts = []
        self.social_title = ""
        self.base_url = ""
        self.icons = []
        self.images = []
        self.done = False
        self.price_meta = {}
        self.structured_data = []
        self.json_parts = None

    def handle_starttag(self, tag, attrs):
        attrs = {key: value or "" for key, value in attrs}
        if tag == "script" and attrs.get("type", "").strip().lower() == "application/ld+json":
            self.json_parts = []
        if self.done:
            return
        if tag == "title":
            self.in_title = True
        elif tag == "body":
            self.done = True
        elif tag == "base" and not self.base_url:
            self.base_url = attrs.get("href", "").strip()
        elif tag == "meta":
            key = (attrs.get("property") or attrs.get("name", "")).lower()
            content = attrs.get("content", "").strip()
            if key == "og:title":
                self.social_title = content
            elif key in PREVIEW_TAGS and content:
                self.images.append((PREVIEW_TAGS.index(key), content))
            elif key in PRICE_TAGS and content:
                self.price_meta.setdefault(key, content)
        elif tag == "link":
            relations = attrs.get("rel", "").lower().split()
            href = attrs.get("href", "").strip()
            if href and "icon" in relations:
                self.icons.append((0, href))
            elif href and any(rel.startswith("apple-touch-icon") for rel in relations):
                self.icons.append((1, href))

    def handle_endtag(self, tag):
        if tag == "script" and self.json_parts is not None:
            try:
                self.structured_data.append(json.loads("".join(self.json_parts), parse_float=str))
            except (ValueError, RecursionError):
                pass
            self.json_parts = None
        elif tag == "title":
            self.in_title = False
        elif tag == "head":
            self.done = True

    def handle_data(self, data):
        if self.json_parts is not None:
            self.json_parts.append(data)
        elif self.in_title and not self.done:
            self.title_parts.append(data)


def http_url(base, link):
    try:
        url = urljoin(base, link)
        parts = urlsplit(url)
        if parts.scheme in ("http", "https") and parts.hostname and parts.username is None:
            return url
    except ValueError:
        pass
    return ""


def product_nodes(documents):
    pending = list(reversed(documents))
    while pending:
        node = pending.pop()
        if isinstance(node, list):
            pending.extend(reversed(node))
        elif isinstance(node, dict):
            types = node.get("@type", [])
            if isinstance(types, str):
                types = [types]
            if isinstance(types, list) and any(
                value in ("Product", "https://schema.org/Product", "http://schema.org/Product")
                for value in types
            ):
                yield node
            if "@graph" in node:
                pending.append(node["@graph"])


def format_price(amount, currency):
    amount = str(amount).strip()
    currency = str(currency).strip().upper()
    if not re.fullmatch(r"[0-9]+(?:[.,][0-9]+)?", amount) or not re.fullmatch(r"[A-Z]{3}", currency):
        return ""
    return f"{amount.replace('.', ',')} {'€' if currency == 'EUR' else currency}"


def product_price(product):
    offers = product.get("offers", [])
    if isinstance(offers, dict):
        offers = [offers]
    if not isinstance(offers, list):
        return ""

    prices = set()
    for offer in offers:
        if not isinstance(offer, dict):
            continue
        price = format_price(offer.get("price"), offer.get("priceCurrency"))
        if price:
            prices.add(price)
            continue
        specs = offer.get("priceSpecification", [])
        if isinstance(specs, dict):
            specs = [specs]
        if isinstance(specs, list):
            for spec in specs:
                if not isinstance(spec, dict):
                    continue
                price_type = str(spec.get("priceType", "")).rsplit("/", 1)[-1]
                if price_type in ("StrikethroughPrice", "ListPrice", "MSRP"):
                    continue
                price = format_price(spec.get("price"), spec.get("priceCurrency") or offer.get("priceCurrency"))
                if price:
                    prices.add(price)
    return prices.pop() if len(prices) == 1 else ""


def retry_delay(header):
    try:
        return max(1, int(header))
    except (ValueError, TypeError):
        try:
            deadline = parsedate_to_datetime(header)
            return max(1, (deadline - datetime.now(timezone.utc)).total_seconds())
        except (ValueError, TypeError, OverflowError):
            return 60


def image_extension(data):
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "gif"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "webp"
    if data.startswith(b"\0\0\1\0"):
        return "ico"
    if data[4:12] in (b"ftypavif", b"ftypavis"):
        return "avif"
    if data.startswith(b"BM"):
        return "bmp"
    return ""


def read_image(url):
    host = urlsplit(url).hostname
    if retry_at.get(host, 0) > monotonic():
        return b"", ""
    request = Request(url, headers={"User-Agent": "CuadernoDeCompras/1.0", "Accept": "image/*"})
    try:
        with urlopen(request, timeout=8) as response:
            limit = 12 * 1024 * 1024
            data = response.read(limit + 1)
            extension = image_extension(data)
            if extension and len(data) <= limit:
                return data, extension
    except HTTPError as error:
        if error.code == 429:
            retry_at[host] = monotonic() + retry_delay(error.headers.get("Retry-After"))
        error.close()
    except (HTTPException, OSError, ValueError):
        pass
    return b"", ""


def read_metadata(url):
    host = urlsplit(url).hostname
    if retry_at.get(host, 0) > monotonic():
        return PageMetadata("", [])
    try:
        request = Request(url, headers={
            "User-Agent": "CuadernoDeCompras/1.0",
            "Accept": "text/html, application/xhtml+xml",
        })
        with urlopen(request, timeout=8) as response:
            final_url = response.geturl()
            fallback_icon = urljoin(final_url, "/favicon.ico")
            if response.headers.get_content_type() not in ("text/html", "application/xhtml+xml"):
                return PageMetadata("", [fallback_icon])
            encoding = response.headers.get_content_charset() or "utf-8-sig"
            head = PageParser()
            head.feed(response.read(4 * 1024 * 1024).decode(encoding, errors="replace"))
    except HTTPError as error:
        if error.code == 429:
            retry_at[host] = monotonic() + retry_delay(error.headers.get("Retry-After"))
        print(f"Metadatos de {urlsplit(error.url).hostname}: HTTP {error.code}.", file=sys.stderr)
        error.close()
        return PageMetadata("", [])
    except (HTTPException, OSError, ValueError, LookupError):
        return PageMetadata("", [])

    title = " ".join((head.social_title or "".join(head.title_parts)).split())
    base = http_url(final_url, head.base_url) or final_url
    icons = [
        icon for _, href in sorted(head.icons, key=lambda entry: entry[0])
        if (icon := http_url(base, href))
    ]
    image = next((
        image for _, href in sorted(head.images, key=lambda entry: entry[0])
        if (image := http_url(base, href))
    ), "")
    product = next(product_nodes(head.structured_data), {})
    if not image:
        images = product.get("image", [])
        if not isinstance(images, list):
            images = [images]
        for candidate in images:
            if isinstance(candidate, dict):
                candidate = candidate.get("url") or candidate.get("contentUrl")
            if isinstance(candidate, str) and candidate and (image := http_url(base, candidate)):
                break
    name = product.get("name")
    product_name = " ".join(name.split()) if isinstance(name, str) else ""
    price = product_price(product) or next((
        price for amount_tag, currency_tag in PRICE_TAG_PAIRS
        if (price := format_price(head.price_meta.get(amount_tag), head.price_meta.get(currency_tag)))
    ), "")
    return PageMetadata(title, [*icons, fallback_icon], image, product_name, price)
