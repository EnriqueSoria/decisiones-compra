import io
import json
import shutil
import tempfile
import unittest
from email.message import Message
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.response import addinfourl

import build
import source_metadata


class SlowdecoTest(unittest.TestCase):
    def test_offer_then_rate_limit_then_new_price(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name in ("templates", "static"):
                shutil.copytree(build.ROOT / name, root / name)
            product = root / "datos/mueble-tv"
            (product / "opciones").mkdir(parents=True)
            (product / "ficha.toml").write_text(
                'titulo="Mueble TV"\ncategoria="Salón"\nestado="Explorando"\nresumen="Muebles de TV"\n'
            )
            url = ("https://slowdeco.es/collections/black-friday-mueble-de-tv/products/"
                   "mueble-tv-ptas-cajonestulsa-nogal-00mb362533")
            (product / "opciones/tulsa.toml").write_text(f'url="{url}"')
            (product / "fuentes.txt").write_text("https://slowdeco.es/")
            amount = "925.60"
            headers = Message()
            headers["Content-Type"] = "text/html"
            attempts = []
            photo = b"GIF89a-photo-1"
            icon = b"GIF89a-icon-1"
            service_icon = "https://icons.duckduckgo.com/ip3/slowdeco.es.ico"
            photo_url = "https://slowdeco.es/tulsa.jpg"

            def fetch(request, timeout):
                attempts.append(request.full_url)
                if request.get_header("Accept") == "image/*":
                    data = photo if request.full_url.endswith("tulsa.jpg") else icon
                    return addinfourl(io.BytesIO(data), headers, request.full_url)
                if request.full_url != url:
                    return addinfourl(io.BytesIO(b"<title>Slowdeco</title>"), headers, request.full_url)
                if not amount:
                    raise HTTPError(url, 429, "Too many requests", {"Retry-After": "60"}, None)
                data = {"@type": "Product", "name": "Mueble TV Tulsa", "image": ["/tulsa.jpg"],
                        "offers": {"priceCurrency": "EUR", "priceSpecification": [
                            {"price": "1157.00", "priceType": "https://schema.org/StrikethroughPrice"},
                            {"price": amount}]}}
                html = (f'<head><link rel="icon" href="/{amount}.ico"></head>'
                        f'<body><script type="application/ld+json">{json.dumps(data)}</script></body>')
                return addinfourl(io.BytesIO(html.encode()), headers, url)

            page = root / "dist/productos/mueble-tv/index.html"
            with (patch.object(build, "ROOT", root), patch.object(build, "DIST", root / "dist"),
                  patch.object(source_metadata, "urlopen", fetch), patch.object(source_metadata, "retry_at", {}),
                  patch.object(source_metadata, "monotonic", return_value=100) as clock):
                build.build()
                self.assertEqual(attempts[:2], [url, "https://slowdeco.es/"])
                self.assertCountEqual(attempts[2:], [service_icon, photo_url])
                self.assertIn("Slowdeco", page.read_text())
                media_dir = root / "dist/assets/tiendas"
                self.assertCountEqual([p.read_bytes() for p in media_dir.iterdir()], [photo, icon])
                self.assertIn("925,60 €", page.read_text())
                self.assertNotIn("Último precio observado", page.read_text())

                amount = ""
                attempts.clear()
                build.build()
                self.assertEqual(attempts, [])
                build.build(refresh=True)
                self.assertEqual(attempts, [url])
                attempts.clear()
                build.build()
                self.assertEqual(attempts, [])
                self.assertCountEqual([p.read_bytes() for p in media_dir.iterdir()], [photo, icon])
                html = page.read_text()
                for value in ("Mueble TV Tulsa", "../../assets/tiendas/", "925,60 €", "Último precio observado"):
                    self.assertIn(value, html)

                clock.return_value = 161
                amount = "899.00"
                photo = b"GIF89a-photo-2"
                saved_icon = icon
                icon = b"GIF89a-icon-2"
                build.build(refresh=True)
                self.assertCountEqual(attempts, [url, "https://slowdeco.es/", photo_url])
                self.assertCountEqual([p.read_bytes() for p in media_dir.iterdir()], [photo, saved_icon])
                html = page.read_text()
                self.assertIn("899,00 €", html)
                self.assertNotIn("925,60 €", html)
                self.assertNotIn("Último precio observado", html)

                cached_icon = next(p for p in (root / "cache/archivos").iterdir() if p.read_bytes() == saved_icon)
                cached_icon.unlink()
                attempts.clear()
                build.build(refresh=True)
                self.assertCountEqual(attempts, [url, "https://slowdeco.es/", service_icon, photo_url])
                self.assertCountEqual([p.read_bytes() for p in media_dir.iterdir()], [photo, icon])
