"""``/api/phone`` (ADR 070, amendment 2026-11-10): unlock with the phone PIN, then trade Paper or Sim.

The only writes another device may make (``request_guard``), opened by the phone PIN's session and
not by ``X-Nova-Api-Key`` (``auth``): the key never leaves the PC. Every order names the desk's venue
(Paper or Sim) and is handed to the desk's own handlers, so the one order door judges it -- the arm
latch, the stale-view rules (ADR 045), the size limit (ADR 064), the loss limit -- and refuses it
``VENUE_CHANGED`` if the desk has moved by the time it is sent. On Live the phone looks only. No short
entry, no bracket, no setting: a buy, a sell, a stop, a flatten, a cancel, the padlock on Paper and Sim,
and (amendment 2026-11-13) the desk's venue and the Sim's playhead, each through the desk's own handler.

The phone's Trade screen (amendment 2026-11-12) sends the desk's own order body here, so the fields it
does not take (a venue, a time in force) are read past, never trusted: every order is Paper, DAY.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field, StrictBool

from phone import pin, session
from phone.constants_phone import (
    PHONE_API_PREFIX,
    PHONE_LOCKED,
    PHONE_LIVE_LOOK_ONLY,
    PHONE_NO_VIEW,
    PHONE_SCHEMA_VERSION,
    PHONE_SIM_CLOCK_KEYS,
    PHONE_TRADE_VENUES,
    PHONE_VENUE,
)
from routes import trading_execution as desk

logger = logging.getLogger(__name__)
router = APIRouter(prefix=PHONE_API_PREFIX, tags=["phone"])


class UnlockBody(BaseModel):
    pin: str = Field(max_length=32)


class ArmBody(BaseModel):
    armed: StrictBool


class VenueBody(BaseModel):
    venue: Literal["live", "paper", "sim"]


class PhoneOrder(BaseModel):
    """One order on Paper or Sim. The timing and the view are required: without them the door would not judge lag."""

    symbol: str = Field(min_length=1, max_length=16)
    side: Literal["BUY", "SELL"]
    qty: float = Field(gt=0)
    order_type: Literal["MKT", "LMT", "STP"] = "MKT"
    limit_price: float | None = Field(default=None, gt=0)
    # A stop: the price that wakes it. A sell stop under a long, or a buy stop above the market.
    stop_price: float | None = Field(default=None, gt=0)
    # The bid or ask a limit was priced from, for the door's slippage check; never the order's price.
    reference_price: float | None = Field(default=None, gt=0)
    outside_rth: bool = False
    intent: Literal["flatten"] | None = None
    idempotency_key: str | None = Field(default=None, max_length=128)
    client_timing: desk.BrowserTimingRequest
    view: desk.ViewStamp


def _refuse(code: str, text: str, status: int) -> HTTPException:
    return HTTPException(status_code=status, detail={"reason": code, "error": text})


def _venue() -> str:
    from sim.mode import venue

    return venue()


def require_session(x_nova_phone_session: str | None = Header(default=None)) -> str:
    if not session.valid(x_nova_phone_session):
        raise _refuse(PHONE_LOCKED, "Unlock with your PIN first. Nothing was sent.", 401)
    return str(x_nova_phone_session)


def _trade_venue() -> str:
    """The desk's venue when the phone may trade it (Paper or Sim). Refused in plain words on Live, before the door:
    the door's own venue check is what holds when the desk moves between this read and the send."""
    where = _venue()
    if where not in PHONE_TRADE_VENUES:
        raise _refuse(PHONE_LIVE_LOOK_ONLY,
                      f"The desk is on {where.capitalize()}: from the phone, Live is look only. Send Live orders "
                      "from the PC. Nothing was sent.", 409)
    return where


def _status(token: str | None) -> dict[str, Any]:
    from ibkr import safety

    where = _venue()
    return {
        "schema_version": PHONE_SCHEMA_VERSION,
        "pin_set": pin.pin_is_set(),
        "unlocked": session.valid(token),
        "expires_at": session.expires_at(token),
        "venue": where,
        "paper": where == PHONE_VENUE,
        # Whether the phone may send orders on the desk's venue now (Paper or Sim).
        "trades": where in PHONE_TRADE_VENUES,
        "armed": bool(safety.armed()),
        # The PC's clock (epoch s): the phone's once-a-second read of this route measures its link and its clock.
        "now": time.time(),
    }


@router.get("")
def get_status(x_nova_phone_session: str | None = Header(default=None)) -> dict[str, Any]:
    return _status(x_nova_phone_session)


@router.post("/unlock")
def unlock(body: UnlockBody) -> dict[str, Any]:
    code, reason = pin.check(body.pin)
    if code:
        raise _refuse(code, reason, 403)
    token, _expires = session.open_session()
    logger.warning("PHONE: unlocked with the operator's PIN (Paper and Sim)")
    return {"token": token, **_status(token)}


@router.post("/lock")
def lock(token: str = Depends(require_session)) -> dict[str, Any]:
    session.close()
    logger.warning("PHONE: locked from the phone")
    return _status(token)


