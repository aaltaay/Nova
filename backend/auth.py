"""API-key guard for mutating Nova HTTP routes (SEC-002 / SEC-004 / D-040).

Local loopback with no ``NOVA_API_KEY`` stays open for most mutating routes
(single-operator desktop). Public binds require a key.

``POST /api/config``, ``POST /api/issues`` and mutating ``/api/bot/*`` / ``/bot/*`` always require
a configured ``NOVA_API_KEY`` and a matching ``X-Nova-Api-Key`` header, even
on loopback. Any local process can reach ``127.0.0.1:8000``. The Desktop
sidecar reads the same ``NOVA_API_KEY`` the API already uses (repo
``.env``, ``NOVA_ENV_PATH``, or userData ``.env``) and injects it on
``novaDesktop.apiKey``. Vite serve maps that repo key onto
``VITE_NOVA_API_KEY``. Settings can still save ``localStorage.nova_api_key``.
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

from constants import (
    NOVA_API_KEY_HEADER,
    NOVA_API_LOOPBACK_HOSTS,
    NOVA_CONFIG_MUTATE_PATH,
)

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


def is_config_mutate(method: str, path: str) -> bool:
    return method in _MUTATING and path.rstrip("/") == NOVA_CONFIG_MUTATE_PATH


def is_bot_http_path(path: str) -> bool:
    normalized = path.rstrip("/") or "/"
    return normalized.startswith("/api/bot") or normalized.startswith("/bot")


def is_bot_mutate(method: str, path: str) -> bool:
    return method in _MUTATING and is_bot_http_path(path)


def is_setup_template_mutate(method: str, path: str) -> bool:
    """A template sets what the bot may enter at Strategy (ADR 029): keyed like a bot route."""
    normalized = path.rstrip("/") or "/"
    return method in _MUTATING and normalized.startswith("/api/setups/templates")


def is_issue_report_mutate(method: str, path: str) -> bool:
    """Filing an issue publishes on a public repository as the operator: keyed like a bot route."""
    normalized = path.rstrip("/") or "/"
    return method in _MUTATING and (normalized == "/api/issues" or normalized.startswith("/api/issues/"))


def is_stock_mode_mutate(method: str, path: str) -> bool:
    """The per-stock switch lets Nova place and cancel orders (ADR 037): keyed like a bot route."""
    normalized = path.rstrip("/") or "/"
    return method in _MUTATING and (normalized == "/api/stock-mode" or normalized.startswith("/api/stock-mode/"))


def is_sensor_http_path(path: str) -> bool:
    normalized = path.rstrip("/") or "/"
    return normalized == "/sensors" or normalized.startswith("/sensors/")


def is_sensor_mutate(method: str, path: str) -> bool:
    return method in _MUTATING and is_sensor_http_path(path)


_BOT_KEY_REQUIRED = (
    "NOVA_API_KEY must be set for mutating bot routes, including on loopback"
)
_ISSUE_KEY_REQUIRED = (
    "NOVA_API_KEY must be set to file an issue from the desk, including on loopback"
)


def check_api_key(
    provided: str | None,
    *,
    require_configured_key: bool = False,
    missing_key_detail: str | None = None,
) -> tuple[int, str] | None:
    """Return ``(status, detail)`` if rejected, else ``None``."""
    expected = _configured_api_key()
    if not expected:
        if require_configured_key:
            return (
                503,
                missing_key_detail
                or "NOVA_API_KEY must be set to change config, including on loopback",
            )
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


async def require_bot_auth(
    api_key: Annotated[str | None, Security(_api_key_header)] = None,
) -> None:
    """Mutating bot routes -- always require a configured API key."""
    rejected = check_api_key(
        api_key,
        require_configured_key=True,
        missing_key_detail=_BOT_KEY_REQUIRED,
    )
    if rejected is not None:
        status, detail = rejected
        raise HTTPException(status_code=status, detail=detail)


class MutatingApiKeyMiddleware(BaseHTTPMiddleware):
    """Enforce API key on mutating ``/api/*``, ``/bot/*``, and ``/sensors/*``."""

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        mutating = request.method in _MUTATING
        bot = (is_bot_mutate(request.method, path) or is_setup_template_mutate(request.method, path)
               or is_stock_mode_mutate(request.method, path))
        issue = is_issue_report_mutate(request.method, path)
        api = path.startswith("/api/")
        sensors = is_sensor_mutate(request.method, path)
        if mutating and (bot or api or sensors):
            rejected = check_api_key(
                request.headers.get(NOVA_API_KEY_HEADER),
                require_configured_key=is_config_mutate(request.method, path) or bot or issue,
                missing_key_detail=_BOT_KEY_REQUIRED if bot else (_ISSUE_KEY_REQUIRED if issue else None),
            )
            if rejected is not None:
                status, detail = rejected
                return JSONResponse(status_code=status, content={"detail": detail})
        return await call_next(request)


def configure_api_auth(app) -> None:
    """Register mutating-route API-key middleware (call from app factory)."""
    app.add_middleware(MutatingApiKeyMiddleware)
    if _configured_api_key():
        logger.info(
            "API auth: mutating-route key configured -- mutating /api/* requires %s",
            NOVA_API_KEY_HEADER,
        )
    elif _is_loopback_bind():
        logger.info(
            "API auth: mutating-route key unset on loopback bind (%s) -- "
            "mutating routes open locally except %s and mutating bot routes (require a key)",
            _bind_host(),
            NOVA_CONFIG_MUTATE_PATH,
        )
    else:
        logger.warning(
            "API auth: mutating-route key unset and bind host %s is not loopback -- "
            "mutating /api/* will return 503 until a key is configured",
            _bind_host(),
        )


# Re-export for Depends(require_auth) static discovery
__all__ = [
    "MutatingApiKeyMiddleware",
    "check_api_key",
    "configure_api_auth",
    "is_bot_http_path",
    "is_bot_mutate",
    "is_config_mutate",
    "is_issue_report_mutate",
    "is_sensor_http_path",
    "is_sensor_mutate",
    "is_setup_template_mutate",
    "require_auth",
    "require_bot_auth",
]
