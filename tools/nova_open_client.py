"""Ask the running Nova API to open a ticker. The MCP process does not move its own clock.

The API owns the install token (``GET /api/agent/open-token``). This client never sends ``X-Nova-Api-Key``.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

DESK_NOT_RUNNING_TEXT = (
    "Nova's desk is not running. Start it with scripts/windows/Run Nova Desktop.bat, then ask again."
)
HEADER = "X-Nova-Open-Token"
DEFAULT_API = "http://127.0.0.1:8000"


def api_base() -> str:
    return (os.environ.get("NOVA_API_BASE") or DEFAULT_API).rstrip("/")


def post_open(payload: dict[str, Any], *, base: str | None = None, urlopen=urllib.request.urlopen) -> dict[str, Any]:
    root = (base or api_base()).rstrip("/")
    try:
        token = _read_token(root, urlopen)
        status, body = _request(
            urlopen,
            urllib.request.Request(
                root + "/api/agent/open-in-nova",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json", HEADER: token},
                method="POST",
            ),
        )
    except OSError:
        return {"ok": False, "reason": "DESK_NOT_RUNNING", "error": DESK_NOT_RUNNING_TEXT}
    if status < 400 and isinstance(body, dict) and body.get("ok") is True:
        return body
    return _error_body(body)


def _read_token(root: str, urlopen) -> str:
    _status, body = _request(urlopen, urllib.request.Request(root + "/api/agent/open-token"))
    token = body.get("token") if isinstance(body, dict) else None
    if not isinstance(token, str) or not token:
        raise OSError("open token missing")
    return token


def _request(urlopen, request: urllib.request.Request) -> tuple[int, Any]:
    try:
        with urlopen(request, timeout=30) as response:
            raw = response.read()
            status = int(response.status)
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        status = int(exc.code)
    try:
        body = json.loads(raw.decode("utf-8") or "null")
    except (UnicodeDecodeError, json.JSONDecodeError):
        body = {"error": raw.decode("utf-8", errors="replace")}
    return status, body


def _error_body(body: Any) -> dict[str, Any]:
    detail = body.get("detail") if isinstance(body, dict) else None
    if isinstance(detail, dict):
        return {"ok": False, "reason": str(detail.get("reason") or "BAD_REQUEST"), "error": str(detail.get("error") or "")}
    if isinstance(body, dict):
        return {"ok": False, "reason": str(body.get("reason") or "BAD_REQUEST"), "error": str(body.get("error") or "")}
    return {"ok": False, "reason": "BAD_REQUEST", "error": "the desk refused the open"}
