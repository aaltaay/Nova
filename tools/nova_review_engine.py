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
import hmac
import ipaddress
import json
import os
import secrets
import signal
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse
from urllib.request import urlopen

import nova_review_build as review_build
import nova_review_causal as causal
import nova_review_http as review_http
import nova_review_load as review_load
import nova_review_warm as review_warm

ENGINE_VERSION = "4"
SHOT_HEADER = "X-Nova-Review-Token"
HOST_NOT_ALLOWED = "HOST_NOT_ALLOWED"
_THIS_PC = (ipaddress.ip_address("127.0.0.1"), ipaddress.ip_address("::1"))
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
        self.token = ""
        self.last = time.monotonic()
        self.lock = threading.Lock()

    def touch(self) -> None:
        self.last = time.monotonic()


STATE = _State()
_OWNER = None


def this_pc_host(host: str) -> bool:
    """localhost, 127.0.0.1, or ::1. ipaddress equality, never a 127. prefix."""
    name = host.lower().rstrip(".")
    if name == "localhost":
        return True
    try:
        return ipaddress.ip_address(name) in _THIS_PC
    except ValueError:
        return False


def _port_ok(port: str) -> bool:
    return port.isascii() and port.isdigit() and 1 <= len(port) <= 5


def host_header_allowed(raw: str | None) -> bool:
    """Host is exactly 127.0.0.1, localhost, or ::1, with an optional port.

    A DNS name such as 127.0.0.1.evil.example is refused. 127.0.0.2 is refused
    too: only those three hosts, not every address in 127.0.0.0/8.
    """
    if raw is None or len(raw) > 255 or "\r" in raw or "\n" in raw:
        return False
    value = raw.strip().lower()
    if not value or any(ch.isspace() for ch in value) or "@" in value or "/" in value:
        return False
    if value.startswith("["):
        end = value.find("]")
        if end < 0:
            return False
        rest = value[end + 1:]
        if rest and not (rest.startswith(":") and _port_ok(rest[1:])):
            return False
        return this_pc_host(value[1:end])
    if ":" in value:
        name, _, port = value.rpartition(":")
        if not _port_ok(port) or ":" in name:
            return False
        return this_pc_host(name)
    return this_pc_host(value)


def _refuse_open_host(handler) -> bool:
    """True when this open route must stop. DNS rebinding sends a foreign Host."""
    if host_header_allowed(handler.headers.get("Host")):
        return False
    handler._send(400, {  # noqa: SLF001 -- the engine handler owns the reply
        "ok": False,
        "reason": HOST_NOT_ALLOWED,
        "error": "this open path refuses that Host",
    })
    return True


def dist_dirs() -> list[Path]:
    """Where /review and /assets/ come from: NOVA_REVIEW_DIST, else the engine's own build (nova_review_build)."""
    return review_build.serving_dirs()


def dist_dir() -> Path:
    found = dist_dirs()
    return found[0] if found else review_build.build_root()


def shot_dir() -> Path:
    raw = os.environ.get("NOVA_REVIEW_SHOT_DIR")
    path = Path(raw) if raw else Path(tempfile.gettempdir()) / "nova-review-shots"
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def _dir_prefix(root: str) -> str:
    return root if root.endswith(os.sep) else root + os.sep


def read_dist_asset(url_path: str) -> tuple[bytes, str] | None:
    """Bytes of one built file, or None when the path leaves dist.

    CodeQL treats ``os.path.realpath`` plus ``startswith`` in this function as the
    jail. The file is opened here, on that checked path. The current build is asked
    first, then the previous one, so a page loaded just before a rebuild keeps its assets.
    """
    rel = unquote(url_path).lstrip("/")
    if not rel or "\x00" in rel or "\\" in rel:
        return None
    parts = [part for part in rel.split("/") if part not in ("", ".")]
    if not parts or any(part == ".." for part in parts):
        return None
    for folder in dist_dirs():
        root = os.path.realpath(folder)
        prefix = _dir_prefix(root)
        full = os.path.realpath(os.path.join(root, *parts))
        if full.startswith(prefix) and os.path.isfile(full):
            with open(full, "rb") as handle:
                return handle.read(), os.path.splitext(full)[1]
    return None


