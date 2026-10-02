"""Today's hot list (ADR 043).

  GET    /api/hot-list                 the list (``hot_list.view``)
  POST   /api/hot-list/star            {symbol}: star a stock onto today's list (it takes the default Buy / Sell)
  DELETE /api/hot-list/{symbol}        off the list, You · You on every venue (refused while Nova trades it)
  PATCH  /api/hot-list                 {auto_n?, default_buy?, default_sell?}
  POST   /api/hot-list/bring-back      yesterday's names as stars, up to the cap

Every write answers the view. Writes decide what Nova may buy, so they need the desk's API key even on
loopback, like the bot's and stock mode's routes (``auth.is_hot_list_mutate``). A refusal is
``{detail: {reason, error, field}}``: 400 ``HOT_LIST_INVALID``; 409 ``HOT_LIST_FULL``, ``HOT_LIST_NOVA_TRADE``,
``HOT_LIST_UNREADABLE`` -- and stock mode's own reasons when its switch refuses the You · You of a removal.
"""
from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth import require_bot_auth
from constants_hot_list import HOT_LIST_BY_OPERATOR
from hot_list import service, stock_tie, view
from hot_list.errors import HotListError
from scanner_wire import wire_safe
from stock_mode.errors import StockModeError

router = APIRouter(tags=["hot_list"])
_write = [Depends(require_bot_auth)]


class StarBody(BaseModel):
    symbol: Any = None      # checked here, so a bad one is HOT_LIST_INVALID rather than a bare 422


class SettingsBody(BaseModel):
    auto_n: Any = None
    default_buy: Any = None
    default_sell: Any = None


def _refused(exc: HotListError | StockModeError) -> HTTPException:
    return HTTPException(status_code=exc.status, detail=exc.detail())


@router.get("/api/hot-list")
def hot_list() -> dict[str, Any]:
    return wire_safe(view.build())


@router.post("/api/hot-list/star", dependencies=_write)
async def star(body: StarBody) -> dict[str, Any]:
    now = time.time()
    try:
        sym = service.symbol(body.symbol)
        if service.star(sym, by=HOT_LIST_BY_OPERATOR, now=now):
            await stock_tie.apply_default(sym, now=now)
    except (HotListError, StockModeError) as exc:
        raise _refused(exc) from exc
    return wire_safe(view.build())


@router.delete("/api/hot-list/{symbol:path}", dependencies=_write)
async def remove(symbol: str) -> dict[str, Any]:
    try:
        await stock_tie.unlist(symbol)
    except (HotListError, StockModeError) as exc:
        raise _refused(exc) from exc
    return wire_safe(view.build())


@router.patch("/api/hot-list", dependencies=_write)
async def settings(body: SettingsBody) -> dict[str, Any]:
    try:
        service.settings(auto_n=body.auto_n, default_buy=body.default_buy, default_sell=body.default_sell)
    except HotListError as exc:
        raise _refused(exc) from exc
    return wire_safe(view.build())


@router.post("/api/hot-list/bring-back", dependencies=_write)
async def bring_back() -> dict[str, Any]:
    now = time.time()
    try:
        for sym in service.bring_back(now=now):
            await stock_tie.apply_default(sym, now=now)
    except (HotListError, StockModeError) as exc:
        raise _refused(exc) from exc
    return wire_safe(view.build())
