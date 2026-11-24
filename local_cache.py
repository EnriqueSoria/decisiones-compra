"""Caché de páginas y recursos compartida por el generador y el servidor."""
import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from hashlib import sha256
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.parse import urlsplit

from source_metadata import read_image, read_metadata


def key(url):
    return sha256(url.encode()).hexdigest()


def write_bytes(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=path.parent, delete=False) as temp:
        try:
            temp.write(data)
            temp.close()
            Path(temp.name).replace(path)
        finally:
            Path(temp.name).unlink(missing_ok=True)


def load_record(path, url):
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return {}
    return record if isinstance(record, dict) and record.get("url") == url else {}


def save_record(path, record):
    write_bytes(path, (json.dumps(record, indent=2, ensure_ascii=False) + "\n").encode())


def by_store(urls, fetch):
    stores = {}
    for url in dict.fromkeys(urls):
        stores.setdefault(urlsplit(url).hostname, []).append(url)

    def fetch_store(group):
        return {url: fetch(url) for url in group}

    with ThreadPoolExecutor(max_workers=8) as pool:
        return {url: data for store in pool.map(fetch_store, stores.values()) for url, data in store.items()}


class LocalCache:
    def __init__(self, root, refresh):
        self.root = root
        self.refresh = refresh

    def page(self, url):
        path = self.root / (key(url) + ".json")
        saved = load_record(path, url)
        if saved and not self.refresh:
            return saved, False

        page = read_metadata(url)
        record = dict(saved, url=url)
        for field, value in (("titulo", page.title), ("modelo", page.product_name or page.title),
                             ("imagen", page.image), ("iconos", page.icons)):
            if value:
                record[field] = value
        if page.price:
            record.update(precio=page.price, fecha=date.today().isoformat())
        if record != saved:
            save_record(path, record)
        return record, bool(page.price)

    def file_exists(self, name):
        return (isinstance(name, str) and re.fullmatch(r"[0-9a-f]{64}\.(png|jpg|gif|webp|ico|avif|bmp)", name)
                and (self.root / "archivos" / name).is_file())

    def favicons(self, saved_names, urls):
        urls = list(dict.fromkeys(urls))
        names = list(saved_names)
        for url in urls:
            record = load_record(self.root / "medios" / (key(url) + ".json"), url)
            names.append(record.get("archivo"))
        available = [name for name in dict.fromkeys(names) if self.file_exists(name)]
        if available:
            return available
        for url in urls:
            name = self.media(url)
            if name:
                return [name]
        return []

    def media(self, url):
        path = self.root / "medios" / (key(url) + ".json")
        saved = load_record(path, url)
        previous = saved.get("archivo", "")
        if saved and not self.refresh and (not previous or self.file_exists(previous)):
            return previous
        data, extension = read_image(url)
        name = previous if self.file_exists(previous) else ""
        if data:
            name = sha256(data).hexdigest() + "." + extension
            target = self.root / "archivos" / name
            if not target.exists():
                write_bytes(target, data)
        record = {"url": url, "archivo": name}
        if record != saved:
            save_record(path, record)
        return name

    def remember_assets(self, record, images, icons):
        # Una tienda puede mover un recurso antes de que la nueva URL responda.
        changed = False
        for field, names in (("imagen_local", images), ("icono_local", icons)):
            if names and record.get(field) != names[0]:
                record[field] = names[0]
                changed = True
            elif not names and self.file_exists(record.get(field)):
                names.append(record[field])
        if changed:
            save_record(self.root / (key(record["url"]) + ".json"), record)
