"""Loopback HTTP for the review page. Read only. No orders and no broker.

Bind is 127.0.0.1. The desk's Vite server proxies ``/api/review`` here so the
page stays same-origin. Tests pass their own readers and port 0.
"""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

import nova_review_load as review_load


def _query(path: str) -> dict[str, str]:
    parsed = urlparse(path)
    found = parse_qs(parsed.query, keep_blank_values=False)
    return {key: values[-1] for key, values in found.items() if values}


def make_handler(bars_reader, daily_reader):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt: str, *args: Any) -> None:
            return

        def _send(self, status: int, body: dict[str, Any]) -> None:
            raw = json.dumps(body).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(raw)

        def do_OPTIONS(self) -> None:  # noqa: N802
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path != "/api/review":
                self._send(404, {"ok": False, "error": "not found"})
                return
            query = _query(self.path)
            try:
                body = review_load.load_review(
                    query.get("symbol", ""),
                    query.get("date", ""),
                    query.get("tf"),
                    query.get("as_of"),
                    bars_reader=bars_reader,
                    daily_reader=daily_reader,
                )
                self._send(200, body)
            except Exception as exc:  # maintainer: allow-swallow a bad review read is the HTTP answer
                self._send(200, {"ok": False, "error": f"{type(exc).__name__}: {exc}"})

    return Handler


def serve(port: int = 8765, bars_reader=None, daily_reader=None) -> ThreadingHTTPServer:
    handler = make_handler(bars_reader or review_load.front_door_bars, daily_reader or review_load.front_door_daily)
    httpd = ThreadingHTTPServer(("127.0.0.1", port), handler)
    return httpd


def serve_background(port: int = 8765) -> ThreadingHTTPServer:
    import threading
    httpd = serve(port)
    threading.Thread(target=httpd.serve_forever, name="nova-review-http", daemon=True).start()
    return httpd
