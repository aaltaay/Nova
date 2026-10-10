"""The guard as pure ASGI middleware, for HTTP requests and WebSocket handshakes alike.

Not a ``BaseHTTPMiddleware``: those never see a websocket scope. Not Starlette's
``TrustedHostMiddleware`` either: it splits ``[::1]:8000`` at the first colon,
compares case-sensitively, keeps a trailing dot and has no Origin check.
"""
from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from datetime import datetime

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send
from starlette.websockets import WebSocketClose

from request_guard.constants_request_guard import (
    HOST_REFUSED_DETAIL,
    HOST_REFUSED_STATUS,
    LOGGED_VALUE_MAX_CHARS,
    ORIGIN_REFUSED_DETAIL,
    REASON_HOST_NOT_ALLOWED,
    REFUSAL_LOG_KEYS_MAX,
    REFUSAL_LOG_WINDOW_SEC,
    WS_CLOSE_REASON_HOST,
    WS_CLOSE_REASON_ORIGIN,
    WS_POLICY_VIOLATION,
    WS_REFUSED_HTTP_STATUS,
)
from request_guard.policy import GuardPolicy, Refusal, check_request

logger = logging.getLogger(__name__)

_GUARDED_SCOPES = ("http", "websocket")
_WS_DENIAL_EXTENSION = "websocket.http.response"


class RefusalLog:
    """One WARNING per refused (kind, header, value) per window, so a page or a
    reconnect loop cannot flood the log; the next line counts the ones between."""

    def __init__(
        self,
        window_sec: float = REFUSAL_LOG_WINDOW_SEC,
        keys_max: int = REFUSAL_LOG_KEYS_MAX,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._window = window_sec
        self._keys_max = keys_max
        self._clock = clock
        # key -> [monotonic time logged, wall time logged, refusals since then not logged]
        self._seen: dict[tuple[str, str, str], list] = {}
        self._lock = threading.Lock()

    def note(self, kind: str, path: str, refusal: Refusal) -> None:
        value = refusal.value[:LOGGED_VALUE_MAX_CHARS]
        key = (kind, refusal.header, value)
        now = self._clock()
        with self._lock:
            entry = self._seen.get(key)
            if entry is not None and now - entry[0] < self._window:
                entry[2] += 1
                return
            if entry is None and len(self._seen) >= self._keys_max:
                self._seen.clear()
            suffix = ""
            if entry is not None and entry[2]:
                suffix = f"; {entry[2]} more since {entry[1]:%H:%M:%S}"
            self._seen[key] = [now, datetime.now(), 0]
        logger.warning(
            "request guard: refused %s %r -- %s %r is not allowed%s",
            kind, path[:LOGGED_VALUE_MAX_CHARS], refusal.header, value, suffix,
        )


def _hosts_and_origins(scope: Scope) -> tuple[list[str], list[str]]:
    """Every Host and Origin value sent (ASGI header names arrive lowercased)."""
    hosts: list[str] = []
    origins: list[str] = []
    for name, value in scope.get("headers") or ():
        if name == b"host":
            hosts.append(value.decode("latin-1"))
        elif name == b"origin":
            origins.append(value.decode("latin-1"))
    return hosts, origins


async def _refuse(scope: Scope, receive: Receive, send: Send, refusal: Refusal) -> None:
    host = refusal.reason == REASON_HOST_NOT_ALLOWED
    body = {"detail": HOST_REFUSED_DETAIL if host else ORIGIN_REFUSED_DETAIL, "reason": refusal.reason}
    if scope["type"] == "http":
        await JSONResponse(body, status_code=HOST_REFUSED_STATUS)(scope, receive, send)
        return
    if _WS_DENIAL_EXTENSION in (scope.get("extensions") or {}):
        # The handshake gets an HTTP answer a non-browser client can read; a browser sees close 1006.
        await JSONResponse(body, status_code=WS_REFUSED_HTTP_STATUS)(scope, receive, send)
        return
    reason = WS_CLOSE_REASON_HOST if host else WS_CLOSE_REASON_ORIGIN
    await WebSocketClose(code=WS_POLICY_VIOLATION, reason=reason)(scope, receive, send)


class RequestGuardMiddleware:
    """Refuse a request whose Host is not one of the API's names, and a socket from a foreign page."""

    def __init__(self, app: ASGIApp, policy: GuardPolicy) -> None:
        self.app = app
        self.policy = policy
        self.refusals = RefusalLog()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        kind = scope["type"]
        if kind not in _GUARDED_SCOPES:
            await self.app(scope, receive, send)
            return
        hosts, origins = _hosts_and_origins(scope)
        refusal = check_request(self.policy, kind, hosts, origins)
        if refusal is None:
            await self.app(scope, receive, send)
            return
        self.refusals.note(kind, scope.get("path", ""), refusal)
        await _refuse(scope, receive, send, refusal)
