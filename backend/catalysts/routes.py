"""Catalyst routes (ADR 024). Read-only: news only, never a price, never an order.

  GET /api/catalysts/{symbol}   the Trader's News panel -- today's verdict and every item read since
                                the prior close, each labelled (``catalysts.live.panel``)
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from catalysts import live

router = APIRouter(tags=["catalysts"])
_MAX_SYMBOL_LEN = 12


@router.get("/api/catalysts/{symbol:path}")
def catalyst_panel(symbol: str) -> dict:
    sym = (symbol or "").strip().upper()
    if not sym or len(sym) > _MAX_SYMBOL_LEN:
        raise HTTPException(400, "a ticker symbol is required")
    return live.panel(sym)
