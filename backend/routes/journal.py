"""
Journal routes -- READ + append only. No route here places, modifies, or
cancels an order.

Endpoints:
  GET /api/journal/signals   -- recent detected setups (from setups_stream.py)
  GET /api/journal/trades    -- recent closed round-trips (empty until Phase D)
  GET /api/journal/metrics   -- win rate, avg win/loss, P/L ratio, go/no-go bar

`include_mock` (default False) opts into synthetic rows seeded by
journal/mock_data.py for UI/logic testing -- real trade metrics never
include them unless a caller explicitly asks. There is no endpoint to seed
or clear mock data; that is a local dev/test action run from the terminal
(`py -3 -m journal.mock_data seed`), deliberately not exposed as a runtime
UI action.
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
def journal_trades(limit: int = JOURNAL_TRADES_DEFAULT_LIMIT, include_mock: bool = False) -> dict:
    rows = get_trades(limit=limit, include_mock=include_mock)
    return {"count": len(rows), "includes_mock_data": include_mock, "trades": rows}


@router.get("/metrics")
def journal_metrics(include_mock: bool = False) -> dict:
    return compute_metrics(include_mock=include_mock)
