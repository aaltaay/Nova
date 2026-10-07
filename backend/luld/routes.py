"""LULD routes (ADR 047). Read-only.

``GET /api/luld/{symbol}`` is one stock's view, the same the Level 2 socket sends: the live feed's,
or on a Sim desk off the live edge the loaded Session Record's at the playhead. ``GET /api/luld``
says which stocks the live worker follows. Memory reads only: no network, no IBKR request.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from luld import live
from luld.ladder import source_view

router = APIRouter(prefix="/api/luld", tags=["luld"])


@router.get("")
def luld_status() -> dict[str, Any]:
    return live.status()


@router.get("/{symbol}")
def luld_view(symbol: str) -> dict[str, Any]:
    return source_view(symbol)
