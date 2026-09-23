"""Localhost bot HTTP API (ADR 016). Thin handlers -- logic lives in bot/."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from auth import require_bot_auth
from bot.advise_guard import latest as advise_latest
from bot.advise_guard import start as advise_start
from bot.api_models import (
    ActionBody,
    AdviseBody,
    AllowlistBody,
    ArmBody,
    FocusBody,
    HeartbeatBody,
    LiveSyncBody,
    ProposalBody,
    SessionPatch,
)
from bot.arming import (
    assert_desk_activate,
    disarm_session,
    issue_arm_token,
    record_heartbeat,
)
from bot.audit import list_entries
from bot.audit import record as audit_record
from bot.autonomy import apply_patch
from bot.day_pnl import read_account_day_pnl
from bot.eligibility import add_symbol, remove_symbol
from bot.errors import BotError
from bot.focus import add_focus, set_focus, snapshot as focus_snapshot
from bot.focus import sync_trader_live
from bot.gates import assert_can_activate
from bot.http import brain_id, desk_arm_token, http_error, require_loopback
from bot.persist import load_session, save_session
from bot.proposals import accept, list_proposals, reject, submit
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
def bot_session_patch(request: Request, body: SessionPatch) -> dict:
    payload = body.model_dump(exclude_none=True)
    try:
        apply_patch(payload, desk=True, arm_token=desk_arm_token(request, payload))
        return get_session()
    except BotError as exc:
        raise http_error(exc) from exc


@router.post("/api/bot/session/arm", dependencies=_write)
@router.post("/bot/session/arm", dependencies=_write)
def bot_arm(request: Request, body: ArmBody | None = None) -> dict:
    payload = body.model_dump(exclude_none=True) if body else {}
    try:
        assert_desk_activate(brain_id(request, payload))
        assert_can_activate(load_session())
        token = issue_arm_token(reenable=bool(payload.get("reenable")))
        audit_record(action="activate", outcome="ok", reason="desk")
        view = get_session()
        view["desk_arm_token"] = token
        return view
    except BotError as exc:
        raise http_error(exc) from exc


@router.post("/api/bot/session/disarm", dependencies=_write)
@router.post("/bot/session/disarm", dependencies=_write)
def bot_disarm(request: Request, body: ArmBody | None = None) -> dict:
    payload = body.model_dump(exclude_none=True) if body else {}
    try:
        assert_desk_activate(brain_id(request, payload))
        disarm_session()
        audit_record(action="deactivate", outcome="ok", reason="desk")
        return get_session()
    except BotError as exc:
        raise http_error(exc) from exc


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
def bot_claim(request: Request, body: SessionPatch | None = None) -> dict:
    payload = body.model_dump(exclude_none=True) if body else {}
    try:
        require_l2_brain(brain_id(request, payload), claim=True)
        return get_session()
    except BotError as exc:
        raise http_error(exc) from exc


@router.post("/api/bot/allowlist", dependencies=_write)
@router.post("/bot/allowlist", dependencies=_write)
def bot_allowlist(body: AllowlistBody) -> dict:
    row = load_session()
    try:
        if body.op == "remove":
            remove_symbol(row, body.symbol)
        else:
            add_symbol(row, body.symbol)
        save_session(row)
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


@router.get("/api/bot/proposals")
@router.get("/bot/proposals")
def bot_proposals() -> dict:
    return {"proposals": list_proposals()}


@router.post("/api/bot/proposals", dependencies=_write)
@router.post("/bot/proposals", dependencies=_write)
def bot_propose(request: Request, body: ProposalBody) -> dict:
    payload = body.model_dump(exclude_none=True)
    try:
        return submit(payload, brain_session_id=brain_id(request, payload))
    except BotError as exc:
        raise http_error(exc) from exc


@router.post("/api/bot/proposals/{proposal_id}/accept", dependencies=_write)
@router.post("/bot/proposals/{proposal_id}/accept", dependencies=_write)
def bot_accept(proposal_id: str) -> dict:
    try:
        return accept(proposal_id)
    except BotError as exc:
        raise http_error(exc) from exc


@router.post("/api/bot/proposals/{proposal_id}/reject", dependencies=_write)
@router.post("/bot/proposals/{proposal_id}/reject", dependencies=_write)
def bot_reject(proposal_id: str) -> dict:
    try:
        return reject(proposal_id)
    except BotError as exc:
        raise http_error(exc) from exc


@router.get("/api/bot/focus")
@router.get("/bot/focus")
def bot_focus() -> dict:
    return focus_snapshot()


@router.post("/api/bot/focus", dependencies=_write)
@router.post("/bot/focus", dependencies=_write)
def bot_focus_set(body: FocusBody) -> dict:
    try:
        if body.symbols is not None:
            return set_focus(body.symbols)
        if body.symbol:
            return add_focus(body.symbol)
        return focus_snapshot()
    except BotError as exc:
        raise http_error(exc) from exc


@router.post("/api/bot/focus/sync", dependencies=_write)
@router.post("/bot/focus/sync", dependencies=_write)
def bot_focus_sync(body: LiveSyncBody) -> dict:
    return sync_trader_live(body.live)


@router.get("/api/bot/advise/latest")
@router.get("/bot/advise/latest")
def bot_advise_latest(symbol: str, depth: int | None = None) -> dict:
    try:
        return {"run": advise_latest(symbol, depth)}
    except BotError as exc:
        raise http_error(exc) from exc


@router.post("/api/bot/advise", dependencies=_write)
@router.post("/bot/advise", dependencies=_write)
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