def page_ready() -> dict[str, Any] | None:
    """None when /review can be served; else the error a chart call reports (the build could not be made)."""
    status = review_build.ensure_fresh()
    if dist_dirs():
        return None
    return {"ok": False, "error": {"code": "REVIEW_BUILD_UNAVAILABLE",
                                   "detail": str(status.get("detail") or status.get("state"))}}


def _matching_listener(port: int) -> bool:
    """True when this port already answers as the current review engine."""
    if not port or not review_http.health_ok(port):
        return False
    body = read_health(port)
    if not body:
        return True
    version = body.get("version")
    return version in (None, ENGINE_VERSION)


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
    base = os.path.realpath(dest.parent)
    temp_prefix = _dir_prefix(os.path.realpath(tempfile.gettempdir()))
    full = os.path.realpath(os.path.join(base, os.path.basename(os.fspath(dest))))
    if base.startswith(temp_prefix) and full.startswith(_dir_prefix(base)):
        os.makedirs(base, exist_ok=True)
        with open(full, "wb") as handle:
            handle.write(PNG_STUB)
        return {
            "ok": True,
            "path": full,
            "sha256": hashlib.sha256(PNG_STUB).hexdigest(),
            "bytes": len(PNG_STUB),
            "png": PNG_STUB,
        }
    return {"ok": False, "error": {"code": "REVIEW_SHOT_FAILED", "detail": "shot folder"}}


def _shots() -> review_warm.ReviewShots:
    if STATE.shots is None:
        shoot = _stub_shoot if os.environ.get("NOVA_REVIEW_SHOT") == "stub" else None
        STATE.shots = review_warm.ReviewShots(shoot=shoot)
    return STATE.shots


def take_shot(url: str, dest: Path) -> dict[str, Any]:
    missing = page_ready()
    if missing:
        return missing
    renderer = _shots()
    with STATE.lock:
        if not STATE._counted:
            started = renderer.start()
            if not started.get("ok"):
                return started
            STATE.renderer_starts += 1
            STATE._counted = True
    return renderer.shoot(url, dest)


def request_shot(port: int, fields: dict[str, Any], req_id: str) -> dict[str, Any]:
    import urllib.error
    import urllib.request

    payload = json.dumps({"id": req_id, **fields}).encode()
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/api/review/shot",
        data=payload,
        headers={"Content-Type": "application/json", SHOT_HEADER: review_http.read_token()},
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
    base = os.environ.get("NOVA_REVIEW_BASE", "").strip().rstrip("/")
    return (base,) if base else ()


