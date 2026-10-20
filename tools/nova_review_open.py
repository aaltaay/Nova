"""Same-origin open path for the /review page.

The page asks this listener. The listener asks the Nova API. The answer has no
``Access-Control-Allow-Origin``, so another origin cannot read the install token.
The API key is never on this path.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlparse

from nova_open_client import DESK_NOT_RUNNING_TEXT, DESK_OUT_OF_DATE_TEXT, HEADER

TOKEN_PATH = "/api/review/open-token"
OPEN_PATH = "/api/review/open-in-nova"


def foreign_origin(origin: str | None) -> bool:
    """Loopback, no Origin, and file:// are this PC. A 127. prefix is not loopback."""
    if origin is None or origin == "" or origin == "file://":
        return False
    if origin == "null" or "\r" in origin or "\n" in origin:
        return True
    parsed = urlparse(origin)
    if parsed.scheme not in {"http", "https"} or parsed.username is not None or parsed.password is not None:
        return True
    host = parsed.hostname
    if not host:
        return True
    import nova_review_engine as engine

    return not engine.this_pc_host(host)


def _host_refused(handler) -> bool:
    import nova_review_engine as engine

    if engine.host_header_allowed(handler.headers.get("Host")):
        return False
    _send(handler, 400, {
        "ok": False,
        "reason": engine.HOST_NOT_ALLOWED,
        "error": "this open path refuses that Host",
    })
    return True


def try_get(handler) -> bool:
    if urlparse(handler.path).path != TOKEN_PATH:
        return False
    _send_token(handler)
    return True


def try_post(handler) -> bool:
    if urlparse(handler.path).path != OPEN_PATH:
        return False
    _forward_open(handler)
    return True


def _send_token(handler) -> None:
    if _host_refused(handler):
        return
    if foreign_origin(handler.headers.get("Origin")):
        _send(handler, 403, {"reason": "FORBIDDEN", "error": "this open path refuses a foreign Origin"})
        return
    try:
        status, body = _call("GET", "/api/agent/open-token", None, None)
    except OSError:
        _send(handler, 409, {"reason": "DESK_NOT_RUNNING", "error": DESK_NOT_RUNNING_TEXT})
        return
    if status == 404:
        _send(handler, 409, {"reason": "DESK_OUT_OF_DATE", "error": DESK_OUT_OF_DATE_TEXT})
        return
    if not isinstance(body, dict) or "token" not in body:
        _send(handler, 409, {"reason": "DESK_NOT_RUNNING", "error": DESK_NOT_RUNNING_TEXT})
        return
    _send(handler, status, {"schema_version": body.get("schema_version"), "token": body.get("token")})


def _forward_open(handler) -> None:
    if _host_refused(handler):
        return
    if foreign_origin(handler.headers.get("Origin")):
        _send(handler, 403, {"reason": "FORBIDDEN", "error": "this open path refuses a foreign Origin"})
        return
    ctype = (handler.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
    if ctype != "application/json":
        _send(handler, 415, {"reason": "BAD_REQUEST", "error": "Content-Type must be application/json"})
        return
    length = int(handler.headers.get("Content-Length") or "0")
    raw = handler.rfile.read(length) if length else b""
    token = handler.headers.get(HEADER) or ""
    try:
        status, body = _call("POST", "/api/agent/open-in-nova", raw, token)
    except OSError:
        _send(handler, 409, {"reason": "DESK_NOT_RUNNING", "error": DESK_NOT_RUNNING_TEXT})
        return
    if status == 404:
        _send(handler, 409, {"reason": "DESK_OUT_OF_DATE", "error": DESK_OUT_OF_DATE_TEXT})
        return
    if not isinstance(body, dict):
        _send(handler, 502, {"reason": "BAD_REQUEST", "error": "the desk answer was not JSON"})
        return
    _send(handler, status, body)


def _call(method: str, path: str, raw: bytes | None, token: str | None) -> tuple[int, Any]:
    root = (os.environ.get("NOVA_API_BASE") or "http://127.0.0.1:8000").rstrip("/")
    headers = {}
    data = None
    if method == "POST":
        headers["Content-Type"] = "application/json"
        headers[HEADER] = token or ""
        data = raw or b""
    request = urllib.request.Request(root + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = response.read()
            status = int(response.status)
    except urllib.error.HTTPError as exc:
        payload = exc.read()
        status = int(exc.code)
    return status, json.loads(payload.decode("utf-8") or "null")


def _send(handler, status: int, body: dict[str, Any]) -> None:
    raw = json.dumps(body).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(raw)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(raw)
