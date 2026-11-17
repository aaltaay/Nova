"""``/api/brain`` (ADR 072 decision 10, ``bot.md`` "The brain's door"). Loopback only; every write needs the desk's
API key and the brain's own ``X-Nova-Brain-Session`` id, and all but ``claim`` need that id to hold the door.

- ``GET  /api/brain``            what the brain's program reads before it acts
- ``POST /api/brain/claim``      take the door (``409 BRAIN_HELD`` while another program's heartbeat is fresh)
- ``POST /api/brain/heartbeat``  say it is alive
- ``POST /api/brain/arm``        arm Paper as an agent (never Live, never over the operator's padlock)
- ``POST /api/brain/watch``      name lane 3's stock
- ``POST /api/brain/note``       its words and what it reads, for its pill and panel
- ``POST /api/brain/order``      a long bracket inside its limits
- ``POST /api/brain/stop``       raise its resting stop
- ``POST /api/brain/cancel``     cancel one of its own working orders
- ``POST /api/brain/close``      cancel its orders on a stock and sell its shares there at market
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from agent_desk.routes import require_local
from auth import require_agent_key
from brain import book, orders, rules, session, view
from brain.constants_brain import (
    BRAIN_HELD,
    BRAIN_HELD_TEXT,
    BRAIN_NOT_CLAIMED,
    BRAIN_NOT_CLAIMED_TEXT,
    BRAIN_NOT_PAPER,
    BRAIN_NOTE_MAX,
    BRAIN_REFUSED,
    BRAIN_STALE,
    BRAIN_UNREAD_TEXT,
    BRAIN_VENUE,
    BRAIN_WHY_MAX,
)

router = APIRouter(prefix="/api/brain", tags=["brain"], dependencies=[Depends(require_local)])
_keyed = [Depends(require_agent_key)]


class WatchBody(BaseModel):
    symbol: str | None = None
    why: str = Field(default="", max_length=BRAIN_WHY_MAX)


class ReadingRow(BaseModel):
    symbol: str
    text: str = ""


class NoteBody(BaseModel):
    text: str = Field(default="", max_length=BRAIN_NOTE_MAX)
    reading: list[ReadingRow] | None = None


class OrderBody(BaseModel):
    symbol: str
    qty: float
    limit: float
    stop: float
    target: float
    why: str = Field(default="", max_length=BRAIN_NOTE_MAX)


class StopBody(BaseModel):
    symbol: str
    stop: float


class CancelBody(BaseModel):
    order_id: int


class CloseBody(BaseModel):
    symbol: str | None = None
    why: str = Field(default="", max_length=BRAIN_NOTE_MAX)


def _refuse(code: str, text: str, status: int = 409) -> HTTPException:
    return HTTPException(status_code=status, detail={"reason": code, "error": text})


def _holder(session_id: str | None) -> str:
    """The session that holds the door, its heartbeat refreshed; ``409`` for any other. A refusal says fixed words:
    an exception's own text goes to the log, never to the caller."""
    try:
        session.beat(session_id or "")
    except session.NotClaimed as exc:
        raise _refuse(BRAIN_NOT_CLAIMED, BRAIN_NOT_CLAIMED_TEXT) from exc
    return str(session_id)


@router.get("")
def get_brain(x_nova_brain_session: str | None = Header(default=None)) -> dict[str, Any]:
    return view.status(x_nova_brain_session)


@router.post("/claim", dependencies=_keyed)
def claim(x_nova_brain_session: str | None = Header(default=None)) -> dict[str, Any]:
    try:
        new = session.claim(x_nova_brain_session or "")
    except session.Held as exc:
        raise _refuse(BRAIN_HELD, BRAIN_HELD_TEXT) from exc
    except session.NotClaimed as exc:
        raise _refuse(BRAIN_NOT_CLAIMED, BRAIN_NOT_CLAIMED_TEXT, 400) from exc
    if new:
        session.event("claim", "The brain's program connected")
    return {"ok": True, "session": session.view(x_nova_brain_session)}


@router.post("/heartbeat", dependencies=_keyed)
def heartbeat(x_nova_brain_session: str | None = Header(default=None)) -> dict[str, Any]:
    sid = _holder(x_nova_brain_session)
    return {"ok": True, "session": session.view(sid)}


@router.post("/arm", dependencies=_keyed)
def arm(x_nova_brain_session: str | None = Header(default=None)) -> dict[str, Any]:
    from ibkr import safety
    from sim.mode import venue

    sid = _holder(x_nova_brain_session)
    if venue() != BRAIN_VENUE:
        raise _refuse(BRAIN_NOT_PAPER, f"The desk is on {venue()}: the brain arms Paper only")
    if safety.locked_by() == "operator":
        raise _refuse(BRAIN_REFUSED, "You locked the padlock: the brain never unlocks it. Open it when you want "
                                     "the brain to trade.")
    code, reason = safety.arm(True, actor="bot")
    if code:
        raise _refuse(code, reason)
    session.event("armed", "The brain armed the desk on Paper")
    return view.status(sid)


