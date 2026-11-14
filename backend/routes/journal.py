"""
Journal routes -- READ + append only. No route here places, modifies, or
cancels an order.

Endpoints:
  GET /api/journal/signals   -- setups recorded by the retired setups_stream loop (history)
  GET /api/journal/trades    -- recent closed round-trips
  GET /api/journal/metrics   -- win rate, avg win/loss, P/L ratio and adherence statistics
  GET /api/journal/calendar  -- year/month daily P&L aggregates (Reports tab)
  GET /api/journal/tags      -- per-tag win rate / pnl (Reports v2)
  GET /api/journal/r-multiples -- R-multiple expectancy (Reports v2)
  GET /api/journal/drawdown  -- equity curve + max drawdown (Reports v2)
  GET /api/journal/trail     -- closed-trade / session activity (ledger + journal)
  POST /api/journal/trades/{id}/tags -- update trade tags
  POST /api/journal/import -- Reports CSV/JSON file upload (never invents P/L)
  POST /api/journal/import/ibkr -- IBKR fills probe or JSON trade import

The Reports readers (calendar, tags, r-multiples, drawdown, trades) take a
venue and a view (ADR 069 decision 6, architecture/schema/journal.md):
`venue=paper` reads Paper's round trips -- brought up to the practice ledger
first (journal/paper_trips.py) -- and `owner` / `bot` narrow them to one book
or one bot; the All view adds yours and the bots' beside each total. The
default, `live`, is the journal as it was; /metrics reads only that.

`include_mock` (default False) opts into synthetic rows seeded by
journal/mock_data.py for UI/logic testing -- real trade metrics never
include them unless a caller explicitly asks. There is no endpoint to seed
or clear mock data; that is a local dev/test action run from the terminal
(`py -3 -m journal.mock_data seed`), deliberately not exposed as a runtime
UI action.
"""
from __future__ import annotations

import logging
from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from constants import (
    JOURNAL_CALENDAR_MAX_YEAR,
    JOURNAL_CALENDAR_MIN_YEAR,
    JOURNAL_SIGNALS_DEFAULT_LIMIT,
    JOURNAL_TAGS_MAX_PER_TRADE,
    JOURNAL_TRAIL_DEFAULT_LIMIT,
    JOURNAL_TRADES_DEFAULT_LIMIT,
)
from constants_owners import JOURNAL_VENUE_LIVE, JOURNAL_VENUE_PAPER, OWNER_EARLIER_BOTS
from journal import paper_trips, split
from journal.drawdown import compute_drawdown
from journal.ibkr_import import import_trades_from_json, try_import_from_ibkr_gateway
from journal.import_apply import import_uploaded_file
from journal.r_multiples import compute_r_multiples
from journal.tags import tag_performance
from journal.calendar import build_month_calendar, build_year_calendar
from journal.metrics import compute_metrics
from journal.store import get_closed_trades, get_signals, get_trade_by_id, get_trades, update_trade_tags

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/journal", tags=["journal"])

Venue = Literal["live", "paper"]
Owner = Literal["you", "claude", "brain", "earlier_bots"]
VenueQ = Annotated[Venue, Query(description="live (IBKR round trips and imported files) | paper")]
OwnerQ = Annotated[Owner | None, Query(description="you | claude | brain | earlier_bots: one book (Paper)")]
BotQ = Annotated[str | None, Query(description="One retired bot inside Earlier bots, by its origin (Paper)")]
_R_SPLIT = ("trade_count", "scored_count", "skipped_no_stop", "expectancy_r", "avg_win_r", "avg_loss_r")
_DD_SPLIT = ("trade_count", "final_equity", "peak_equity", "max_drawdown", "max_drawdown_pct")


class TradeTagsBody(BaseModel):
    tags: list[str] = Field(default_factory=list, max_length=JOURNAL_TAGS_MAX_PER_TRADE)


class IbkrImportBody(BaseModel):
    trades: list[dict[str, Any]] | None = None
    use_gateway: bool = False


class JournalImportFileBody(BaseModel):
    filename: str
    content: str


def _closed(include_mock: bool, venue: str, owner: str | None = None, bot: str | None = None) -> list[dict]:
    """The closed trades a Reports read shows; Paper's are first brought up to the practice ledger."""
    if venue == JOURNAL_VENUE_PAPER:
        try:
            paper_trips.sync()
        except Exception:   # the journal still answers with the round trips it holds
            logger.exception("journal: Paper round trips could not be brought up to the ledger")
    return get_closed_trades(include_mock=include_mock, venue=venue, owner=owner, bot=bot)


def _view(venue: str, owner: str | None, bot: str | None) -> dict[str, Any]:
    """What every Reports answer echoes: the venue and the view it read."""
    return {"venue": venue, "view": {"owner": OWNER_EARLIER_BOTS if bot else owner, "bot": bot}}


def _splits(venue: str, owner: str | None, bot: str | None) -> bool:
    """Paper's All view carries each trader's beside each total."""
    return venue == JOURNAL_VENUE_PAPER and owner is None and bot is None


def _bot(bot: str | None) -> str | None:
    return (bot or "").strip() or None


@router.get("/signals")
def journal_signals(limit: int = JOURNAL_SIGNALS_DEFAULT_LIMIT) -> dict:
    rows = get_signals(limit=limit)
    return {"count": len(rows), "signals": rows}


