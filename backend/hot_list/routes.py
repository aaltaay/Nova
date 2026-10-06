"""Today's hot list (ADR 044).

  GET    /api/hot-list                 the list (``hot_list.view``)
  POST   /api/hot-list/star            {symbol}: star a stock onto today's list
  DELETE /api/hot-list/{symbol}        off the list (who trades it is unchanged)
  PATCH  /api/hot-list                 {auto_n?}
  POST   /api/hot-list/bring-back      yesterday's names as stars, up to the cap

Every write answers the view. Writes decide which names the scanners keep following, so they need the desk's
API key even on loopback, like the bot's and stock mode's routes (``auth.is_hot_list_mutate``). A refusal is
``{detail: {reason, error, field}}``: 400 ``HOT_LIST_INVALID``; 409 ``HOT_LIST_FULL``, ``HOT_LIST_UNREADABLE``.
The list never sets who trades a stock (ADR 044, amended 2026-10-06).
"""
from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth import require_bot_auth
from constants_hot_list import HOT_LIST_BY_OPERATOR
from hot_list import service, view
from hot_list.errors import HotListError
from scanner_wire import wire_safe

router = APIRouter(tags=["hot_list"])
_write = [Depends(require_bot_auth)]


class StarBody(BaseModel):
    symbol: Any = None      # checked here, so a bad one is HOT_LIST_INVALID rather than a bare 422


class SettingsBody(BaseModel):
    auto_n: Any = None


def _refused(exc: HotListError) -> HTTPException:
    return HTTPException(status_code=exc.status, detail=exc.detail())


@router.get("/api/hot-list")
def hot_list() -> dict[str, Any]:
    return wire_safe(view.build())


@router.post("/api/hot-list/star", dependencies=_write)
def star(body: StarBody) -> dict[str, Any]:
    try:
        service.star(body.symbol, by=HOT_LIST_BY_OPERATOR, now=time.time())
    except HotListError as exc:
        raise _refused(exc) from exc
    return wire_safe(view.build())


@router.delete("/api/hot-list/{symbol:path}", dependencies=_write)
def remove(symbol: str) -> dict[str, Any]:
    try:
        service.remove(service.symbol(symbol))
    except HotListError as exc:
        raise _refused(exc) from exc
    return wire_safe(view.build())


@router.patch("/api/hot-list", dependencies=_write)
def settings(body: SettingsBody) -> dict[str, Any]:
    try:
        service.settings(auto_n=body.auto_n)
    except HotListError as exc:
        raise _refused(exc) from exc
    return wire_safe(view.build())


@router.post("/api/hot-list/bring-back", dependencies=_write)
def bring_back() -> dict[str, Any]:
    try:
        service.bring_back(now=time.time())
    except HotListError as exc:
        raise _refused(exc) from exc
    return wire_safe(view.build())
