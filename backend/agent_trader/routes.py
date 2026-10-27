"""``/api/agent/trader`` (ADR 068): Claude's seat, its line, its Paper orders, and the operator's two buttons.

Loopback only, like every ``/api/agent`` route; every write needs the desk's API key (``auth.is_agent_mutate``).
Claude's own calls also name the seat with ``X-Agent-Seat`` (the token ``POST /seat`` returned). The operator's
buttons -- take Claude's line, give it back, stop Claude -- need no token: the operator is never locked out.
"""
from __future__ import annotations

import logging
from typing import Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field

from agent_desk.routes import require_local
from agent_trader import ledger, lines, look, orders, reflexes, rules, seat, tab_line, view, watcher
from agent_trader import clock
from agent_trader.constants_agent_trader import (
    AGENT_BREAK_DEFAULT_MIN,
    AGENT_BREAK_MAX_MIN,
    AGENT_NOT_MINE,
    AGENT_NOT_PAPER,
    AGENT_REFLEX_DEFAULT_MIN,
    AGENT_REFLEX_MAX,
    AGENT_REFLEX_MAX_MIN,
    AGENT_REFUSED,
    AGENT_SEAT_OFF,
    AGENT_VENUE,
    ENTRY_BREAK,
    ENTRY_LIMIT,
)
from auth import require_agent_key

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/agent/trader", tags=["agent"], dependencies=[Depends(require_local)])
_keyed = [Depends(require_agent_key)]


def _refuse(code: str, text: str, status: int = 409) -> HTTPException:
    return HTTPException(status_code=status, detail={"reason": code, "error": text})


def _holder(token: str | None) -> None:
    if why := seat.refusal(token):
        raise _refuse(why.code, why.text, why.status)


def _unread(where: str) -> HTTPException:
    """Paper could not be read: the words on the wire are fixed, the detail is in the log (ledger.ReadError)."""
    logger.warning("AGENT %s: Paper could not be read", where, exc_info=True)
    return _refuse(AGENT_REFUSED, ledger.UNREAD_TEXT)


class WatchBody(BaseModel):
    symbol: str = Field(min_length=1, max_length=10)


class OrderBody(BaseModel):
    kind: Literal["limit", "break"]
    symbol: str = Field(min_length=1, max_length=10)
    qty: float = Field(gt=0)
    entry: float | None = Field(default=None, gt=0)      # a limit's price
    trigger: float | None = Field(default=None, gt=0)    # a break: a print at or above this ...
    top: float | None = Field(default=None, gt=0)        # ... sends a buy up to this price
    stop: float = Field(gt=0)
    target: float = Field(gt=0)
    target2: float | None = Field(default=None, gt=0)
    target1_qty: float | None = Field(default=None, gt=0)
    minutes: float | None = Field(default=None, gt=0)    # a break's life
    confirm: ConfirmBody | None = None                   # a break sends only while buyers lead (reflexes.confirmed)
    why: str = Field(min_length=1, max_length=400)       # one line for the desk


class ConfirmBody(BaseModel):
    seconds: float = Field(gt=0)
    shares: float = Field(gt=0)
    ratio: float = Field(gt=0)


class ReflexBody(BaseModel):
    kind: Literal["bid_pulled", "ask_wall", "sellers", "last_below"]
    action: Literal["sell_all", "cancel_buy"]
    price: float | None = Field(default=None, gt=0)
    shares: float | None = Field(default=None, gt=0)
    seconds: float | None = Field(default=None, gt=0)
    ratio: float | None = Field(default=None, gt=0)
    minutes: float | None = Field(default=None, gt=0)
    why: str = Field(min_length=1, max_length=400)


class StopBody(BaseModel):
    order_id: int
    stop: float = Field(gt=0)


class CloseBody(BaseModel):
    symbol: str = Field(min_length=1, max_length=10)


class NoteBody(BaseModel):
    text: str = Field(min_length=1, max_length=400)


@router.get("")
def get_status() -> dict[str, Any]:
    return view.status()


