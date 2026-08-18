"""IBKR L1 ticker-update parsing + quote listener dispatch (split from ticks.py)."""
from __future__ import annotations

import asyncio
import logging
import math
import time
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from constants import IBKR_QUOTE_QUALITY_CLOSE_FALLBACK

logger = logging.getLogger(__name__)

BroadcastFn = Callable[..., Any]
FindCacheRowFn = Callable[[str], Optional[dict]]
QuoteListenerFn = Callable[..., None]

# Wall-clock time of the most recent IBKR event across ALL subscriptions.
# Unlike price-change recency this advances on every ticker event -- the honest
# "is the socket alive" signal for integrity checks.
_last_event_ts: float | None = None


def get_last_event_ts() -> float | None:
    """Wall-clock time of the most recent IBKR event across all streams."""
    return _last_event_ts


def clean(x: float | None) -> float | None:
    if x is None:
        return None
    try:
        return None if math.isnan(x) else float(x)
    except TypeError:
        return None


def exchange_ts_unix(ticker: Any) -> float:
    """Prefer exchange/trade time over the local receive clock (G3)."""
    for attr in ("lastTimestamp", "rtTime", "time"):
        raw = getattr(ticker, attr, None)
        if raw is None:
            continue
        if isinstance(raw, (int, float)):
            val = float(raw)
            if val > 1e12:  # milliseconds
                val /= 1000.0
            if val > 1e9:
                return val
            continue
        try:
            if hasattr(raw, "timestamp"):
                val = float(raw.timestamp())
                if val > 1e9:
                    return val
        except (TypeError, ValueError, OSError, OverflowError):
            continue
    return time.time()


def notify_quote_listeners(
    listeners: list[QuoteListenerFn],
    symbol: str,
    price: float,
    vol_i: int | None,
    prev_close: float | None,
    ts_unix: float,
    *,
    quote_quality: str | None,
) -> None:
    for listener in list(listeners):
        try:
            try:
                listener(
                    symbol,
                    float(price),
                    vol_i,
                    prev_close,
                    ts_unix,
                    quote_quality=quote_quality,
                )
            except TypeError:
                # Legacy 5-arg listeners (no quote_quality kwarg).
                listener(symbol, float(price), vol_i, prev_close, ts_unix)
        except Exception:
            logger.exception("IBKR ticks: quote listener failed for %s", symbol)


def on_ticker_update(
    ticker: Any,
    symbol: str,
    *,
    subs: dict[str, dict[str, Any]],
    quote_listeners: list[QuoteListenerFn],
    find_cache_row: FindCacheRowFn | None,
    broadcast: BroadcastFn | None,
    owner_detail: str,
) -> None:
    """Apply one IBKR ticker event: liveness, day-high, quote listeners, broadcast."""
    global _last_event_ts
    _last_event_ts = time.time()
    sub = subs.get(symbol)
    if sub is not None:
        # Liveness for is_fresh() -- even when price is unchanged.
        sub["last_update_ts"] = time.time()
    last = clean(getattr(ticker, "last", None))
    close = clean(getattr(ticker, "close", None))
    # Tick type 6 = day High (ib_async: ticker.high) -- HOD truth floor.
    day_high = clean(getattr(ticker, "high", None))
    day_high_changed = False
    if sub is not None and day_high is not None and day_high > 0:
        prev_dh = sub.get("day_high")
        if prev_dh != day_high:
            day_high_changed = True
        sub["day_high"] = day_high
    close_fallback = last is None and close is not None
    price = last or close
    if price is None:
        return

    volume = clean(getattr(ticker, "volume", None))
    vol_i = int(volume) if volume is not None else None
    prev_close = close
    row = find_cache_row(symbol) if find_cache_row else None
    if row:
        prev_close = (row.get("previous_close") or row.get("prev_close")) or prev_close
        if vol_i is None and row.get("volume") is not None:
            try:
                vol_i = int(row["volume"])
            except (TypeError, ValueError):
                vol_i = None

    ts_unix = exchange_ts_unix(ticker)
    quote_quality = (
        IBKR_QUOTE_QUALITY_CLOSE_FALLBACK if close_fallback else None
    )
    price_changed = sub is None or sub.get("last_price") != price
    if sub is not None and price_changed:
        sub["last_price"] = price

    # Also notify when day High arrives/raises so HOD can seed without a new last.
    if price_changed or day_high_changed:
        notify_quote_listeners(
            quote_listeners,
            symbol,
            float(price),
            vol_i,
            prev_close,
            ts_unix,
            quote_quality=quote_quality,
        )

    if not price_changed or broadcast is None:
        return
    # Detail panel only needs trade_update when a detail owner is present.
    if sub is not None and owner_detail not in sub.get("owners", set()):
        return
    ts = datetime.now(timezone.utc).isoformat()
    def _broadcast() -> None:
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(broadcast(symbol, price, None, ts, vol_i, prev_close))
        except RuntimeError:
            logger.debug("IBKR ticks: no running loop to broadcast %s", symbol)

    from ibkr.loop_supervisor import is_ib_loop, publish_to_http

    if is_ib_loop():
        publish_to_http(_broadcast)
    else:
        _broadcast()
