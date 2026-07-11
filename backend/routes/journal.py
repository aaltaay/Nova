"""
Journal routes -- READ + append only. No route here places, modifies, or
cancels an order.

Endpoints:
  GET /api/journal/signals   -- recent detected setups (from setups_stream.py)
  GET /api/journal/trades    -- recent closed round-trips (empty until Phase D)
  GET /api/journal/metrics   -- win rate, avg win/loss, P/L ratio, go/no-go bar
  GET /api/journal/calendar  -- year/month daily P&L aggregates (Reports tab)

`include_mock` (default False) opts into synthetic rows seeded by
journal/mock_data.py for UI/logic testing -- real trade metrics never
include them unless a caller explicitly asks. There is no endpoint to seed
or clear mock data; that is a local dev/test action run from the terminal
(`py -3 -m journal.mock_data seed`), deliberately not exposed as a runtime
UI action.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from constants import (
    JOURNAL_CALENDAR_MAX_YEAR,
    JOURNAL_CALENDAR_MIN_YEAR,
    JOURNAL_SIGNALS_DEFAULT_LIMIT,
    JOURNAL_TRADES_DEFAULT_LIMIT,
)
from journal.calendar import build_month_calendar, build_year_calendar
from journal.metrics import compute_metrics
from journal.store import get_closed_trades, get_signals, get_trades

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


@router.get("/calendar")
def journal_calendar(
    year: int = Query(..., description="Calendar year (America/New_York)"),
    month: int | None = Query(None, ge=1, le=12, description="Optional month 1-12 for day grid + weeks"),
    include_mock: bool = False,
) -> dict:
    if year < JOURNAL_CALENDAR_MIN_YEAR or year > JOURNAL_CALENDAR_MAX_YEAR:
        raise HTTPException(
            status_code=400,
            detail=f"year must be {JOURNAL_CALENDAR_MIN_YEAR}..{JOURNAL_CALENDAR_MAX_YEAR}",
        )
    trades = get_closed_trades(include_mock=include_mock)
    if month is not None:
        return build_month_calendar(trades, year, month, include_mock=include_mock)
    return build_year_calendar(trades, year, include_mock=include_mock)