@router.post("/watch", dependencies=_keyed)
async def watch(body: WatchBody, x_nova_brain_session: str | None = Header(default=None)) -> dict[str, Any]:
    from line_lanes import brain as lane

    _holder(x_nova_brain_session)
    before = lane.stock()
    after = await lane.watch(body.symbol, body.why)
    if after != before:
        words = f"The brain wants {after}" + (f": {body.why.strip()}" if body.why.strip() else "") if after \
            else "The brain let its lane go"
        session.event("watch", words, after)
    return {"ok": True, "lane": view.lane_view()}


@router.post("/note", dependencies=_keyed)
def note(body: NoteBody, x_nova_brain_session: str | None = Header(default=None)) -> dict[str, Any]:
    _holder(x_nova_brain_session)
    session.set_note(body.text, None if body.reading is None else [r.model_dump() for r in body.reading])
    return {"ok": True}


@router.post("/order", dependencies=_keyed)
async def place(body: OrderBody, x_nova_brain_session: str | None = Header(default=None)) -> dict[str, Any]:
    sid = _holder(x_nova_brain_session)
    order = body.model_dump()
    order["symbol"] = body.symbol.strip().upper()
    if refused := rules.entry_refusal(order):
        session.event("refused", f"Buy {body.qty:g} {order['symbol']} at {body.limit:g} refused: {refused[1]}",
                      order["symbol"])
        raise _refuse(*refused)
    session.set_note(body.why)
    receipt = await orders.send_entry(order)
    if why := orders.receipt_error(receipt):
        session.event("refused", f"Buy {body.qty:g} {order['symbol']} at {body.limit:g} refused: {why}", order["symbol"])
        raise _refuse(getattr(receipt, "reason_code", None) or BRAIN_REFUSED, why)
    session.event("buy_set", f"Buy {body.qty:g} {order['symbol']} at {body.limit:g}, stop {body.stop:g}, "
                             f"target {body.target:g}", order["symbol"])
    return {"order_id": getattr(receipt, "order_id", None), "stop_order_id": getattr(receipt, "stop_order_id", None),
            "status": view.status(sid)}


@router.post("/stop", dependencies=_keyed)
async def move_stop(body: StopBody, x_nova_brain_session: str | None = Header(default=None)) -> dict[str, Any]:
    """Raise the brain's own stop (never lower it: its risk a trade is counted from the entry to the stop)."""
    sid = _holder(x_nova_brain_session)
    sym = body.symbol.strip().upper()
    try:
        row = book.stop_of(sym)
    except book.ReadError as exc:
        raise _refuse(BRAIN_STALE, BRAIN_UNREAD_TEXT) from exc
    if row is None:
        raise _refuse(BRAIN_REFUSED, f"The brain has no stop resting on {sym}")
    if body.stop <= float(row["stop_price"]):
        raise _refuse(BRAIN_REFUSED, f"A stop only moves up: {body.stop:g} is not above {float(row['stop_price']):g}")
    receipt = await orders.move_stop(int(row["order_id"]), sym, body.stop)
    if why := orders.receipt_error(receipt):
        raise _refuse(getattr(receipt, "reason_code", None) or BRAIN_REFUSED, why)
    session.event("stop_moved", f"Moved the stop on {sym} up to {body.stop:g}", sym)
    return view.status(sid)


@router.post("/cancel", dependencies=_keyed)
async def cancel(body: CancelBody, x_nova_brain_session: str | None = Header(default=None)) -> dict[str, Any]:
    sid = _holder(x_nova_brain_session)
    try:
        row = next((r for r in book.working() if int(r.get("order_id") or -1) == body.order_id), None)
    except book.ReadError as exc:
        raise _refuse(BRAIN_STALE, BRAIN_UNREAD_TEXT) from exc
    if row is None:
        raise _refuse(BRAIN_REFUSED, f"Order {body.order_id} is not one of the brain's working orders")
    receipt = await orders.cancel(body.order_id, str(row["symbol"]))
    if why := orders.receipt_error(receipt):
        raise _refuse(getattr(receipt, "reason_code", None) or BRAIN_REFUSED, why)
    return view.status(sid)


@router.post("/close", dependencies=_keyed)
async def close(body: CloseBody, x_nova_brain_session: str | None = Header(default=None)) -> dict[str, Any]:
    """Always goes: a close is never refused by the switch, the day stop or the clock."""
    sid = _holder(x_nova_brain_session)
    sym = (body.symbol or "").strip().upper() or None
    session.set_note(body.why)
    problems = await orders.close(sym)
    if problems:
        raise _refuse(BRAIN_REFUSED, "; ".join(problems))
    return view.status(sid)
