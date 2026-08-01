"""
Browser client-error intake — structured log only (no secrets).

POST /api/client-errors
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from constants import (
    CLIENT_ERRORS_ENABLED,
    CLIENT_ERRORS_MAX_BODY_BYTES,
    CLIENT_ERRORS_MAX_MESSAGE_CHARS,
)

router = APIRouter(tags=["observability"])
logger = logging.getLogger("nova.client_errors")


def _is_dev_tooling_noise(message: str, stack: str | None) -> bool:
    """Drop known browser/dev noise — not product bugs (keeps Sentry quiet).

    Includes Vite HMR WS races and TradingView ``Object is disposed`` on
    chart unmount/HMR (PYTHON-FASTAPI-2B).
    """
    msg = (message or "").strip()
    msg_l = msg.lower()
    stk = stack or ""
    if "@vite/client" in stk or "/@vite/client" in stk:
        return True
    if msg == "send was called before connect":
        return True
    if "reading 'send'" in msg and "vite" in stk.lower():
        return True
    # LightweightCharts / TradingView dispose races during unmount or HMR.
    if "object is disposed" in msg_l:
        return True
    return False


def _is_provider_shell_noise(message: str) -> bool:
    """React provider/HMR shell races — local log only, not Sentry error Issues."""
    return "must be used within" in (message or "").lower()


class ClientErrorBody(BaseModel):
    message: str = Field(default="", max_length=CLIENT_ERRORS_MAX_MESSAGE_CHARS)
    stack: str | None = Field(default=None, max_length=CLIENT_ERRORS_MAX_MESSAGE_CHARS)
    component_stack: str | None = Field(default=None, max_length=CLIENT_ERRORS_MAX_MESSAGE_CHARS)
    source: str = Field(default="unknown", max_length=64)
    url: str | None = Field(default=None, max_length=512)
    user_agent: str | None = Field(default=None, max_length=512)
    ts: float | None = None


@router.post("/api/client-errors")
async def post_client_error(request: Request, body: ClientErrorBody):
    """Accept a browser error report and write one structured warning line."""
    if not CLIENT_ERRORS_ENABLED:
        return {"ok": False, "disabled": True}

    raw_len = int(request.headers.get("content-length") or 0)
    if raw_len > CLIENT_ERRORS_MAX_BODY_BYTES:
        return {"ok": False, "error": "payload_too_large"}

    if _is_dev_tooling_noise(body.message or "", body.stack):
        return {"ok": True, "ignored": True, "reason": "dev_tooling_noise"}

    if _is_provider_shell_noise(body.message or ""):
        logger.warning(
            "client_error_shell source=%s msg=%s url=%s",
            body.source,
            (body.message or "")[:CLIENT_ERRORS_MAX_MESSAGE_CHARS],
            (body.url or "")[:200],
        )
        return {"ok": True, "ignored": True, "reason": "provider_shell_noise"}

    logger.warning(
        "client_error source=%s msg=%s url=%s ua=%s stack=%s component=%s",
        body.source,
        (body.message or "")[:CLIENT_ERRORS_MAX_MESSAGE_CHARS],
        (body.url or "")[:200],
        (body.user_agent or "")[:120],
        (body.stack or "")[:400],
        (body.component_stack or "")[:400],
    )

    # Mirror into Sentry when SENTRY_DSN is configured (init in app_lifespan).
    try:
        import sentry_sdk

        if sentry_sdk.is_initialized():
            msg = (body.message or "client_error")[:CLIENT_ERRORS_MAX_MESSAGE_CHARS]
            source = body.source or "unknown"
            with sentry_sdk.push_scope() as scope:
                scope.set_tag("source", source)
                scope.set_extra("url", body.url)
                scope.set_extra("user_agent", body.user_agent)
                scope.set_extra("stack", (body.stack or "")[:800])
                scope.set_extra("component_stack", (body.component_stack or "")[:800])
                scope.fingerprint = ["client-error", source, msg[:120]]
                sentry_sdk.capture_message(msg, level="error")
    except Exception:
        logger.debug("Sentry client_error mirror skipped", exc_info=True)

    return {"ok": True}
