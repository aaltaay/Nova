#!/usr/bin/env python3
"""One review engine per PC. It outlives the MCP client that started it.

maintainer: one-concern the single review engine (listener, lease, and the one Chromium) must live in one place

The engine owns the loopback listener and the one Chromium. A chart call
attaches when the health check matches this file's version, and starts a new
process when it does not. The process exits after it has been idle.

Port 18765 is the default. 8765 is the research downloads page and is not used.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import urlopen

import nova_review_http as review_http
import nova_review_warm as review_warm

ENGINE_VERSION = "2"
IDLE_SEC = 30 * 60
REPO = Path(__file__).resolve().parents[1]
PNG_STUB = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


class _State:
    def __init__(self) -> None:
        self.renderer_starts = 0
        self._counted = False
        self.shots: review_warm.ReviewShots | None = None
        self.last = time.monotonic()
        self.lock = threading.Lock()

    def touch(self) -> None:
        self.last = time.monotonic()


STATE = _State()
_OWNER = None


def dist_dir() -> Path:
    raw = os.environ.get("NOVA_REVIEW_DIST")
    return Path(raw) if raw else REPO / "frontend" / "dist"


def idle_sec() -> float:
    raw = os.environ.get("NOVA_REVIEW_IDLE_SEC", str(IDLE_SEC))
    try:
        return max(float(raw), 1.0)
    except ValueError:
        return float(IDLE_SEC)


def read_health(port: int, timeout: float = 0.4) -> dict[str, Any] | None:
    try:
        with urlopen(f"http://127.0.0.1:{port}/api/review/health", timeout=timeout) as response:
            if response.status != 200:
                return None
            body = json.loads(response.read().decode())
    except (OSError, ValueError):
        return None
    return body if isinstance(body, dict) else None


def engine_ok(body: dict[str, Any] | None) -> bool:
    return bool(
        body
        and body.get("ok") is True
        and body.get("service") == review_http.SERVICE
        and body.get("version") == ENGINE_VERSION
    )


def _live_port(preferred: int) -> int | None:
    advertised = review_http._read_lease()
    for candidate in (advertised, preferred):
        if candidate and engine_ok(read_health(int(candidate))):
            return int(candidate)
    return None


def _stop_mismatched(port: int) -> None:
    body = read_health(port)
    if not body or body.get("service") != review_http.SERVICE or body.get("version") == ENGINE_VERSION:
        return
    pid = body.get("pid")
    if not isinstance(pid, int) or pid <= 0 or pid == os.getpid():
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        return
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        if read_health(port) is None:
            return
        time.sleep(0.05)


def _spawn(port: int) -> None:
    cmd = [sys.executable, str(Path(__file__).resolve()), "--port", str(port)]
    kwargs: dict[str, Any] = {
        "env": os.environ.copy(),
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if os.name == "nt":
        flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        kwargs["creationflags"] = flags
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen(cmd, **kwargs)


def _wait_live(preferred: int, seconds: float = 8) -> int | None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        found = _live_port(preferred)
        if found:
            return found
        time.sleep(0.05)
    return None


def ensure_engine(port: int) -> int:
    """Return the live engine port. Start one detached process when none is healthy."""
    found = _live_port(port)
    if found:
        return found
    advertised = review_http._read_lease()
    for candidate in (advertised, port):
        if candidate:
            _stop_mismatched(int(candidate))
    _spawn(port)
    found = _wait_live(port)
    if found:
        return found
    _spawn(port)
    found = _wait_live(port)
    if found:
        return found
    raise OSError("review engine did not become healthy")


def _owner_path() -> Path:
    return Path(str(review_http.lock_file()) + ".owner")


def _hold_owner_lock() -> bool:
    """One engine process holds this lock until it exits. A second starter leaves."""
    global _OWNER
    path = _owner_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(path, "a+b")
    try:
        if os.name == "nt":
            import msvcrt
            if handle.seek(0, os.SEEK_END) == 0:
                handle.write(b" ")
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return False
    _OWNER = handle
    return True


def _stub_shoot(url: str, dest: Path) -> dict[str, Any]:
    try:
        with urlopen(url, timeout=5) as response:
            status = response.status
            body = response.read()
    except OSError as exc:
        return {"ok": False, "error": {"code": "REVIEW_DESK_UNREACHABLE", "detail": str(exc)}}
    if status != 200 or b"data-review-ready" not in body:
        return {"ok": False, "error": {"code": "REVIEW_DESK_UNREACHABLE", "detail": "review page was not ready"}}
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(PNG_STUB)
    return {
        "ok": True,
        "path": str(dest),
        "sha256": hashlib.sha256(PNG_STUB).hexdigest(),
        "bytes": len(PNG_STUB),
        "png": PNG_STUB,
    }


def _shots() -> review_warm.ReviewShots:
    if STATE.shots is None:
        shoot = _stub_shoot if os.environ.get("NOVA_REVIEW_SHOT") == "stub" else None
        STATE.shots = review_warm.ReviewShots(shoot=shoot)
    return STATE.shots


def take_shot(url: str, dest: Path) -> dict[str, Any]:
    renderer = _shots()
    with STATE.lock:
        if not STATE._counted:
            started = renderer.start()
            if not started.get("ok"):
                return started
            STATE.renderer_starts += 1
            STATE._counted = True
    return renderer.shoot(url, dest)


def request_shot(port: int, url: str, dest: Path, req_id: str) -> dict[str, Any]:
    import urllib.error
    import urllib.request

    payload = json.dumps({"id": req_id, "url": url, "dest": str(dest)}).encode()
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/api/review/shot",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=90) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        raw = exc.read()
    except OSError as exc:
        return {"ok": False, "error": {"code": "REVIEW_DESK_UNREACHABLE", "detail": str(exc)}}
    try:
        body = json.loads(raw.decode())
    except ValueError:
        return {"ok": False, "error": {"code": "REVIEW_SHOT_FAILED", "detail": "shot reply was not json"}}
    if body.get("id") != req_id:
        return {"ok": False, "error": {"code": "REVIEW_SHOT_FAILED", "detail": "shot id did not match"}}
    png = body.get("png")
    if isinstance(png, str):
        body["png"] = base64.b64decode(png)
    return body


def _origins() -> tuple[str, ...]:
    raw = os.environ.get("NOVA_REVIEW_ORIGINS", "")
    listed = tuple(item for item in raw.split(",") if item)
    if listed:
        return listed
    base = os.environ.get("NOVA_REVIEW_BASE", "http://127.0.0.1:5173").rstrip("/")
    return (base,) if base else ()


def make_engine_handler():
    parent = review_http.make_handler(None, None, _origins())

    class Handler(parent):
        def _touch(self) -> None:
            STATE.touch()

        def _send_file(self, path: Path) -> None:
            if not path.is_file():
                self._send(404, {"ok": False, "error": "not found"})
                return
            raw = path.read_bytes()
            kind = "application/octet-stream"
            if path.suffix == ".html":
                kind = "text/html; charset=utf-8"
            elif path.suffix == ".js":
                kind = "text/javascript; charset=utf-8"
            elif path.suffix == ".css":
                kind = "text/css; charset=utf-8"
            self.send_response(200)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self) -> None:  # noqa: N802
            self._touch()
            parsed = urlparse(self.path)
            if parsed.path == "/api/review/health":
                self._send(200, {
                    "ok": True,
                    "service": review_http.SERVICE,
                    "version": ENGINE_VERSION,
                    "renderer_starts": STATE.renderer_starts,
                    "pid": os.getpid(),
                })
                return
            if parsed.path in ("/review", "/review/"):
                self._send_file(dist_dir() / "index.html")
                return
            if parsed.path.startswith("/assets/"):
                self._send_file(dist_dir() / parsed.path.lstrip("/"))
                return
            super().do_GET()

        def do_POST(self) -> None:  # noqa: N802
            self._touch()
            parsed = urlparse(self.path)
            if parsed.path != "/api/review/shot":
                self._send(404, {"ok": False, "error": "not found"})
                return
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b""
            try:
                body = json.loads(raw.decode() or "{}")
            except ValueError:
                self._send(400, {"ok": False, "error": "bad json"})
                return
            req_id = str(body.get("id") or "")
            url = str(body.get("url") or "")
            dest = str(body.get("dest") or "")
            if not req_id or not url or not dest:
                self._send(400, {"ok": False, "id": req_id, "error": "bad shot"})
                return
            result = take_shot(url, Path(dest))
            answer = {"id": req_id, **result}
            png = answer.get("png")
            if isinstance(png, (bytes, bytearray)):
                answer["png"] = base64.b64encode(bytes(png)).decode("ascii")
            self._send(200 if result.get("ok") else 500, answer)

    return Handler


def serve_engine(port: int):
    handler = make_engine_handler()
    from http.server import ThreadingHTTPServer

    try:
        httpd = ThreadingHTTPServer(("127.0.0.1", port), handler)
        how = "started"
    except OSError:
        if engine_ok(read_health(port)):
            return None
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        actual = int(httpd.server_address[1])
        print(
            f"nova-review: port {port} is taken by another process. "
            f"Review data is on http://127.0.0.1:{actual}/api/review",
            file=sys.stderr,
        )
        how = "moved"
    actual = int(httpd.server_address[1])
    if how == "started":
        print(f"nova-review: listening on http://127.0.0.1:{actual}/api/review", file=sys.stderr)
    return httpd


def _watch_idle(httpd) -> None:
    limit = idle_sec()
    while True:
        time.sleep(min(5.0, limit))
        if time.monotonic() - STATE.last >= limit:
            threading.Thread(target=httpd.shutdown, daemon=True).start()
            return


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Nova review engine")
    parser.add_argument("--port", type=int, default=review_http.DEFAULT_PORT)
    args = parser.parse_args(argv)
    if _live_port(args.port):
        return 0
    if not _hold_owner_lock():
        found = _wait_live(args.port)
        return 0 if found else 1
    httpd = serve_engine(args.port)
    if httpd is None:
        return 0
    with review_http._lease_lock():
        review_http._write_lease(int(httpd.server_address[1]))
    threading.Thread(target=_watch_idle, args=(httpd,), name="nova-review-idle", daemon=True).start()

    def _stop(_signum, _frame) -> None:
        threading.Thread(target=httpd.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, _stop)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        httpd.shutdown()
    httpd.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