@router.get("/trades")
def journal_trades(
    limit: int = JOURNAL_TRADES_DEFAULT_LIMIT,
    include_mock: bool = False,
    symbol: str | None = None,
    setup: str | None = None,
    tag: str | None = None,
    adherent: bool | None = None,
    date_from: str | None = Query(None, description="YYYY-MM-DD: trades opened on or after this ET day"),
    date_to: str | None = Query(None, description="YYYY-MM-DD: trades opened on or before this ET day"),
    venue: VenueQ = JOURNAL_VENUE_LIVE,
    owner: OwnerQ = None,
    bot: BotQ = None,
) -> dict:
    bot = _bot(bot)
    if venue == JOURNAL_VENUE_PAPER:
        _closed(include_mock, venue)    # brings Paper's round trips up to the ledger
    try:
        rows = get_trades(limit=limit, include_mock=include_mock, symbol=symbol, setup=setup, tag=tag,
                          adherent=adherent, date_from=date_from, date_to=date_to,
                          venue=venue, owner=owner, bot=bot)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"date_from / date_to must be YYYY-MM-DD: {exc}") from exc
    asked = {k: v for k, v in (("symbol", symbol), ("setup", setup), ("tag", tag), ("adherent", adherent),
                               ("date_from", date_from), ("date_to", date_to), ("owner", owner),
                               ("bot", bot)) if v is not None}
    return {"count": len(rows), "includes_mock_data": include_mock, "filters": asked, "trades": rows,
            **_view(venue, owner, bot)}


@router.get("/metrics")
def journal_metrics(include_mock: bool = False) -> dict:
    return compute_metrics(include_mock=include_mock)


@router.get("/calendar")
def journal_calendar(
    year: int = Query(..., description="Calendar year (America/New_York)"),
    month: int | None = Query(None, ge=1, le=12, description="Optional month 1-12 for day grid + weeks"),
    include_mock: bool = False,
    venue: VenueQ = JOURNAL_VENUE_LIVE,
    owner: OwnerQ = None,
    bot: BotQ = None,
) -> dict:
    if year < JOURNAL_CALENDAR_MIN_YEAR or year > JOURNAL_CALENDAR_MAX_YEAR:
        raise HTTPException(
            status_code=400,
            detail=f"year must be {JOURNAL_CALENDAR_MIN_YEAR}..{JOURNAL_CALENDAR_MAX_YEAR}",
        )
    bot = _bot(bot)
    trades = _closed(include_mock, venue, owner, bot)
    split_books = _splits(venue, owner, bot)
    if month is not None:
        out = build_month_calendar(trades, year, month, include_mock=include_mock, split_books=split_books)
    else:
        everyone = None
        if venue == JOURNAL_VENUE_PAPER:   # the Bots menu counts every holder, whatever the view
            everyone = trades if split_books else get_closed_trades(include_mock=include_mock, venue=venue)
        out = build_year_calendar(trades, year, include_mock=include_mock, split_books=split_books,
                                  everyone=everyone)
    return {**out, **_view(venue, owner, bot)}


@router.get("/tags")
def journal_tags(
    include_mock: bool = False,
    venue: VenueQ = JOURNAL_VENUE_LIVE,
    owner: OwnerQ = None,
    bot: BotQ = None,
) -> dict:
    bot = _bot(bot)
    trades = _closed(include_mock, venue, owner, bot)
    rows = tag_performance(trades)
    return {"includes_mock_data": include_mock, "count": len(rows), "tags": rows, **_view(venue, owner, bot)}


@router.get("/r-multiples")
def journal_r_multiples(
    include_mock: bool = False,
    venue: VenueQ = JOURNAL_VENUE_LIVE,
    owner: OwnerQ = None,
    bot: BotQ = None,
) -> dict:
    bot = _bot(bot)
    trades = _closed(include_mock, venue, owner, bot)
    result = compute_r_multiples(trades)
    result["includes_mock_data"] = include_mock
    if _splits(venue, owner, bot):
        result["by_owner"] = split.by_owner(trades, compute_r_multiples, _R_SPLIT)
    return {**result, **_view(venue, owner, bot)}


@router.get("/drawdown")
def journal_drawdown(
    include_mock: bool = False,
    venue: VenueQ = JOURNAL_VENUE_LIVE,
    owner: OwnerQ = None,
    bot: BotQ = None,
) -> dict:
    bot = _bot(bot)
    trades = _closed(include_mock, venue, owner, bot)
    result = compute_drawdown(trades)
    result["includes_mock_data"] = include_mock
    if _splits(venue, owner, bot):
        result["by_owner"] = split.by_owner(trades, compute_drawdown, _DD_SPLIT)
    return {**result, **_view(venue, owner, bot)}


@router.get("/trail")
def journal_trail(
    limit: int = JOURNAL_TRAIL_DEFAULT_LIMIT,
    symbol: str | None = None,
    include_mock: bool = False,
) -> dict:
    from journal.trail import recent_trail

    return recent_trail(limit=limit, symbol=symbol, include_mock=include_mock)


@router.post("/trades/{trade_id}/tags")
def journal_update_trade_tags(trade_id: int, body: TradeTagsBody) -> dict:
    if not get_trade_by_id(trade_id):
        raise HTTPException(status_code=404, detail=f"trade {trade_id} not found")
    updated = update_trade_tags(trade_id, body.tags)
    if updated is None:
        raise HTTPException(status_code=404, detail=f"trade {trade_id} not found")
    return {"ok": True, "trade": updated}


@router.post("/import")
def journal_import_file(body: JournalImportFileBody) -> dict:
    raw = body.content.encode("utf-8")
    result = import_uploaded_file(body.filename or "upload", raw)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result)
    return result


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
