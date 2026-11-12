"""Serve the built phone page to the private tunnel (ADR 070).

Side effect, on purpose: listens on a loopback port and answers GET and HEAD from one folder, the
built ``frontend/dist``. It never binds another interface: the tunnel (``tailscale serve``) is the
only way in from another device, and it forwards to this port. It serves files and nothing else --
no API, no write.

Why not ``python -m http.server``: that one speaks HTTP/1.0 with a five-connection backlog. The
tunnel's proxy asks for the phone page's files in one burst (about eighty on first load), and a
share of them came back 502, so the page did not start. This one keeps connections open
(HTTP/1.1) and queues a burst.

It names each file's type itself, from the short list a built page holds. The standard handler asks the
operating system, which on Windows reads the registry the first time: with eighty requests arriving at
once on a server that had just started, each thread read it, and the first burst stalled about ten
seconds. A registry can also call a ``.js`` file plain text, which a browser refuses to run as a module.

It also says how long a file may be kept: a file under ``assets/`` has its content's hash in its
name, so a phone may keep it for good; every other file (the pages, the manifest) is asked for
again each time, so a reload after ``npm run build`` shows the new build.

    py -3 tools/serve_phone_page.py                 # frontend/dist on 127.0.0.1:4181
    py -3 tools/serve_phone_page.py --port 4181 --directory C:\\path\\to\\Nova\\frontend\\dist
"""
from __future__ import annotations

import argparse
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEFAULT_DIRECTORY = REPO / "frontend" / "dist"
DEFAULT_PORT = 4181
# The only address this server may listen on: the tunnel forwards to it from this PC.
LOOPBACK = "127.0.0.1"
# Connections the system holds while every worker thread is busy; a first load asks for about eighty files at once.
BACKLOG = 512

# Every kind of file `npm run build` puts in dist. Anything else is sent as bytes to download, never guessed.
CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json",
    ".map": "application/json",
    ".webmanifest": "application/manifest+json",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".ico": "image/x-icon",
    ".woff2": "font/woff2",
    ".woff": "font/woff",
    ".wasm": "application/wasm",
    ".txt": "text/plain; charset=utf-8",
}
UNKNOWN_TYPE = "application/octet-stream"

HASHED_PREFIX = "/assets/"
CACHE_HASHED = "public, max-age=31536000, immutable"
CACHE_FRESH = "no-cache"


def cache_control(path: str) -> str:
    """How long a browser may keep the file at *path* (the request path, with or without a query)."""
    return CACHE_HASHED if path.split("?", 1)[0].startswith(HASHED_PREFIX) else CACHE_FRESH


class PhonePageHandler(SimpleHTTPRequestHandler):
    """One folder, read only, over connections that stay open."""

    protocol_version = "HTTP/1.1"

    def guess_type(self, path) -> str:  # noqa: ANN001 -- the base class's signature
        return CONTENT_TYPES.get(Path(str(path)).suffix.lower(), UNKNOWN_TYPE)

    def end_headers(self) -> None:
        self.send_header("Cache-Control", cache_control(self.path))
        super().end_headers()

    def list_directory(self, path):  # noqa: ANN001, ANN201 -- the base class's signature
        # A folder is never listed: the page names every file it needs.
        self.send_error(404, "File not found")
        return None

    def log_message(self, format: str, *args) -> None:  # noqa: A002 -- the base class's name
        # Quiet on success; a refusal or a missing file is worth a line.
        if args and str(args[1] if len(args) > 1 else "").startswith(("4", "5")):
            super().log_message(format, *args)


class PhonePageServer(ThreadingHTTPServer):
    request_queue_size = BACKLOG
    daemon_threads = True


def make_server(directory: Path, port: int) -> PhonePageServer:
    """A server for *directory* on the loopback *port* (0 picks a free one), not yet serving."""
    return PhonePageServer((LOOPBACK, port), partial(PhonePageHandler, directory=str(directory)))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Serve the built phone page to the private tunnel.")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--directory", type=Path, default=DEFAULT_DIRECTORY)
    args = parser.parse_args(argv)
    directory = args.directory.resolve()
    if not (directory / "phone.html").is_file():
        print(f"No phone.html in {directory}. Build the page first: npm run build (in frontend/).", file=sys.stderr)
        return 2
    server = make_server(directory, args.port)
    print(f"Serving {directory} on http://{LOOPBACK}:{server.server_address[1]} (Ctrl+C stops it).", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
