from pathlib import Path
from urllib.parse import quote, urljoin, urlsplit
import argparse
import re
import shutil
import tomllib

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from local_cache import LocalCache, by_store
from source_metadata import http_url

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"
STATES = ("Explorando", "Comparando", "Decidido", "Comprado")
OPTION_FIELDS = ("modelo", "precio", "url", "estado", "notas", "imagen")


def default_icons(url, domain):
    return [
        f"https://icons.duckduckgo.com/ip3/{quote(domain, safe='')}.ico",
        urljoin(url, "/favicon.ico"),
    ]


def read_options(folder):
    options = []
    for path in sorted((folder / "opciones").glob("*.toml")):
        with path.open("rb") as stream:
            option = tomllib.load(stream)
        row = {}
        for field in OPTION_FIELDS:
            value = option.get(field, "")
            if not isinstance(value, str):
                raise ValueError(f"{path}: {field} debe ser texto entre comillas")
            row[field] = value.strip()
        row["nombre_archivo"] = path.stem
        if not row["url"]:
            raise ValueError(f"{path}: falta url")
        try:
            url = urlsplit(row["url"])
            if (
                url.scheme not in ("http", "https")
                or not url.hostname
                or url.username is not None
                or any(char.isspace() for char in row["url"])
            ):
                raise ValueError("se esperaba una URL HTTP o HTTPS sin credenciales")
            hostname = url.hostname
        except ValueError as error:
            raise ValueError(f"{path}: {error}") from error
        if row["imagen"] and not http_url("", row["imagen"]):
            raise ValueError(f"{path}: imagen debe ser una URL HTTP o HTTPS absoluta")
        row["tienda"] = hostname.removeprefix("www.")
        row["iconos"] = default_icons(row["url"], row["tienda"])
        options.append(row)
    return options


def read_sources(folder):
    path = folder / "fuentes.txt"
    if not path.exists():
        return []
    sources = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        url = line.strip()
        if not url:
            continue
        try:
            parts = urlsplit(url)
            if (
                parts.scheme not in ("http", "https")
                or not parts.hostname
                or parts.username is not None
                or any(char.isspace() for char in url)
            ):
                raise ValueError("se esperaba un enlace HTTP o HTTPS sin credenciales")
            parts.port  # Comprueba el puerto antes de generar los enlaces.
        except ValueError as error:
            raise ValueError(f"{path}:{line_number}: {error}") from error

        domain = parts.hostname.removeprefix("www.")
        sources.append({
            "url": url,
            "nombre": domain,
            "iconos": default_icons(url, domain),
        })
    return sources


def read_product(path):
    slug = path.parent.name
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug):
        raise ValueError(f"{path}: usa un nombre de carpeta como monitor-27")
    with path.open("rb") as stream:
        product = tomllib.load(stream)
    for field in ("titulo", "categoria", "estado", "resumen"):
        if not isinstance(product.get(field), str) or not product[field].strip():
            raise ValueError(f"{path}: {field} debe contener texto")
    if product["estado"] not in STATES:
        raise ValueError(f"{path}: estado esperado: {', '.join(STATES)}")
    notes = path.parent / "notas.txt"
    return {
        **product,
        "slug": slug,
        "opciones": read_options(path.parent),
        "fuentes": read_sources(path.parent),
        "notas": notes.read_text(encoding="utf-8").strip() if notes.exists() else "",
    }


def store_favicons(items, pages_by_url, cache):
    stores = {}
    for item in items:
        service, fallback = item["iconos"]
        saved, candidates = stores.setdefault(fallback, ([], [service]))
        record, _ = pages_by_url[item["url"]]
        saved.append(record.get("icono_local"))
        candidates.extend(record.get("iconos", []))

    def resolve(fallback):
        saved, candidates = stores[fallback]
        return cache.favicons(saved, [*candidates, fallback])

    return by_store(stores, resolve)


def build(reload_version=None, refresh=False):
    products = [read_product(path) for path in sorted(ROOT.glob("datos/*/ficha.toml"))]
    products.sort(key=lambda item: item["titulo"].casefold())
    sources = [source for product in products for source in product["fuentes"]]
    options = [option for product in products for option in product["opciones"]]
    cache = LocalCache(ROOT / "cache", refresh)
    items = options + sources
    pages_by_url = by_store((item["url"] for item in items), cache.page)
    favicons = store_favicons(items, pages_by_url, cache)
    media_urls = []
    for option in options:
        record, _ = pages_by_url[option["url"]]
        media_urls.extend(filter(None, (record.get("imagen"), option["imagen"])))
    media = by_store(media_urls, cache.media)
    used = set()

    def local_paths(names):
        used.update(names)
        return ["../../assets/tiendas/" + name for name in dict.fromkeys(names)]

    for item in items:
        record, fresh_price = pages_by_url[item["url"]]
        icons = favicons[item["iconos"][-1]]
        images = []
        if "modelo" in item:
            item["modelo"] = item["modelo"] or record.get("modelo") or item["nombre_archivo"]
            item["fecha_precio"] = "" if item["precio"] or fresh_price else record.get("fecha", "")
            item["precio"] = item["precio"] or record.get("precio", "")
            preview = media.get(record.get("imagen"))
            if preview:
                images.append(preview)
        else:
            item["titulo"] = record.get("titulo", "")
        cache.remember_assets(record, images, icons)
        item["iconos"] = local_paths(icons)
        if "imagen" in item:
            manual = media.get(item["imagen"])
            if manual:
                images.append(manual)
            item["imagenes"] = local_paths(images)

    env = Environment(
        loader=FileSystemLoader(ROOT / "templates"),
        autoescape=select_autoescape(),
        undefined=StrictUndefined,
    )
    env.globals["reload_version"] = reload_version
    pages = {
        Path("index.html"): env.get_template("index.html").render(
            productos=products, estados=STATES, base="./", titulo="Mis compras"
        ),
    }
    template = env.get_template("producto.html")
    for product in products:
        pages[Path("productos", product["slug"], "index.html")] = template.render(
            p=product, base="../../", titulo=product["titulo"]
        )

    if DIST.exists():
        shutil.rmtree(DIST)
    shutil.copytree(ROOT / "static", DIST / "assets")
    if used:
        media_dir = DIST / "assets/tiendas"
        media_dir.mkdir()
        for name in used:
            shutil.copyfile(cache.root / "archivos" / name, media_dir / name)
    for path, html in pages.items():
        target = DIST / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(html, encoding="utf-8")
    print(f"Generadas {len(pages)} páginas en {DIST}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh", action="store_true", help="Actualizar metadatos y fotos. Descargar solo los favicons que falten.")
    build(refresh=parser.parse_args().refresh)
