"""``/api/ahead/*`` -- the forecast zone on the Trader's 1-minute chart (ADR 061, ``architecture/schema/ahead.md``).

Read-only: it places, stages and blocks nothing. Always registered: with no forecaster set up it answers
``not_set_up`` and sends no request. The forecast answers 200 in every state and 422 only for a bad symbol; it lives
under ``/forecast/`` so ``status`` can never be read as a ticker.
"""
from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, HTTPException

from ahead import service
from constants_ahead import AHEAD_ERR_BAD_SYMBOL
from scanner_wire import wire_safe

router = APIRouter(tags=["ahead"])
_SYMBOL = re.compile(r"[A-Z][A-Z0-9.\-]{0,9}")


@router.get("/api/ahead/status")
async def ahead_status() -> dict[str, Any]:
    return wire_safe(await service.status())


@router.get("/api/ahead/forecast/{symbol}")
async def ahead_forecast(symbol: str) -> dict[str, Any]:
    sym = symbol.strip().upper()
    if not _SYMBOL.fullmatch(sym):
        raise HTTPException(status_code=422, detail={"reason": AHEAD_ERR_BAD_SYMBOL,
                                                     "error": f"Not a stock symbol: {symbol[:20]!r}"})
    return wire_safe(await service.ahead(sym))
