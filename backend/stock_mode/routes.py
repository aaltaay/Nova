"""Who trades the stock (ADR 037).

  GET    /api/stock-mode                       every stock not at Signal only
  GET    /api/stock-mode/{symbol}              one stock's view (polled by the Trader tab)
  PUT    /api/stock-mode/{symbol}              {buy, sell, risk_usd?}: set the switch
  POST   /api/stock-mode/{symbol}/approve      {setup_id, entry, stop, target, qty, now?}
  DELETE /api/stock-mode/{symbol}/approve      withdraw the approval (or cancel its unfilled entry)
  POST   /api/stock-mode/{symbol}/take-over    cancel the exits Nova holds on the stock

Writes place and cancel orders, so they need the desk's API key even on loopback, like the bot's routes
(``auth.is_stock_mode_mutate``).
"""
from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel

from auth import require_bot_auth
from constants_stock_mode import STOCK_MODE_SCHEMA_VERSION
from scanner_wire import wire_safe
from stock_mode import actions, gates, view
from stock_mode.errors import StockModeError

router = APIRouter(tags=["stock_mode"])
_write = [Depends(require_bot_auth)]


class SwitchBody(BaseModel):
    buy: str
    sell: str
    risk_usd: float | None = None


class ApproveBody(BaseModel):
    setup_id: str
    entry: float
    stop: float
    target: float
    qty: int
    now: bool = False


class TakeOverBody(BaseModel):
    risk_usd: float | None = None


# The take-over body is optional (it may carry the desk's risk per trade for the Auto-entry it leaves).
_NO_BODY = Body(None)


def _refused(exc: StockModeError) -> HTTPException:
    return HTTPException(status_code=exc.status, detail=exc.detail())


@router.get("/api/stock-mode")
def stock_modes() -> dict[str, Any]:
    now = time.time()
    venue, _replay = gates.venue_state()
    return wire_safe({"schema_version": STOCK_MODE_SCHEMA_VERSION, "generated_at": now, "venue": venue,
                      "stocks": view.all_stocks(now=now)})


@router.get("/api/stock-mode/{symbol}")
def stock_mode(symbol: str) -> dict[str, Any]:
    try:
        return wire_safe(view.build(symbol))
    except StockModeError as exc:
        raise _refused(exc) from exc


@router.put("/api/stock-mode/{symbol}", dependencies=_write)
async def set_stock_mode(symbol: str, body: SwitchBody) -> dict[str, Any]:
    try:
        return wire_safe(await actions.set_mode(symbol, body.buy, body.sell, body.risk_usd))
    except StockModeError as exc:
        raise _refused(exc) from exc


@router.post("/api/stock-mode/{symbol}/approve", dependencies=_write)
async def approve_plan(symbol: str, body: ApproveBody) -> dict[str, Any]:
    try:
        return wire_safe(await actions.approve(symbol, body.model_dump()))
    except StockModeError as exc:
        raise _refused(exc) from exc


@router.delete("/api/stock-mode/{symbol}/approve", dependencies=_write)
async def withdraw_approval(symbol: str) -> dict[str, Any]:
    try:
        return wire_safe(await actions.withdraw(symbol))
    except StockModeError as exc:
        raise _refused(exc) from exc


@router.post("/api/stock-mode/{symbol}/take-over", dependencies=_write)
async def take_over_exit(symbol: str, body: TakeOverBody | None = _NO_BODY) -> dict[str, Any]:
    try:
        return wire_safe(await actions.take_over(symbol, risk=body.risk_usd if body else None))
    except StockModeError as exc:
        raise _refused(exc) from exc