@router.get("/look")
async def get_look(symbol: str = Query(min_length=1, max_length=10),
                   seconds: float = Query(default=120.0, gt=0, le=900)) -> dict[str, Any]:
    return await look.look(symbol, seconds)


@router.post("/seat", dependencies=_keyed)
def claim_seat() -> dict[str, Any]:
    from market import now_et

    et = now_et()
    if et.weekday() >= 5 or not (4 <= et.hour < 16):
        raise _refuse(AGENT_SEAT_OFF, "Claude's seat opens on weekdays from 04:00 to 16:00 ET")
    token, why = seat.claim()
    if why:
        raise _refuse(why.code, why.text, why.status)
    return {"token": token, "status": view.status()}


@router.post("/beat", dependencies=_keyed)
def beat(x_agent_seat: str | None = Header(default=None)) -> dict[str, Any]:
    if why := seat.beat(x_agent_seat):
        raise _refuse(why.code, why.text, why.status)
    return view.status()


@router.delete("/seat", dependencies=_keyed)
async def leave_seat(x_agent_seat: str | None = Header(default=None)) -> dict[str, Any]:
    """Claude lets go: its orders cancelled, its shares sold, its line freed."""
    _holder(x_agent_seat)
    problems = await watcher.end_seat("Claude left its seat")
    return {"problems": problems, "status": view.status()}


@router.post("/watch", dependencies=_keyed)
async def watch(body: WatchBody, x_agent_seat: str | None = Header(default=None)) -> dict[str, Any]:
    _holder(x_agent_seat)
    sym = body.symbol.strip().upper()
    try:
        if (held := lines.held_symbol()) and held != sym and (ledger.working() or ledger.positions()):
            raise _refuse(AGENT_REFUSED, f"Claude still has orders or shares on {held}: close them before moving")
    except ledger.ReadError:
        raise _unread("watch") from None
    seat.set_symbol(sym)
    seat.beat(x_agent_seat)
    if seat.reserves_line():
        await watcher.run_pass()
    return view.status()


@router.post("/note", dependencies=_keyed)
def note(body: NoteBody, x_agent_seat: str | None = Header(default=None)) -> dict[str, Any]:
    _holder(x_agent_seat)
    seat.set_note(body.text)
    seat.beat(x_agent_seat)
    return view.status()


@router.post("/arm", dependencies=_keyed)
def arm_paper(x_agent_seat: str | None = Header(default=None)) -> dict[str, Any]:
    """Arm the desk on Paper as a bot (ADR 018): never Live, never over a padlock the operator locked."""
    from ibkr import safety
    from sim.mode import venue

    _holder(x_agent_seat)
    if venue() != AGENT_VENUE:
        raise _refuse(AGENT_NOT_PAPER, f"the desk is on {venue()}: Claude arms Paper only")
    if safety.locked_by() == "operator":
        raise _refuse(AGENT_REFUSED, "you locked the padlock: Claude never unlocks it -- open it when you want "
                      "Claude to trade")
    code, reason = safety.arm(True, actor="bot")
    if code:
        raise _refuse(code, reason)
    seat.event("armed", "Claude armed the desk on Paper")
    return view.status()


