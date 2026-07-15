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

    logger.warning(
        "client_error source=%s msg=%s url=%s ua=%s stack=%s component=%s",
        body.source,
        (body.message or "")[:CLIENT_ERRORS_MAX_MESSAGE_CHARS],
        (body.url or "")[:200],
        (body.user_agent or "")[:120],
        (body.stack or "")[:400],
        (body.component_stack or "")[:400],
    )
    return {"ok": True}
