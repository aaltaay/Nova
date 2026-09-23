"""The Five Pillars for any one symbol (operator ask, 2026-09-23).

The quote panel grades the symbol it shows whether or not the ranked
watchlist holds it. Read-only and no network: the symbol's own scanner row
when a board holds it (surfaced exactly as the Scanner shows it), else its
live L1 quote decorated the same way -- float and RVOL from the fundamentals
cache, news from the headline badge, the catalyst verdict from
``catalysts/live``. A fact nobody holds stays unknown and its pillar fails
with that reason; nothing is guessed in favour of a trade.

Owner: this module (no state of its own). Pure apart from the caches it reads.
"""
from __future__ import annotations

import logging
from typing import Any

from strategy.five_pillars import catalyst_read

logger = logging.getLogger(__name__)

# Board search order: the watchlist's own (a gapper row wins over a gainer row,
# as in ``routes.strategy._watchlist_universe``), then the other boards.
BOARD_ORDER: tuple[str, ...] = ("gappers", "gainers", "losers", "afterhours", "large_cap")
SOURCE_QUOTE = "quote"


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if number == number else None  # NaN is unknown


def raw_boards() -> dict[str, list[dict]]:
    """Every scanner board's cached rows, by name (raw: ``scanner_surface.surface_rows`` decorates them)."""
    from runtime_state import get_runtime_state

    state = get_runtime_state()
    return {
        "gappers": state.gapper_cache,
        "gainers": state.gainer_cache,
        "losers": state.loser_cache,
        "afterhours": state.afterhours_cache,
        "large_cap": state.large_cap_cache,
    }


def live_quote(symbol: str) -> dict | None:
    """The symbol's IBKR L1 quote row, or None when no line holds it."""
    try:
        from ibkr import ticks as _ticks

        return _ticks.last_quotes([symbol]).get(symbol)
    except Exception:
        logger.warning("symbol pillars: L1 quote unreadable for %s", symbol, exc_info=True)
        return None


def find_board_row(symbol: str, boards: dict[str, list[dict]]) -> tuple[dict | None, str | None]:
    """The first board row for ``symbol`` in ``BOARD_ORDER``, with the board's name."""
    for name in BOARD_ORDER:
        for row in boards.get(name) or ():
            if str(row.get("symbol") or "").upper() == symbol:
                return row, name
    return None, None


def quote_row(symbol: str, quote: dict | None) -> dict:
    """A scanner-shaped row from the symbol's L1 quote; every unknown stays None."""
    q = quote or {}
    price = _number(q.get("price"))
    prev_close = _number(q.get("prev_close"))
    volume = _number(q.get("volume"))
    change = price / prev_close - 1.0 if price is not None and prev_close else None
    return {
        "symbol": symbol,
        "price": price,
        "prev_close": prev_close,
        "change_pct": change,
        "volume": int(volume) if volume is not None else None,
    }


def with_catalyst(row: dict) -> dict:
    """The row with today's catalyst verdict when the board did not already carry one."""
    if catalyst_read(row.get("catalyst")):
        return row
    symbol = str(row.get("symbol") or "")
    try:
        from catalysts import live as catalyst_live

        catalyst_live.request([symbol])
        verdict = catalyst_live.verdict_for(symbol)
    except Exception:
        logger.warning("symbol pillars: catalyst verdict failed for %s", symbol, exc_info=True)
        return row
    return {**row, "catalyst": verdict} if isinstance(verdict, dict) else row