@router.post("/order", dependencies=_keyed)
async def place(body: OrderBody, x_agent_seat: str | None = Header(default=None)) -> dict[str, Any]:
    _holder(x_agent_seat)
    seat.beat(x_agent_seat)
    order = body.model_dump()
    order["symbol"] = body.symbol.strip().upper()
    if body.kind == ENTRY_BREAK:
        if body.trigger is None or body.top is None:
            raise _refuse(AGENT_REFUSED, "a break needs its trigger and its top price")
        order["entry"] = body.top
    elif body.entry is None:
        raise _refuse(AGENT_REFUSED, "a limit needs its entry price")
    if refused := rules.entry_refusal(order, pending_breaks=len(seat.breaks())):
        raise _refuse(*refused)
    seat.set_note(body.why)
    if body.kind == ENTRY_LIMIT:
        receipt = await orders.send_entry(order, tag="limit")
        if why := orders.receipt_error(receipt):
            seat.event("refused", f"buy {body.qty:g} {order['symbol']} at {body.entry:g} refused: {why}")
            raise _refuse(getattr(receipt, "reason_code", None) or AGENT_REFUSED, why)
        seat.event("buy_set", f"buy {body.qty:g} {order['symbol']} at {body.entry:g}, stop {body.stop:g}, "
                   f"target {body.target:g}")
        return {"order_id": getattr(receipt, "order_id", None), "stop_order_id": getattr(receipt, "stop_order_id", None),
                "status": view.status()}
    if why := reflexes.confirm_refusal(order.get("confirm")):
        raise _refuse(AGENT_REFUSED, why)
    minutes = min(float(body.minutes or AGENT_BREAK_DEFAULT_MIN), AGENT_BREAK_MAX_MIN)
    row = {k: order[k] for k in ("symbol", "qty", "trigger", "top", "stop", "target", "target2", "target1_qty",
                                 "confirm")}
    made = seat.add_break({**row, "expires_at": clock.now() + minutes * 60.0, "why": body.why})
    return {"break": made, "status": view.status()}


def _mine(order_id: int) -> dict[str, Any]:
    try:
        row = next((r for r in ledger.working() if int(r["order_id"]) == int(order_id)), None)
    except ledger.ReadError:
        raise _unread("order lookup") from None
    if row is None:
        raise _refuse(AGENT_NOT_MINE, f"order {order_id} is not a working order of Claude's", 404)
    return row


@router.post("/stop", dependencies=_keyed)
async def move_stop(body: StopBody, x_agent_seat: str | None = Header(default=None)) -> dict[str, Any]:
    """Raise Claude's own stop (never lower it)."""
    _holder(x_agent_seat)
    seat.beat(x_agent_seat)
    row = _mine(body.order_id)
    if row.get("leg_role") != "stop" or row.get("stop_price") is None:
        raise _refuse(AGENT_REFUSED, f"order {body.order_id} is not Claude's stop")
    if body.stop <= float(row["stop_price"]):
        raise _refuse(AGENT_REFUSED, f"a stop only moves up: {body.stop:g} is not above {float(row['stop_price']):g}")
    receipt = await orders.move_stop(body.order_id, str(row["symbol"]), body.stop)
    if why := orders.receipt_error(receipt):
        raise _refuse(getattr(receipt, "reason_code", None) or AGENT_REFUSED, why)
    seat.event("stop", f"moved the stop on {row['symbol']} up to {body.stop:g}")
    return view.status()


@router.delete("/order/{order_id}", dependencies=_keyed)
async def cancel(order_id: int, x_agent_seat: str | None = Header(default=None)) -> dict[str, Any]:
    _holder(x_agent_seat)
    seat.beat(x_agent_seat)
    row = _mine(order_id)
    receipt = await orders.cancel(order_id, str(row["symbol"]))
    if why := orders.receipt_error(receipt):
        raise _refuse(getattr(receipt, "reason_code", None) or AGENT_REFUSED, why)
    seat.event("cancel", f"cancelled order {order_id} on {row['symbol']}")
    return view.status()


@router.post("/reflex", dependencies=_keyed)
def arm_reflex(body: ReflexBody, x_agent_seat: str | None = Header(default=None)) -> dict[str, Any]:
    """Arm a Level 2 / Time & Sales reflex on the seat's stock (decision 11): Nova acts the moment it holds."""
    _holder(x_agent_seat)
    seat.beat(x_agent_seat)
    sym = seat.symbol()
    if not sym:
        raise _refuse(AGENT_REFUSED, "watch a stock first: a reflex is armed on the seat's stock")
    row = {k: v for k, v in body.model_dump().items() if k not in ("minutes",)}
    if why := reflexes.shape_refusal(row):
        raise _refuse(AGENT_REFUSED, why)
    if len(seat.reflexes()) >= AGENT_REFLEX_MAX:
        raise _refuse(AGENT_REFUSED, f"Claude keeps {AGENT_REFLEX_MAX} reflexes at most: drop one first")
    minutes = min(float(body.minutes or AGENT_REFLEX_DEFAULT_MIN), AGENT_REFLEX_MAX_MIN)
    made = seat.add_reflex({**row, "symbol": sym, "expires_at": clock.now() + minutes * 60.0}, reflexes.text(row))
    return {"reflex": made, "status": view.status()}


