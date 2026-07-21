"""IBKR ticker snapshot helpers — scanner cache reuse + live fallback.

``TickerSnapshotPort`` lives in ``ports.ticker``; the adapter is
``adapters.ibkr_ticker.IbkrTickerSnapshotAdapter``.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from constants import TICKER_IBKR_BRIDGE_TIMEOUT_SEC, TICKER_IBKR_SNAPSHOT_TIMEOUT_SEC
from ports.ticker import TickerSnapshotPort  # noqa: F401 — re-export for callers
from runtime_state import get_runtime_state

logger = logging.getLogger(__name__)


def find_ibkr_cache_row(symbol: str) -> dict | None:
    """Look up a symbol's current row in whichever IBKR-sourced cache has it.

    Gainer/loser rows are checked before gapper rows: gappers stop refreshing
    once the market opens, so a symbol in both caches must resolve to the live
    gainer/loser row (see PROBLEM_LOG 2026-07-13).
    """
    state = get_runtime_state()
    for cache in (state.gainer_cache, state.loser_cache, state.gapper_cache):
        for row in cache:
            if row.get("symbol") == symbol:
                return row
    return None


def _price_from_l1_stream(symbol: str) -> float | None:
    """Last print from an existing Stock View / scanner L1 subscription."""
    try:
        from ibkr import ticks as _ticks

        row = _ticks.last_quotes([symbol]).get((symbol or "").strip().upper())
        if not row:
            return None
        price = row.get("price")
        return float(price) if price is not None else None
    except Exception as exc:
        logger.debug("ticker IBKR L1 lookup failed for %s: %s", symbol, exc)
        return None


def _price_from_chart_bars(symbol: str) -> float | None:
    """Last 1‑min bar close — same feed the Stock View charts already use."""
    try:
        from alpaca import _get_discovery_provider
        from chart_bars import fetch_chart_bars

        payload = fetch_chart_bars(
            symbol,
            timeframe="1Min",
            limit=5,
            discovery_provider=_get_discovery_provider(),
            interactive=True,
        )
        bars = payload.get("bars") or []
        if not bars:
            return None
        close = bars[-1].get("c")
        return float(close) if close is not None else None
    except Exception as exc:
        logger.debug("ticker IBKR chart-bar lookup failed for %s: %s", symbol, exc)
        return None


def _prev_close_from_daily_bars(symbol: str) -> float | None:
    """Prior session close from daily bars (for day change when quote close is missing)."""
    try:
        from alpaca import _get_discovery_provider
        from chart_bars import fetch_chart_bars

        payload = fetch_chart_bars(
            symbol,
            timeframe="1Day",
            limit=3,
            discovery_provider=_get_discovery_provider(),
            interactive=True,
        )
        bars = payload.get("bars") or []
        if len(bars) < 2:
            return None
        # Last daily bar may be today's partial — prior close is the previous bar.
        close = bars[-2].get("c")
        return float(close) if close is not None else None
    except Exception as exc:
        logger.debug("ticker IBKR daily prev_close failed for %s: %s", symbol, exc)
        return None


def fetch_ticker_snapshot_ibkr(symbol: str) -> dict:
    """IBKR counterpart to Alpaca snapshot fetch.

    Reuses the IBKR scanner cache row for symbols already tracked by discovery
    (avoids a redundant IB API call and the stale CLOSE tick issue on repeated
    queries — see PROBLEM_LOG 2026-07-13). Falls back to a live snapshot only
    for symbols not in any scanner cache. Never falls back to Alpaca.

    Price alone is enough for a snapshot (header last). ``prev_close`` is
    optional — without it the UI still shows last, just not day change %.
    """
    cached_row = find_ibkr_cache_row(symbol)
    price = None
    prev_close = None
    volume = 0
    exchange = None
    open_price = None

    if cached_row:
        price = cached_row.get("current_price") or cached_row.get("price")
        prev_close = cached_row.get("previous_close") or cached_row.get("prev_close")
        volume = cached_row.get("volume", 0) or 0
        exchange = cached_row.get("exchange")

    # Fast path before slow reqTickersAsync — Stock View charts already prove
    # bars work when the cold snapshot path returns nothing (e.g. CJMB).
    if price is None:
        price = _price_from_l1_stream(symbol)
    if price is None:
        price = _price_from_chart_bars(symbol)

    # Slow cold snapshot only when we still have no last print.
    if price is None:
        from ibkr import client as _ibkr_client
        from ibkr import discovery as _ibkr_discovery

        try:
            quotes = _ibkr_client.run_coro(
                _ibkr_discovery.snapshot_quotes(
                    [symbol], timeout_sec=TICKER_IBKR_SNAPSHOT_TIMEOUT_SEC
                ),
                timeout=TICKER_IBKR_BRIDGE_TIMEOUT_SEC,
            ) or {}
        except Exception as exc:
            logger.warning("ticker IBKR snapshot failed for %s: %s", symbol, exc)
            quotes = {}
        q = quotes.get(symbol) or quotes.get((symbol or "").strip().upper())
        if q:
            price = q.get("price")
            prev_close = q.get("prev_close")
            volume = q.get("volume", 0) or 0
            exchange = q.get("exchange")
            open_price = q.get("open")

    if price is None:
        return {}

    if prev_close is None:
        prev_close = _prev_close_from_daily_bars(symbol)

    now_iso = datetime.now(timezone.utc).isoformat()
    daily_bar = {
        "open": open_price if open_price and open_price > 0 else None,
        "high": None,
        "low": None,
        "close": price,
        "volume": volume,
        "trade_count": None,
        "vwap": None,
        "timestamp": now_iso,
    }
    prev_daily_bar = None
    if prev_close is not None:
        prev_daily_bar = {
            "open": None,
            "high": None,
            "low": None,
            "close": prev_close,
            "volume": None,
            "trade_count": None,
            "vwap": None,
            "timestamp": None,
        }
    return {
        "latest_trade": {
            "price": price,
            "size": None,
            "exchange": exchange,
            "timestamp": now_iso,
        },
        "latest_quote": None,
        "minute_bar": None,
        "daily_bar": daily_bar,
        "prev_daily_bar": prev_daily_bar,
        "prev_close": prev_close,
        "session_close": prev_close,
        "session_prev_close": None,
    }


def __getattr__(name: str):
    """Lazy re-export to avoid import cycle with ``adapters.ibkr_ticker``."""
    if name == "IbkrTickerSnapshotAdapter":
        from adapters.ibkr_ticker import IbkrTickerSnapshotAdapter

        return IbkrTickerSnapshotAdapter
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
