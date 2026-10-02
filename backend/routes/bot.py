"""Localhost bot HTTP API (ADR 016). Thin handlers -- logic lives in bot/.

ADR 042: the bot's stock list is written only through stock mode's rules
(``bot.allowlist``); Activate refuses with a plain reason (``bot.activation``); the
localhost API refuses every kind on Live and on a replay desk (``bot.actions``).

ADR 044: the Bot switch (``POST /api/bot/session/switch``, ``bot.switch``) is the desk's one
control -- ``PATCH {level}`` and ``POST /arm`` stay for the localhost API -- and the squares
(``GET /api/bot/triggers``, ``bot.trigger_audit``) say, by ticker, why Nova bought or did not.
"""
from __future__ import annotations

import re
import time
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from auth import require_bot_auth
from bot.api_models import (
    ActionBody,
    AllowlistBody,
    ArmBody,
    FocusBody,
    HeartbeatBody,
    LiveSyncBody,
    ProposalBody,
    SessionPatch,
    SwitchBody,
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
from bot.errors import BotError
from bot.focus import add_focus, set_focus, snapshot as focus_snapshot
from bot.focus import sync_trader_live
from bot.http import brain_id, desk_arm_token, http_error, require_loopback
from bot.persist import load_session
from bot.proposals import accept, list_proposals, reject, submit
from bot.session import get_session, require_l2_brain
from bot.watch import halt_watch

router = APIRouter(tags=["bot"], dependencies=[Depends(require_loopback)])
_write = [Depends(require_bot_auth)]
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@router.get("/api/bot/session")
@router.get("/bot/session")
def bot_session() -> dict:
    return get_session()


@router.patch("/api/bot/session", dependencies=_write)
@router.patch("/bot/session", dependencies=_write)
async def bot_session_patch(request: Request, body: SessionPatch) -> dict:
    """The desk's controls. ``symbol_allowlist`` goes through stock mode (one owner, ADR 042):
    each stock it cannot set is listed in ``refused`` with its reason, and the rest apply."""
    from bot.allowlist import set_list
    from constants_bot import BOT_REASON_ARM_DESK_ONLY

    payload = body.model_dump(exclude_none=True)
    if brain_id(request, payload):
        # Adapters never raise autonomy (ADR 016): the levels, the sleeve and the stocks are the desk's.
        raise http_error(BotError("a brain cannot change the bot's levels, sleeve, breakers or stocks -- the desk "
                                  "does", 403, BOT_REASON_ARM_DESK_ONLY))
    symbols = payload.pop("symbol_allowlist", None)
    try:
        if payload:
            apply_patch(payload, desk=True, arm_token=desk_arm_token(request, payload))
        refused = await set_list(symbols) if symbols is not None else []
    except BotError as exc:
        raise http_error(exc) from exc
    view = get_session()
    if symbols is not None:
        view["refused"] = refused
    return view


@router.post("/api/bot/session/arm", dependencies=_write)
@router.post("/bot/session/arm", dependencies=_write)
def bot_arm(request: Request, body: ArmBody | None = None) -> dict:
    """Activate (ADR 042 B): refused with a plain reason on Live, a replay desk, an unreadable venue,
    the master below Strategy, no setup at Strategy, a locked padlock, or a bot trip without re-enable."""
    from bot.activation import assert_can_activate

    payload = body.model_dump(exclude_none=True) if body else {}
    reenable = bool(payload.get("reenable"))
    try:
        assert_desk_activate(brain_id(request, payload))
        assert_can_activate(load_session(), reenable=reenable)
        token = issue_arm_token(reenable=reenable)
        audit_record(action="activate", outcome="ok",
                     reason="the bot trip was re-enabled by you" if reenable else "Activated from the desk",
                     inputs={"reenable": reenable})
        view = get_session()
        view["desk_arm_token"] = token
        return view
    except BotError as exc:
        raise http_error(exc) from exc


@router.post("/api/bot/session/switch", dependencies=_write)
@router.post("/bot/session/switch", dependencies=_write)
def bot_switch(request: Request, body: SwitchBody) -> dict:
    """The Bot switch (ADR 044): ON is the master at Strategy and Activate in one step, refused with
    Activate's codes (``BOT_TRIP_LATCHED`` unless ``reenable``); OFF deactivates with the master at Eyes."""
    from bot.switch import turn

    payload = body.model_dump(exclude_none=True)
    try:
        assert_desk_activate(brain_id(request, payload))
        token = turn(body.on, reenable=body.reenable)
    except BotError as exc:
        raise http_error(exc) from exc
    view = get_session()
    if token:
        view["desk_arm_token"] = token
    return view


@router.post("/api/bot/session/disarm", dependencies=_write)
@router.post("/bot/session/disarm", dependencies=_write)
def bot_disarm(request: Request, body: ArmBody | None = None) -> dict:
    from bot.activation import record

    payload = body.model_dump(exclude_none=True) if body else {}
    try:
        assert_desk_activate(brain_id(request, payload))
        disarm_session("operator")
        record("operator")
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
async def bot_allowlist(body: AllowlistBody) -> dict:
    """One stock on or off this venue's bot list, through stock mode's rules (ADR 042 F): ``add`` sets it
    to Bot (Nova / Nova), ``remove`` to Signal only. A refusal is stock mode's ``{detail: {reason, error,
    field}}``."""
    from bot.allowlist import set_one
    from stock_mode.errors import StockModeError

    try:
        await set_one(body.symbol, on=body.op != "remove")
    except StockModeError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.detail()) from exc
    return get_session()


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


@router.get("/api/bot/audit")
@router.get("/bot/audit")
def bot_audit(limit: int = 200) -> dict:
    return {"entries": list_entries(limit=limit)}


@router.get("/api/bot/pnl")
@router.get("/bot/pnl")
def bot_pnl() -> dict:
    pnl, meter = read_account_day_pnl()
    return {"day_pnl": pnl, "meter": meter}


@router.get("/api/bot/triggers")
@router.get("/bot/triggers")
def bot_triggers(date: str | None = Query(None, description="YYYY-MM-DD; trading day (04:00 ET) by default")) -> dict:
    """The squares, by ticker (ADR 044): every listed ticker now and every trigger of the day, gate by gate.
    Read-only; a sync route, so the journal and the audit stream are read off the loop. Today is the hot
    list's trading day, never the calendar's: from midnight to 04:00 ET the list is still the day before."""
    from bot.trigger_audit import answer
    from hot_list import trading_day
    from scanner_wire import wire_safe

    now = time.time()
    today = trading_day(now)
    day = date or today
    try:
        if not _DATE.match(day):
            raise ValueError(day)
        datetime.fromisoformat(day)
    except ValueError:
        raise HTTPException(status_code=400, detail="date is YYYY-MM-DD") from None
    return wire_safe(answer(day, now, today=day == today))