@router.delete("/reflex/{reflex_id}", dependencies=_keyed)
def drop_reflex(reflex_id: str, x_agent_seat: str | None = Header(default=None)) -> dict[str, Any]:
    _holder(x_agent_seat)
    if seat.drop_reflex(reflex_id, f"Claude took back reflex {reflex_id}") is None:
        raise _refuse(AGENT_NOT_MINE, f"no reflex {reflex_id}", 404)
    return view.status()


@router.delete("/break/{break_id}", dependencies=_keyed)
def cancel_break(break_id: str, x_agent_seat: str | None = Header(default=None)) -> dict[str, Any]:
    _holder(x_agent_seat)
    if seat.drop_break(break_id, f"Claude took back break {break_id}") is None:
        raise _refuse(AGENT_NOT_MINE, f"no break {break_id}", 404)
    return view.status()


@router.post("/close", dependencies=_keyed)
async def close(body: CloseBody, x_agent_seat: str | None = Header(default=None)) -> dict[str, Any]:
    """Sell Claude's own shares in ``symbol`` at market, after cancelling its orders there."""
    _holder(x_agent_seat)
    seat.beat(x_agent_seat)
    sym = body.symbol.strip().upper()
    try:
        for row in [r for r in ledger.working() if str(r["symbol"]).upper() == sym]:
            await orders.cancel(int(row["order_id"]), sym)
        qty = ledger.position(sym)
    except ledger.ReadError:
        raise _unread("close") from None
    if qty <= 0:
        return view.status()
    receipt = await orders.close(sym, qty)
    if why := orders.receipt_error(receipt):
        raise _refuse(getattr(receipt, "reason_code", None) or AGENT_REFUSED, why)
    seat.event("close", f"sold {qty:g} {sym} at market")
    return view.status()


# -- the operator's buttons ---------------------------------------------------------------------------------
@router.post("/yield", dependencies=_keyed)
async def take_line() -> dict[str, Any]:
    """Take Claude's line: no new trades, its unfilled buys and breaks cancelled, its stop on held shares kept."""
    if not seat.is_on():
        raise _refuse(AGENT_SEAT_OFF, "Claude's seat is off")
    try:
        for row in ledger.working():
            if str(row.get("side") or "").upper() == "BUY" and row.get("leg_role") in (None, "parent"):
                await orders.cancel(int(row["order_id"]), str(row["symbol"]))
    except ledger.ReadError:
        raise _unread("take the line") from None
    seat.set_yielded(True, "you took Claude's line: no new trades; an open trade keeps its stop")
    await lines.release(at_once=True)
    return view.status()


@router.post("/give-back", dependencies=_keyed)
async def give_back() -> dict[str, Any]:
    if not seat.is_on():
        raise _refuse(AGENT_SEAT_OFF, "Claude's seat is off")
    seat.set_yielded(False, "you gave Claude its line back")
    await watcher.run_pass()
    return view.status()


class TakeBackBody(BaseModel):
    symbol: str = Field(min_length=1, max_length=10)


@router.post("/take-back", dependencies=_keyed)
async def take_back(body: TakeBackBody) -> dict[str, Any]:
    """The operator's right-click on a Trader tab, Take my Level 2 back from Claude (decision 14): that tab's lines
    come back now; Claude stays on, its orders as they are, and waits for another line."""
    if why := await tab_line.take_back(body.symbol):
        raise _refuse(AGENT_NOT_MINE, why, 404)
    return view.status()


@router.post("/stop-claude", dependencies=_keyed)
async def stop_claude() -> dict[str, Any]:
    """Stop Claude: its orders cancelled, its shares sold, the seat off, the line yours."""
    problems = await watcher.end_seat("you stopped Claude")
    return {"problems": problems, "status": view.status()}
