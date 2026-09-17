"""Shared HTTP helpers for bot routes."""
from __future__ import annotations

from fastapi import HTTPException, Request

from bot.errors import BotError
from constants_bot import (
    BOT_DESK_ARM_HEADER,
    BOT_LOOPBACK_HOSTS,
    BOT_REASON_NOT_LOOPBACK,
)


def require_loopback(request: Request) -> None:
    host = ""
    if request.client is not None:
        host = (request.client.host or "").strip().lower()
    if host in BOT_LOOPBACK_HOSTS or host.startswith("127."):
        return
    raise HTTPException(
        status_code=403,
        detail={"reason": BOT_REASON_NOT_LOOPBACK, "error": "bot API is localhost only"},
    )


def desk_arm_token(request: Request, body: dict | None = None) -> str | None:
    header = (request.headers.get(BOT_DESK_ARM_HEADER) or "").strip()
    if header:
        return header
    if body and body.get("desk_arm_token"):
        return str(body["desk_arm_token"]).strip()
    return None


def brain_id(request: Request, body: dict | None = None) -> str | None:
    header = (request.headers.get("x-nova-brain-session") or "").strip()
    if header:
        return header
    if body and body.get("brain_session_id"):
        return str(body["brain_session_id"]).strip()
    return None


def http_error(exc: BotError) -> HTTPException:
    return HTTPException(
        status_code=exc.status_code,
        detail={"reason": exc.reason, "error": exc.message},
    )
