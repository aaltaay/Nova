"""Loopback HTTP for the review page. One shared listener. Read only.

Bind is 127.0.0.1. The desk's Vite server proxies ``/api/review`` here when
``NOVA_REVIEW_API`` matches this port. A second MCP client attaches to the
listener that is already up instead of binding again. Tests pass their own
readers and port 0.

Owner: this module. The lease file in the temp dir is a runtime pointer
(``schema_version`` 1, port, pid), not operator data. A failed health check
stales it.
"""
from __future__ import annotations

import json
import math
import os
import socket
import sys
import tempfile
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import parse_qs, urlparse
from urllib.request import urlopen

import nova_review_load as review_load

DEFAULT_PORT = 18765
SERVICE = "nova-review"
LEASE_SCHEMA = 1
LEASE = Path(tempfile.gettempdir()) / "nova-review-http.json"
LEASE_LOCK = Path(tempfile.gettempdir()) / "nova-review-http.lock"

_owner: ThreadingHTTPServer | None = None
_owner_guard = threading.Lock()


def scrub(value: Any) -> Any:
    """JSON numbers only. NaN and infinity become null so ``response.json()`` can parse the body."""
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {key: scrub(item) for key, item in value.items()}
    if isinstance(value, list):
        return [scrub(item) for item in value]
    return value


def _query(path: str) -> dict[str, str]:
    parsed = urlparse(path)
    found = parse_qs(parsed.query, keep_blank_values=False)
    return {key: values[-1] for key, values in found.items() if values}


