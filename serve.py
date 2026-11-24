import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from uuid import uuid4

from jinja2 import TemplateError

from build import DIST, ROOT, build


def snapshot():
    files = {}
    for folder in ("datos", "templates", "static", "cache"):
        for path in (ROOT / folder).rglob("*"):
            try:
                if path.is_file():
                    stat = path.stat()
                    files[path] = (stat.st_mtime_ns, stat.st_size)
            except FileNotFoundError:
                continue
    return files


class LocalHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/__reload":
            return super().do_GET()

        version = self.server.version.encode("ascii")
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(version)))
        self.end_headers()
        self.wfile.write(version)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_request(self, code="-", size="-"):
        if self.path != "/__reload":
            super().log_request(code, size)


class LocalServer(ThreadingHTTPServer):
    def rebuild(self, refresh=False):
        version = uuid4().hex
        build(reload_version=version, refresh=refresh)
        self.version = version

    def service_actions(self):
        current = snapshot()
        if current == self.files:
            return

        self.files = current
        try:
            self.rebuild()
        except (OSError, ValueError, TemplateError) as error:
            print(f"No se pudo regenerar la web: {error}", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh", action="store_true", help="Actualizar la caché al arrancar")
    args = parser.parse_args()
    handler = partial(LocalHandler, directory=DIST)
    with LocalServer(("0.0.0.0", 8000), handler) as server:
        server.rebuild(refresh=args.refresh)
        server.files = snapshot()
        print("Servidor local listo en el puerto 8000.", flush=True)
        server.serve_forever(poll_interval=1)


if __name__ == "__main__":
    main()