def make_engine_handler(bars_reader=None, daily_reader=None):
    parent = review_http.make_handler(
        bars_reader or review_load.front_door_bars,
        daily_reader or review_load.front_door_daily,
        _origins(),
    )

    class Handler(parent):
        def _touch(self) -> None:
            STATE.touch()

        def _send_asset(self, url_path: str) -> None:
            found = read_dist_asset(url_path)
            if found is None:
                self._send(404, {"ok": False, "error": "not found"})
                return
            raw, suffix = found
            kind = "application/octet-stream"
            if suffix == ".html":
                kind = "text/html; charset=utf-8"
            elif suffix == ".js":
                kind = "text/javascript; charset=utf-8"
            elif suffix == ".css":
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
                    "build": review_build.last_status(),
                })
                return
            if parsed.path in ("/review", "/review/"):
                missing = page_ready()
                if missing:
                    self._send(503, missing)
                    return
                self._send_asset("/index.html")
                return
            if parsed.path.startswith("/assets/"):
                self._send_asset(parsed.path)
                return
            if parsed.path == "/api/review/open-token" and _refuse_open_host(self):
                return
            super().do_GET()

        def _cors(self) -> None:
            origin = self.headers.get("Origin")
            if not origin:
                return
            cleaned = origin.replace("\r", "").replace("\n", "")
            allowed = set(_origins())
            allowed.add(f"http://127.0.0.1:{self.server.server_address[1]}")
            if cleaned in allowed:
                self.send_header("Access-Control-Allow-Origin", cleaned)
                self.send_header("Vary", "Origin")

        def _token_ok(self) -> bool:
            presented = self.headers.get(SHOT_HEADER) or ""
            expected = STATE.token
            if not expected or not presented:
                return False
            return hmac.compare_digest(presented, expected)

        def _shot_page(self, body: dict[str, Any]) -> tuple[str, str]:
            if "url" in body or "dest" in body:
                raise ValueError("the engine chooses the page and the file")
            session = causal.parse_day(str(body.get("date") or "")).isoformat()
            clock = causal.check_clock(str(body.get("as_of") or causal.DEFAULT_AS_OF))
            origin = f"http://127.0.0.1:{self.server.server_address[1]}"
            if body.get("symbols"):
                names = causal.parse_symbols(body["symbols"])
                gtf = str(body.get("gtf") or "5m")
                return causal.gallery_link(names, session, clock, None, origin, gtf=gtf), "gallery"
            symbol = causal.check_symbol(str(body.get("symbol") or ""))
            return causal.review_link(symbol, session, clock, None, origin), symbol

        def do_POST(self) -> None:  # noqa: N802
            self._touch()
            import nova_review_open as review_open

            if urlparse(self.path).path == review_open.OPEN_PATH and _refuse_open_host(self):
                return
            if review_open.try_post(self):
                return
            parsed = urlparse(self.path)
            if parsed.path != "/api/review/shot":
                self._send(404, {"ok": False, "error": "not found"})
                return
            if self.headers.get("Origin"):
                self._send(403, {"ok": False, "error": "origin"})
                return
            kind = (self.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
            if kind != "application/json":
                self._send(415, {"ok": False, "error": "content type"})
                return
            if not self._token_ok():
                self._send(401, {"ok": False, "error": "token"})
                return
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b""
            try:
                body = json.loads(raw.decode() or "{}")
            except ValueError:
                self._send(400, {"ok": False, "error": "bad json"})
                return
            if not isinstance(body, dict):
                self._send(400, {"ok": False, "error": "bad json"})
                return
            req_id = str(body.get("id") or "")
            try:
                url, label = self._shot_page(body)
                root = os.path.realpath(shot_dir())
                dest_text = os.path.realpath(os.path.join(root, f"review-{label}-{uuid.uuid4().hex[:8]}.png"))
                if not dest_text.startswith(_dir_prefix(root)):
                    raise ValueError("the shot file leaves the review-shots folder")
                dest = Path(dest_text)
            except (ValueError, OSError) as exc:
                self._send(400, {"ok": False, "id": req_id, "error": str(exc)})
                return
            if not req_id:
                self._send(400, {"ok": False, "error": "bad shot"})
                return
            result = take_shot(url, dest)
            answer = {"id": req_id, **result}
            png = answer.get("png")
            if isinstance(png, (bytes, bytearray)):
                answer["png"] = base64.b64encode(bytes(png)).decode("ascii")
            self._send(200 if result.get("ok") else 500, answer)

    return Handler


def serve_engine(port: int, bars_reader=None, daily_reader=None):
    if not STATE.token:
        STATE.token = secrets.token_hex(32)
    if _matching_listener(port):
        return None
    handler = make_engine_handler(bars_reader, daily_reader)
    try:
        httpd = review_http.ReviewHTTPServer(("127.0.0.1", port), handler)
        how = "started"
    except OSError:
        if _matching_listener(port):
            return None
        httpd = review_http.ReviewHTTPServer(("127.0.0.1", 0), handler)
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
        review_http._write_lease(int(httpd.server_address[1]), STATE.token)
    threading.Thread(target=_watch_idle, args=(httpd,), name="nova-review-idle", daemon=True).start()
    threading.Thread(target=review_build.ensure_fresh, name="nova-review-build", daemon=True).start()

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
