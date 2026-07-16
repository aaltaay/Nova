"""
Journal routes -- READ + append only. No route here places, modifies, or
cancels an order.

Endpoints:
  GET /api/journal/signals   -- recent detected setups (from setups_stream.py)
  GET /api/journal/trades    -- recent closed round-trips (empty until Phase D)
  GET /api/journal/metrics   -- win rate, avg win/loss, P/L ratio, go/no-go bar
  GET /api/journal/calendar  -- year/month daily P&L aggregates (Reports tab)
  GET /api/journal/tags      -- per-tag win rate / pnl (Reports v2)
  GET /api/journal/r-multiples -- R-multiple expectancy (Reports v2)
  GET /api/journal/drawdown  -- equity curve + max drawdown (Reports v2)
  POST /api/journal/trades/{id}/tags -- update trade tags
  POST /api/journal/import/ibkr -- IBKR fills probe or JSON trade import

`include_mock` (default False) opts into synthetic rows seeded by
journal/mock_data.py for UI/logic testing -- real trade metrics never
include them unless a caller explicitly asks. There is no endpoint to seed
or clear mock data; that is a local dev/test action run from the terminal
(`py -3 -m journal.mock_data seed`), deliberately not exposed as a runtime
UI action.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from constants import (
    JOURNAL_CALENDAR_MAX_YEAR,
    JOURNAL_CALENDAR_MIN_YEAR,
    JOURNAL_SIGNALS_DEFAULT_LIMIT,
    JOURNAL_TAGS_MAX_PER_TRADE,
    JOURNAL_TRADES_DEFAULT_LIMIT,
)
from journal.drawdown import compute_drawdown
from journal.ibkr_import import import_trades_from_json, try_import_from_ibkr_gateway
from journal.r_multiples import compute_r_multiples
from journal.tags import tag_performance
from journal.calendar import build_month_calendar, build_year_calendar
from journal.metrics import compute_metrics
from journal.store import get_closed_trades, get_signals, get_trade_by_id, get_trades, update_trade_tags

router = APIRouter(prefix="/api/journal", tags=["journal"])


class TradeTagsBody(BaseModel):
    tags: list[str] = Field(default_factory=list, max_length=JOURNAL_TAGS_MAX_PER_TRADE)


class IbkrImportBody(BaseModel):
    trades: list[dict[str, Any]] | None = None
    use_gateway: bool = False


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


@router.get("/tags")
def journal_tags(include_mock: bool = False) -> dict:
    trades = get_closed_trades(include_mock=include_mock)
    rows = tag_performance(trades)
    return {"includes_mock_data": include_mock, "count": len(rows), "tags": rows}


@router.get("/r-multiples")
def journal_r_multiples(include_mock: bool = False) -> dict:
    trades = get_closed_trades(include_mock=include_mock)
    result = compute_r_multiples(trades)
    result["includes_mock_data"] = include_mock
    return result


@router.get("/drawdown")
def journal_drawdown(include_mock: bool = False) -> dict:
    trades = get_closed_trades(include_mock=include_mock)
    result = compute_drawdown(trades)
    result["includes_mock_data"] = include_mock
    return result


@router.post("/trades/{trade_id}/tags")
def journal_update_trade_tags(trade_id: int, body: TradeTagsBody) -> dict:
    if not get_trade_by_id(trade_id):
        raise HTTPException(status_code=404, detail=f"trade {trade_id} not found")
    updated = update_trade_tags(trade_id, body.tags)
    if updated is None:
        raise HTTPException(status_code=404, detail=f"trade {trade_id} not found")
    return {"ok": True, "trade": updated}


@router.post("/import/ibkr")
def journal_import_ibkr(body: IbkrImportBody | None = None) -> dict:
    payload = body or IbkrImportBody()
    if payload.trades:
        result = import_trades_from_json(payload.trades)
        if not result.get("ok"):
            raise HTTPException(status_code=400, detail=result.get("error") or "import failed")
        return result
    if payload.use_gateway:
        result = try_import_from_ibkr_gateway()
        if not result.get("ok"):
            raise HTTPException(
                status_code=503,
                detail=result.get("error") or "IBKR import unavailable",
            )
        return result
    result = try_import_from_ibkr_gateway()
    if not result.get("ok"):
        raise HTTPException(
            status_code=503,
            detail=result.get("error") or "Provide trades JSON or connect IB Gateway",
        )
    return result
