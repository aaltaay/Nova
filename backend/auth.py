"""API-key guard for mutating Nova HTTP routes (SEC-002 / SEC-004).

Local loopback with no ``NOVA_API_KEY`` stays open for single-operator desktop.
Public binds (``0.0.0.0`` / non-loopback) require ``NOVA_API_KEY``. When the key
is set, every mutating ``/api/*`` request must send ``X-Nova-Api-Key``.
"""
from __future__ import annotations

import hmac
import logging
import os
from typing import Annotated

from fastapi import HTTPException, Request, Security
from fastapi.security import APIKeyHeader
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

from constants import NOVA_API_KEY_HEADER, NOVA_API_LOOPBACK_HOSTS

logger = logging.getLogger(__name__)

_api_key_header = APIKeyHeader(name=NOVA_API_KEY_HEADER, auto_error=False)

_MUTATING = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def _configured_api_key() -> str:
    return (os.environ.get("NOVA_API_KEY") or "").strip()


def _bind_host() -> str:
    return (os.environ.get("NOVA_API_HOST") or "127.0.0.1").strip().lower()


def _is_loopback_bind() -> bool:
    host = _bind_host()
    if host in NOVA_API_LOOPBACK_HOSTS:
        return True
    # IPv6 / atypical localhost forms
    return host.startswith("127.") or host == "::1"


def check_api_key(provided: str | None) -> tuple[int, str] | None:
    """Return ``(status, detail)`` if rejected, else ``None``."""
    expected = _configured_api_key()
    if not expected:
        if _is_loopback_bind():
            return None
        return (
            503,
            "NOVA_API_KEY must be set when the API bind host is not loopback",
        )
    got = (provided or "").strip()
    if not got or not hmac.compare_digest(got, expected):
        return (401, f"Invalid or missing {NOVA_API_KEY_HEADER}")
    return None


async def require_auth(
    api_key: Annotated[str | None, Security(_api_key_header)] = None,
) -> None:
    """FastAPI Depends / Security guard used on sensitive routers."""
    rejected = check_api_key(api_key)
    if rejected is not None:
        status, detail = rejected
        raise HTTPException(status_code=status, detail=detail)


class MutatingApiKeyMiddleware(BaseHTTPMiddleware):
    """Enforce API key on mutating ``/api/*`` HTTP methods (not WebSockets)."""

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.method in _MUTATING and request.url.path.startswith("/api/"):
            rejected = check_api_key(request.headers.get(NOVA_API_KEY_HEADER))
            if rejected is not None:
                status, detail = rejected
                return JSONResponse(status_code=status, content={"detail": detail})
        return await call_next(request)


def configure_api_auth(app) -> None:
    """Register mutating-route API-key middleware (call from app factory)."""
    app.add_middleware(MutatingApiKeyMiddleware)
    if _configured_api_key():
        logger.info("API auth: NOVA_API_KEY set — mutating /api/* requires %s", NOVA_API_KEY_HEADER)
    elif _is_loopback_bind():
        logger.info(
            "API auth: NOVA_API_KEY unset on loopback bind (%s) — mutating routes open locally",
            _bind_host(),
        )
    else:
        logger.warning(
            "API auth: NOVA_API_KEY unset and bind host %s is not loopback — "
            "mutating /api/* will return 503 until NOVA_API_KEY is configured",
            _bind_host(),
        )


# Re-export for Depends(require_auth) static discovery
__all__ = [
    "MutatingApiKeyMiddleware",
    "check_api_key",
    "configure_api_auth",
    "require_auth",
]
