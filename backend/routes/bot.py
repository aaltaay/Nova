"""Localhost bot HTTP API (ADR 016). Thin handlers -- logic lives in bot/.

ADR 072: the bots are retired. What stays is the bot API's door (``/api/bot/action`` with its session claim and
heartbeat), which becomes the brain's -- until then nothing opens it (``bot.door``: Activate is gone) and the
execution door refuses its sends in words (``execution.retired_senders``) -- and the bot audit stream, read-only
history -- and ``PATCH /api/bot/session {caps}``, your risk per trade that Stage sizes by (``bot.caps``). The Bot
switch, the family keys, Activate, the levels, the allowlist, proposals, focus, the day P&L meter and the squares are
gone with the Bots page.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from auth import require_bot_auth
from bot.api_models import ActionBody, CapsPatch, ClaimBody, HeartbeatBody
from bot.arming import record_heartbeat
from bot.audit import list_entries
from bot.errors import BotError
from bot.http import brain_id, http_error, require_loopback
from bot.persist import load_session
from bot.session import get_session, require_l2_brain
from bot.watch import halt_watch

router = APIRouter(tags=["bot"], dependencies=[Depends(require_loopback)])
_write = [Depends(require_bot_auth)]


@router.get("/api/bot/session")
@router.get("/bot/session")
def bot_session() -> dict:
    return get_session()


@router.patch("/api/bot/session", dependencies=_write)
@router.patch("/bot/session", dependencies=_write)
def bot_session_caps(request: Request, body: CapsPatch) -> dict:
    """Your risk per trade on a venue (``bot.caps``): the only write left on the session. The desk's alone."""
    from bot.caps import apply as apply_caps
    from constants_bot import BOT_REASON_CAPS_DESK_ONLY

    payload = body.model_dump(exclude_none=True)
    if brain_id(request, payload):
        raise http_error(BotError("a brain cannot set the risk per trade -- the desk does", 403,
                                  BOT_REASON_CAPS_DESK_ONLY))
    payload.pop("brain_session_id", None)
    try:
        apply_caps(payload)
    except BotError as exc:
        raise http_error(exc) from exc
    return get_session()


@router.post("/api/bot/session/heartbeat", dependencies=_write)
@router.post("/bot/session/heartbeat", dependencies=_write)
def bot_heartbeat(request: Request, body: HeartbeatBody | None = None) -> dict:
    payload = body.model_dump(exclude_none=True) if body else {}
    try:
        record_heartbeat(brain_id(request, payload))
        return get_session()
    except BotError as exc:
        raise http_error(exc) from exc


@router.post("/api/bot/session/claim", dependencies=_write)
@router.post("/bot/session/claim", dependencies=_write)
def bot_claim(request: Request, body: ClaimBody | None = None) -> dict:
    payload = body.model_dump(exclude_none=True) if body else {}
    try:
        require_l2_brain(brain_id(request, payload), claim=True)
        return get_session()
    except BotError as exc:
        raise http_error(exc) from exc


@router.get("/api/bot/watch")
@router.get("/bot/watch")
def bot_watch() -> dict:
    return halt_watch(load_session())


@router.post("/api/bot/action", dependencies=_write)
@router.post("/bot/action", dependencies=_write)
async def bot_action(request: Request, body: ActionBody) -> dict:
    from bot.actions import fire

    payload = body.model_dump(exclude_none=True)
    try:
        return await fire(payload, brain_session_id=brain_id(request, payload))
    except BotError as exc:
        raise http_error(exc) from exc


@router.get("/api/bot/audit")
@router.get("/bot/audit")
def bot_audit(limit: int = 200) -> dict:
    return {"entries": list_entries(limit=limit)}
