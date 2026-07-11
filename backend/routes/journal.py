"""
Journal routes -- READ + append only. No route here places, modifies, or
cancels an order.

Endpoints:
  GET /api/journal/signals   -- recent detected setups (from setups_stream.py)
  GET /api/journal/trades    -- recent closed round-trips (empty until Phase D)
  GET /api/journal/metrics   -- win rate, avg win/loss, P/L ratio, go/no-go bar
"""
from __future__ import annotations

from fastapi import APIRouter

from constants import JOURNAL_SIGNALS_DEFAULT_LIMIT, JOURNAL_TRADES_DEFAULT_LIMIT
from journal.metrics import compute_metrics
from journal.store import get_signals, get_trades

router = APIRouter(prefix="/api/journal", tags=["journal"])


@router.get("/signals")
def journal_signals(limit: int = JOURNAL_SIGNALS_DEFAULT_LIMIT) -> dict:
    rows = get_signals(limit=limit)
    return {"count": len(rows), "signals": rows}


@router.get("/trades")
def journal_trades(limit: int = JOURNAL_TRADES_DEFAULT_LIMIT) -> dict:
    rows = get_trades(limit=limit)
    return {"count": len(rows), "trades": rows}


@router.get("/metrics")
def journal_metrics() -> dict:
    return compute_metrics()