@router.post("/arm")
def arm(body: ArmBody, token: str = Depends(require_session)) -> dict[str, Any]:
    """The padlock, from the phone. Locking is always allowed; unlocking only while the desk is on Paper or Sim."""
    from ibkr import safety

    if body.armed:
        _trade_venue()
    code, reason = safety.arm(bool(body.armed), actor="operator")
    if code:
        raise _refuse(code, reason, 403)
    return _status(token)


@router.post("/order")
async def place(body: PhoneOrder, request: Request, _token: str = Depends(require_session)) -> dict:
    where = _trade_venue()
    order = desk.OrderRequest(
        symbol=body.symbol.strip().upper(), side=body.side, qty=body.qty, order_type=body.order_type,
        limit_price=body.limit_price, stop_price=body.stop_price, reference_price=body.reference_price,
        outside_rth=body.outside_rth, intent=body.intent,
        idempotency_key=body.idempotency_key, client_timing=body.client_timing, view=body.view,
        venue=where,
    )
    # ADR 045 on the desk lets a view without a book through (a desk with no Level 2 pane still has its quote).
    # The phone's only market is the Level 2 it received, so a new entry without one was priced from nothing.
    if (body.view.book is None or body.view.instance is None) and desk.opens_a_position(order):
        raise _refuse(PHONE_NO_VIEW, f"Your phone has not received Level 2 for {order.symbol} yet, so the buy was "
                      "not sent. Wait for the book to show, then tap again. A sell, Flatten and Cancel still "
                      "work.", 409)
    return await desk.place_order(order, request)


@router.delete("/order/{order_id}")
async def cancel(order_id: int, request: Request, _token: str = Depends(require_session)) -> dict:
    where = _trade_venue()
    return await desk.cancel_order(order_id, request, idempotency_key=None, venue=where)


@router.delete("/orders")
async def cancel_many(
    request: Request, symbol: str | None = None, all_symbols: bool = False, _token: str = Depends(require_session),
) -> dict:
    """Cancel every working order on the desk's venue on one symbol, or (``all_symbols=true``) on every symbol."""
    where = _trade_venue()
    return await desk.cancel_orders_for_symbol(
        request, symbol=None if all_symbols else symbol, all_symbols=all_symbols, venue=where,
    )


@router.get("/venue/effects")
def venue_effects() -> dict[str, Any]:
    """What leaving the desk's venue now would cancel or change, said before the tap (a read: no session).

    Nova's entries still waiting to fill there (``stock_mode.leave``), the Bot and the padlock
    (``agent_desk.safety``). A check that cannot be read is named in ``unknown``, never read as nothing."""
    from agent_desk import safety
    from stock_mode import leave

    where = _venue()
    lines: list[str] = []
    unknown: list[str] = []
    try:
        work = leave.work_on(where)
    except Exception:
        logger.warning("PHONE: could not read Nova's working entries on %s", where, exc_info=True)
        unknown.append("Nova's working entries")
    else:
        if work:
            lines.append(f"Cancels on {where.capitalize()}: {', '.join(work)}.")
    items, failed = safety.switch_changes(where)
    lines += [str(item.get("text") or item.get("kind")) for item in items]
    unknown += [str(f.get("kind")) for f in failed]
    return {"venue": where, "lines": lines, "unknown": unknown}


@router.post("/venue")
async def move_venue(body: VenueBody, token: str = Depends(require_session)) -> dict[str, Any]:
    """Move the desk to ``venue`` through the desk's own route, as the header's pill does (one venue for both)."""
    from ibkr import client
    from routes.desk import DeskVenueRequest, post_desk_venue

    answer = await post_desk_venue(DeskVenueRequest(venue=body.venue))
    logger.warning("PHONE: moved the desk to %s", body.venue)
    gateway: str | None = None
    if answer.get("venue") == "live":
        # The desk's pill asks for the live Gateway after a switch to Live; its words only when it did something.
        mode = await client.request_gateway_mode("live")
        if mode.get("message") and mode.get("launch_action") not in (None, "noop"):
            gateway = str(mode["message"])
    return {**_status(token), "left": answer.get("left") or [], "gateway": gateway}


@router.post("/sim/clock")
def sim_clock(body: dict[str, Any], _token: str = Depends(require_session)) -> dict:
    """The Sim's playhead from the phone: pause / play, or a step to a minute. The desk's own handler judges it."""
    from sim.routes import post_sim_clock

    extra = set(body) - PHONE_SIM_CLOCK_KEYS
    if extra or not ({"paused", "minute_from_open"} & set(body)):
        raise HTTPException(status_code=422, detail="The phone sends {paused} or {minute_from_open, symbol?} only.")
    minute = body.get("minute_from_open")
    if "minute_from_open" in body and (isinstance(minute, bool) or not isinstance(minute, int)):
        raise HTTPException(status_code=422, detail="minute_from_open must be a whole minute")
    return post_sim_clock(body)
