"""IBKR ticker snapshot helpers — scanner cache reuse + live fallback.

``TickerSnapshotPort`` lives in ``ports.ticker``; the adapter is
``adapters.ibkr_ticker.IbkrTickerSnapshotAdapter``.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from constants import (
    IBKR_QUOTE_QUALITY_CLOSE_FALLBACK,
    TICKER_IBKR_BRIDGE_TIMEOUT_SEC,
    TICKER_IBKR_SNAPSHOT_TIMEOUT_SEC,
)
from ports.ticker import TickerSnapshotPort  # noqa: F401 — re-export for callers
from runtime_state import get_runtime_state

logger = logging.getLogger(__name__)
ET = ZoneInfo("America/New_York")

# A price and when it traded (epoch seconds, None when unknown).
Traded = tuple[float | None, float | None]


def find_ibkr_cache_row(symbol: str) -> dict | None:
    """Look up a symbol's current row in whichever IBKR-sourced cache has it.

    Gainer/loser rows are checked before gapper rows: gappers stop refreshing
    once the market opens, so a symbol in both caches must resolve to the live
    gainer/loser row (see PROBLEM_LOG 2026-07-13).
    """
    state = get_runtime_state()
    for cache in (
        state.gainer_cache,
        state.loser_cache,
        state.afterhours_cache,
        state.gapper_cache,
    ):
        for row in cache:
            if row.get("symbol") == symbol:
                return row
    return None


def _price_from_l1_stream(symbol: str) -> Traded:
    """Last trade from an existing Stock View / scanner L1 line, with IBKR's Last Timestamp.

    ``(None, None)`` before the line's first trade: its price is then IBKR's
    prior close (``close_fallback``), which is not a trade (#541).
    """
    try:
        from ibkr import ticks as _ticks

        row = _ticks.last_quotes([symbol]).get((symbol or "").strip().upper())
        if not row or row.get("quote_quality") == IBKR_QUOTE_QUALITY_CLOSE_FALLBACK:
            return None, None
        price = row.get("price")
        return (float(price) if price is not None else None), row.get("last_trade_ts")
    except Exception as exc:
        logger.debug("ticker IBKR L1 lookup failed for %s: %s", symbol, exc)
        return None, None


def _bar_epoch(bar: dict) -> float | None:
    raw = bar.get("t")
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00")).timestamp() if raw else None
    except ValueError:
        return None


def _price_from_chart_bars(symbol: str) -> Traded:
    """Today's newest stored 1Min close and its minute -- the store HTTP /bars paints (ADR 012).

    ``fetch_chart_bars(interactive=True)`` on an empty store only schedules a
    fill and returns ``bars=[]``. That made ticker REST miss a last print the
    chart already had (or was about to persist) and fall through to a cold
    ``snapshot_quotes`` that often times out with a blank ``TimeoutError``.
    A bar from an earlier day (last night's 19:59 before today's first trade),
    or one with no time, is not today's last (#541).
    """
    try:
        from bars_store import read

        stored = read((symbol or "").strip().upper(), "1Min", 5)
        bars = (stored or {}).get("bars") or []
        if not bars:
            return None, None
        at = _bar_epoch(bars[-1])
        today = datetime.now(ET).date()
        if at is None or datetime.fromtimestamp(at, ET).date() != today:
            return None, None
        close = bars[-1].get("c")
        return (float(close) if close is not None else None), at
    except Exception as exc:
        from ibkr.errors import describe_exc

        logger.debug(
            "ticker IBKR chart-bar lookup failed for %s: %s",
            symbol,
            describe_exc(exc),
        )
        return None, None


def _prev_close_recorded(symbol: str) -> float | None:
    """IBKR's tick-9 prior close from the symbol's L1 line, else today's leaderboard rows (#542).

    Never a daily bar: the stored daily series is fetched with extended hours
    (``IBKR_HISTORICAL_USE_RTH``), so its close is the last after-hours trade --
    and before today's bar exists ``bars[-2]`` was two sessions back. Unknown is
    ``None``: the quote head then shows no change until the line sends tick 9.
    """
    sym = (symbol or "").strip().upper()
    try:
        from ibkr import ticks as _ticks

        close = (_ticks.last_quotes([sym]).get(sym) or {}).get("prev_close")
        if close is not None:
            return float(close)
    except Exception as exc:
        logger.debug("ticker IBKR L1 prev_close lookup failed for %s: %s", sym, exc)
    from leaderboard import store as leaderboard_store

    return leaderboard_store.day_prev_close(datetime.now(ET).date().isoformat(), sym)


def fetch_ticker_snapshot_ibkr(symbol: str) -> dict:
    """IBKR counterpart to Alpaca snapshot fetch.

    Reuses the IBKR scanner cache row for symbols already tracked by discovery
    (avoids a redundant IB API call and the stale CLOSE tick issue on repeated
    queries — see PROBLEM_LOG 2026-07-13). Falls back to a live snapshot only
    for symbols not in any scanner cache. Never falls back to Alpaca.

    Price alone is enough for a snapshot (header last). ``prev_close`` is
    optional — without it the UI still shows last, just not day change %.
    """
    from sim.mode import is_replay_desk

    if is_replay_desk():
        from sim import market as _sim_market

        return _sim_market.ticker_snapshot(symbol or "")

    cached_row = find_ibkr_cache_row(symbol)
    price: float | None = None
    traded_at: float | None = None
    prev_close = None
    volume = None  # unknown is null, never a placeholder 0 (#541)
    exchange = None
    open_price = None

    if cached_row:
        prev_close = cached_row.get("previous_close") or cached_row.get("prev_close")
        volume = cached_row.get("volume")
        exchange = cached_row.get("exchange")
        open_price = cached_row.get("open")
        # A row repriced before the first trade carries IBKR's prior close; it is not a last (#541).
        if cached_row.get("quote_quality") != IBKR_QUOTE_QUALITY_CLOSE_FALLBACK:
            price = cached_row.get("current_price") or cached_row.get("price")
            traded_at = cached_row.get("quote_ts")

    # Fast path before slow reqTickersAsync -- Stock View charts already prove
    # bars work when the cold snapshot path returns nothing (e.g. CJMB / XAIR).
    if price is None:
        price, traded_at = _price_from_l1_stream(symbol)
    if price is None:
        price, traded_at = _price_from_chart_bars(symbol)

    # Slow cold snapshot only when we still have no last print.
    if price is None:
        from ibkr import client as _ibkr_client
        from ibkr import discovery as _ibkr_discovery
        from ibkr.errors import describe_exc

        try:
            quotes = _ibkr_client.run_coro(
                _ibkr_discovery.snapshot_quotes(
                    [symbol], timeout_sec=TICKER_IBKR_SNAPSHOT_TIMEOUT_SEC
                ),
                timeout=TICKER_IBKR_BRIDGE_TIMEOUT_SEC,
            ) or {}
        except Exception as exc:
            logger.warning(
                "ticker IBKR snapshot failed for %s: %s",
                symbol,
                describe_exc(exc),
            )
            quotes = {}
        q = quotes.get(symbol) or quotes.get((symbol or "").strip().upper())
        if q:
            prev_close = q.get("prev_close") or prev_close
            volume = q.get("volume") if q.get("volume") is not None else volume
            exchange = q.get("exchange") or exchange
            open_price = q.get("open") or open_price
            if q.get("quote_quality") != IBKR_QUOTE_QUALITY_CLOSE_FALLBACK:
                price = q.get("price")  # traded_at stays unknown: the snapshot carries no trade time

    # Chart fill can land while snapshot_quotes is dying -- read the store again.
    if price is None:
        price, traded_at = _price_from_chart_bars(symbol)

    if prev_close is None:
        prev_close = _prev_close_recorded(symbol)

    if price is None and prev_close is None:
        return {}

    # When the last traded, never "now": a snapshot answered from a stored bar or
    # a scanner row is as old as that bar or row, and unknown stays null (#541).
    traded_iso = (
        datetime.fromtimestamp(float(traded_at), timezone.utc).isoformat()
        if traded_at is not None else None
    )
    daily_bar = None
    latest_trade = None
    if price is not None:
        daily_bar = {
            "open": open_price if open_price and open_price > 0 else None,
            "high": None,
            "low": None,
            "close": price,
            "volume": volume,
            "trade_count": None,
            "vwap": None,
            "timestamp": traded_iso,
        }
        latest_trade = {
            "price": price,
            "size": None,
            "exchange": exchange,
            "timestamp": traded_iso,
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
        # ``None`` before today's first trade: the quote head shows the prior
        # close as the prior close, never as a last (#541).
        "latest_trade": latest_trade,
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