def make_handler(bars_reader, daily_reader, allowed_origins: tuple[str, ...] = ()):
    origins = frozenset(allowed_origins)

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt: str, *args: Any) -> None:
            return

        def _cors(self) -> None:
            origin = self.headers.get("Origin")
            if origin and origin in origins:
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Vary", "Origin")

        def _send(self, status: int, body: dict[str, Any]) -> None:
            raw = json.dumps(scrub(body), allow_nan=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self._cors()
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(raw)

        def do_OPTIONS(self) -> None:  # noqa: N802
            self.send_response(204)
            self._cors()
            self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path == "/api/review/health":
                self._send(200, {"ok": True, "service": SERVICE})
                return
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
            except ValueError as exc:
                self._send(400, {"ok": False, "error": str(exc)})
                return
            except Exception as exc:  # maintainer: allow-swallow a bad review read is the HTTP error
                self._send(500, {"ok": False, "error": f"{type(exc).__name__}: {exc}"})
                return
            self._send(200, body)

    return Handler


class ReviewHTTPServer(ThreadingHTTPServer):
    """On Windows a second bind can succeed on a port another process holds.

    ``SO_EXCLUSIVEADDRUSE`` makes that bind fail so the caller can move to a free port.
    """

    def server_bind(self) -> None:
        if os.name == "nt":
            self.allow_reuse_address = False
            exclusive = getattr(socket, "SO_EXCLUSIVEADDRUSE", 0x0004)
            self.socket.setsockopt(socket.SOL_SOCKET, exclusive, 1)
        super().server_bind()


def serve(port: int = DEFAULT_PORT, bars_reader=None, daily_reader=None,
          allowed_origins: tuple[str, ...] = ()) -> ThreadingHTTPServer:
    handler = make_handler(
        bars_reader or review_load.front_door_bars,
        daily_reader or review_load.front_door_daily,
        allowed_origins,
    )
    return ReviewHTTPServer(("127.0.0.1", port), handler)


def health_ok(port: int) -> bool:
    try:
        with urlopen(f"http://127.0.0.1:{port}/api/review/health", timeout=0.4) as response:
            if response.status != 200:
                return False
            body = json.loads(response.read().decode())
    except (OSError, ValueError):
        return False
    return body.get("ok") is True and body.get("service") == SERVICE


def lease_file() -> Path:
    override = os.environ.get("NOVA_REVIEW_LEASE")
    return Path(override) if override else LEASE


def lock_file() -> Path:
    override = os.environ.get("NOVA_REVIEW_LEASE_LOCK")
    return Path(override) if override else LEASE_LOCK


def _read_lease_body() -> dict[str, Any] | None:
    try:
        body = json.loads(lease_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(body, dict) or body.get("schema_version") != LEASE_SCHEMA:
        return None
    return body


def _read_lease() -> int | None:
    body = _read_lease_body()
    if not body:
        return None
    try:
        return int(body["port"])
    except (KeyError, TypeError, ValueError):
        return None


def _write_lease(port: int, token: str | None = None) -> None:
    if not token:
        current = _read_lease_body() or {}
        try:
            same_port = int(current.get("port")) == int(port)
        except (TypeError, ValueError):
            same_port = False
        kept = current.get("token")
        if same_port and isinstance(kept, str) and kept:
            token = kept
    body: dict[str, Any] = {"schema_version": LEASE_SCHEMA, "port": port, "pid": os.getpid()}
    if token:
        body["token"] = token
    lease_file().write_text(json.dumps(body), encoding="utf-8")


def read_token() -> str:
    body = _read_lease_body() or {}
    token = body.get("token")
    return token if isinstance(token, str) else ""


@contextmanager
def _lease_lock() -> Iterator[None]:
    path = lock_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(path, "a+b")
    try:
        if os.name == "nt":
            import msvcrt
            if handle.seek(0, os.SEEK_END) == 0:
                handle.write(b" ")
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        try:
            if os.name == "nt":
                import msvcrt
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


def _start(port: int, allowed_origins: tuple[str, ...]) -> tuple[ThreadingHTTPServer, str]:
    if port and health_ok(port):
        raise OSError(f"nova-review: {port} already answers the health check")
    try:
        httpd = serve(port, allowed_origins=allowed_origins)
    except OSError:
        if health_ok(port):
            raise
        httpd = serve(0, allowed_origins=allowed_origins)
        actual = int(httpd.server_address[1])
        print(
            f"nova-review: port {port} is taken by another process. "
            f"Review data is on http://127.0.0.1:{actual}/api/review",
            file=sys.stderr,
        )
        return httpd, "moved"
    actual = int(httpd.server_address[1])
    print(f"nova-review: listening on http://127.0.0.1:{actual}/api/review", file=sys.stderr)
    return httpd, "started"


def ensure_shared(port: int = DEFAULT_PORT, *, allowed_origins: tuple[str, ...] = ()) -> tuple[int, str]:
    """Return ``(port, how)``. ``how`` is ``shared`` when another Nova review listener is already up."""
    global _owner
    with _owner_guard:
        if _owner is not None:
            return int(_owner.server_address[1]), "started"
    with _lease_lock():
        with _owner_guard:
            if _owner is not None:
                return int(_owner.server_address[1]), "started"
            advertised = _read_lease()
            if advertised and health_ok(advertised):
                return advertised, "shared"
            if health_ok(port):
                _write_lease(port)
                return port, "shared"
            try:
                httpd, how = _start(port, allowed_origins)
            except OSError:
                if health_ok(port):
                    return port, "shared"
                raise
            threading.Thread(target=httpd.serve_forever, name="nova-review-http", daemon=True).start()
            _owner = httpd
            actual = int(httpd.server_address[1])
            _write_lease(actual)
            return actual, how


def stop_owned() -> None:
    """Stop the listener this process started. Tests use this. A shared listener is left running."""
    global _owner
    with _owner_guard:
        httpd = _owner
        _owner = None
    if httpd is None:
        return
    port = int(httpd.server_address[1])
    httpd.shutdown()
    httpd.server_close()
    try:
        body = json.loads(lease_file().read_text(encoding="utf-8"))
        if body.get("pid") == os.getpid() and int(body.get("port", -1)) == port:
            lease_file().unlink()
    except (OSError, ValueError):
        return
