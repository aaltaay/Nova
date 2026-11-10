"""``/api/phone`` (ADR 070, amendment 2026-11-10): unlock with the phone PIN, then trade Paper.

The only writes another device may make (``request_guard``), opened by the phone PIN's session and
not by ``X-Nova-Api-Key`` (``auth``): the key never leaves the PC. Every order names Paper as its
venue and is handed to the desk's own handlers, so the one order door judges it -- the arm latch,
the stale-view rules (ADR 045), the size limit (ADR 064), the loss limit -- and refuses it
``VENUE_CHANGED`` if the desk is anywhere but Paper when it is sent. No short entry, no bracket,
no venue change, no setting: a buy, a sell, a flatten, a cancel, and Paper's padlock.
"""
from __future__ import annotations

import logging
from typing import Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field, StrictBool

from phone import pin, session
from phone.constants_phone import (
    PHONE_API_PREFIX,
    PHONE_LOCKED,
    PHONE_NOT_PAPER,
    PHONE_SCHEMA_VERSION,
    PHONE_VENUE,
)
from routes import trading_execution as desk

logger = logging.getLogger(__name__)
router = APIRouter(prefix=PHONE_API_PREFIX, tags=["phone"])


class UnlockBody(BaseModel):
    pin: str = Field(max_length=32)


class ArmBody(BaseModel):
    armed: StrictBool


class PhoneOrder(BaseModel):
    """One Paper order. The timing and the view are required: without them the door would not judge lag."""

    symbol: str = Field(min_length=1, max_length=16)
    side: Literal["BUY", "SELL"]
    qty: float = Field(gt=0)
    order_type: Literal["MKT", "LMT"] = "MKT"
    limit_price: float | None = Field(default=None, gt=0)
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
        raise _refuse(PHONE_LOCKED, "Unlock with your phone PIN first. Nothing was sent.", 401)
    return str(x_nova_phone_session)


def _paper_only() -> None:
    """Refuse in plain words before the door does; the door's own venue check is what holds under a race."""
    where = _venue()
    if where != PHONE_VENUE:
        raise _refuse(PHONE_NOT_PAPER,
                      f"The desk is on {where.capitalize()}: the phone trades Paper only. Nothing was sent.", 409)


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
        "armed": bool(safety.armed()),
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
    logger.warning("PHONE: unlocked with the phone PIN (Paper only)")
    return {"token": token, **_status(token)}


@router.post("/lock")
def lock(token: str = Depends(require_session)) -> dict[str, Any]:
    session.close()
    logger.warning("PHONE: locked from the phone")
    return _status(token)


@router.post("/arm")
def arm(body: ArmBody, token: str = Depends(require_session)) -> dict[str, Any]:
    """Paper's padlock, from the phone. Locking is always allowed; unlocking only while the desk is on Paper."""
    from ibkr import safety

    if body.armed:
        _paper_only()
    code, reason = safety.arm(bool(body.armed), actor="operator")
    if code:
        raise _refuse(code, reason, 403)
    return _status(token)


@router.post("/order")
async def place(body: PhoneOrder, request: Request, _token: str = Depends(require_session)) -> dict:
    _paper_only()
    order = desk.OrderRequest(
        symbol=body.symbol.strip().upper(), side=body.side, qty=body.qty, order_type=body.order_type,
        limit_price=body.limit_price, outside_rth=body.outside_rth, intent=body.intent,
        idempotency_key=body.idempotency_key, client_timing=body.client_timing, view=body.view,
        venue=PHONE_VENUE,
    )
    return await desk.place_order(order, request)


@router.delete("/order/{order_id}")
async def cancel(order_id: int, request: Request, _token: str = Depends(require_session)) -> dict:
    _paper_only()
    return await desk.cancel_order(order_id, request, idempotency_key=None, venue=PHONE_VENUE)


@router.delete("/orders")
async def cancel_symbol(symbol: str, request: Request, _token: str = Depends(require_session)) -> dict:
    """Cancel every working Paper order on one symbol."""
    _paper_only()
    return await desk.cancel_orders_for_symbol(request, symbol=symbol, all_symbols=False, venue=PHONE_VENUE)
