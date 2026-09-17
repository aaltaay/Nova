"""Localhost bot HTTP API (ADR 016). Thin handlers -- logic lives in bot/."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from auth import require_auth
from bot.advise_guard import latest as advise_latest
from bot.advise_guard import start as advise_start
from bot.audit import list_entries
from bot.autonomy import apply_patch
from bot.day_pnl import read_account_day_pnl
from bot.errors import BotError
from bot.focus import add_focus, set_focus, snapshot as focus_snapshot
from bot.focus import sync_trader_live
from bot.http import brain_id, http_error, require_loopback
from bot.proposals import accept, list_proposals, reject, submit
from bot.session import get_session, require_l2_brain

router = APIRouter(tags=["bot"], dependencies=[Depends(require_loopback)])


class SessionPatch(BaseModel):
    level: int | None = Field(default=None, ge=0, le=3)
    armed: bool | None = None
    strategy: str | None = None
    caps: dict[str, Any] | None = None
    advise: dict[str, Any] | None = None
    reenable: bool | None = None
    brain_session_id: str | None = None


class ActionBody(BaseModel):
    kind: str | None = None
    action: str | None = None
    symbol: str
    brain_session_id: str | None = None
    idempotency_key: str | None = None
    percent: int | None = None
    qty: float | None = None
    shares: float | None = None
    offset_dollars: float | None = None


class ProposalBody(BaseModel):
    symbol: str
    side: str
    kind: str | None = None
    action: str | None = None
    shortcut: str | None = None
    reason: str
    confidence: float | None = Field(default=None, ge=0, le=1)
    brain_session_id: str | None = None
    qty: float | None = None
    shares: float | None = None


class FocusBody(BaseModel):
    symbol: str | None = None
    symbols: list[str] | None = None


class LiveSyncBody(BaseModel):
    live: list[str]


class AdviseBody(BaseModel):
    symbol: str
    depth: int | None = None
    force_refresh: bool = False


def _session_get() -> dict:
    return get_session()


@router.get("/api/bot/session")
@router.get("/bot/session")
def bot_session() -> dict:
    return _session_get()


@router.patch("/api/bot/session", dependencies=[Depends(require_auth)])
@router.patch("/bot/session", dependencies=[Depends(require_auth)])
def bot_session_patch(body: SessionPatch) -> dict:
    try:
        apply_patch(body.model_dump(exclude_none=True), desk=True)
        return get_session()
    except BotError as exc:
        raise http_error(exc) from exc


@router.post("/api/bot/session/claim", dependencies=[Depends(require_auth)])
@router.post("/bot/session/claim", dependencies=[Depends(require_auth)])
def bot_claim(request: Request, body: SessionPatch | None = None) -> dict:
    try:
        payload = body.model_dump(exclude_none=True) if body else {}
        require_l2_brain(brain_id(request, payload), claim=True)
        return get_session()
    except BotError as exc:
        raise http_error(exc) from exc


@router.post("/api/bot/action", dependencies=[Depends(require_auth)])
@router.post("/bot/action", dependencies=[Depends(require_auth)])
async def bot_action(request: Request, body: ActionBody) -> dict:
    from bot.actions import fire

    payload = body.model_dump(exclude_none=True)
    try:
        return await fire(payload, brain_session_id=brain_id(request, payload))
    except BotError as exc:
        raise http_error(exc) from exc


@router.get("/api/bot/proposals")
@router.get("/bot/proposals")
def bot_proposals() -> dict:
    return {"proposals": list_proposals()}


@router.post("/api/bot/proposals", dependencies=[Depends(require_auth)])
@router.post("/bot/proposals", dependencies=[Depends(require_auth)])
def bot_propose(request: Request, body: ProposalBody) -> dict:
    payload = body.model_dump(exclude_none=True)
    try:
        return submit(payload, brain_session_id=brain_id(request, payload))
    except BotError as exc:
        raise http_error(exc) from exc


@router.post("/api/bot/proposals/{proposal_id}/accept", dependencies=[Depends(require_auth)])
@router.post("/bot/proposals/{proposal_id}/accept", dependencies=[Depends(require_auth)])
def bot_accept(proposal_id: str) -> dict:
    try:
        return accept(proposal_id)
    except BotError as exc:
        raise http_error(exc) from exc


@router.post("/api/bot/proposals/{proposal_id}/reject", dependencies=[Depends(require_auth)])
@router.post("/bot/proposals/{proposal_id}/reject", dependencies=[Depends(require_auth)])
def bot_reject(proposal_id: str) -> dict:
    try:
        return reject(proposal_id)
    except BotError as exc:
        raise http_error(exc) from exc


@router.get("/api/bot/focus")
@router.get("/bot/focus")
def bot_focus() -> dict:
    return focus_snapshot()


@router.post("/api/bot/focus", dependencies=[Depends(require_auth)])
@router.post("/bot/focus", dependencies=[Depends(require_auth)])
def bot_focus_set(body: FocusBody) -> dict:
    try:
        if body.symbols is not None:
            return set_focus(body.symbols)
        if body.symbol:
            return add_focus(body.symbol)
        return focus_snapshot()
    except BotError as exc:
        raise http_error(exc) from exc


@router.post("/api/bot/focus/sync")
@router.post("/bot/focus/sync")
def bot_focus_sync(body: LiveSyncBody) -> dict:
    return sync_trader_live(body.live)


@router.get("/api/bot/advise/latest")
@router.get("/bot/advise/latest")
def bot_advise_latest(symbol: str, depth: int | None = None) -> dict:
    try:
        return {"run": advise_latest(symbol, depth)}
    except BotError as exc:
        raise http_error(exc) from exc


@router.post("/api/bot/advise", dependencies=[Depends(require_auth)])
@router.post("/bot/advise", dependencies=[Depends(require_auth)])
async def bot_advise(body: AdviseBody) -> dict:
    try:
        return await advise_start(body.symbol, body.depth, force_refresh=body.force_refresh)
    except BotError as exc:
        raise http_error(exc) from exc


@router.get("/api/bot/audit")
@router.get("/bot/audit")
def bot_audit(limit: int = 200) -> dict:
    return {"entries": list_entries(limit=limit)}


@router.get("/api/bot/pnl")
@router.get("/bot/pnl")
def bot_pnl() -> dict:
    pnl, meter = read_account_day_pnl()
    return {"day_pnl": pnl, "meter": meter}
