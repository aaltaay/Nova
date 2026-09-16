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


def _observe_halt(symbol: str, ticker: Any) -> None:
    """Prefer IBKR tick 49 over tape freeze. Broadcast only on change."""
    from ibkr import halt_status

    _snap, changed = halt_status.observe_from_ticker(symbol, ticker)
    if not changed:
        return
    _broadcast_halt(symbol, _snap)


def _broadcast_halt(symbol: str, halt: dict | None) -> None:
    def _send() -> None:
        try:
            loop = asyncio.get_running_loop()
            from websocket import broadcast_halt_update

            loop.create_task(broadcast_halt_update(symbol, halt))
        except RuntimeError:
            logger.debug("IBKR halt: no running loop to broadcast %s", symbol)

    from ibkr.loop_supervisor import is_ib_loop, publish_to_http

    if is_ib_loop():
        publish_to_http(_send)
    else:
        _send()


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


def l1_size_fields(ticker: Any) -> tuple[float | None, float | None]:
    """lastSize plus cumulative volume from the shared L1 ticker.

    ib_async maps generic tick 233 onto ``lastSize`` and ``rtVolume`` (the
    RTVolume total, not IB's session VWAP). Tick 8 ``volume`` is the fallback
    when 233 is not on the line yet. ``ticker.vwap`` is ignored -- we do not
    invent a second VWAP metric (D-049).
    """
    last_size = clean(getattr(ticker, "lastSize", None))
    rt_volume = clean(getattr(ticker, "rtVolume", None))
    day_volume = clean(getattr(ticker, "volume", None))
    cum = rt_volume if rt_volume is not None else day_volume
    return last_size, cum


def notify_quote_listeners(
    listeners: list[QuoteListenerFn],
    symbol: str,
    price: float,
    vol_i: int | None,
    prev_close: float | None,
    ts_unix: float,
    *,
    quote_quality: str | None,
    open_price: float | None = None,
    last_size: float | None = None,
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
                    open_price=open_price,
                    last_size=last_size,
                )
            except TypeError:
                try:
                    listener(
                        symbol,
                        float(price),
                        vol_i,
                        prev_close,
                        ts_unix,
                        quote_quality=quote_quality,
                        open_price=open_price,
                    )
                except TypeError:
                    try:
                        # Listeners that take quote_quality but not open_price.
                        listener(
                            symbol,
                            float(price),
                            vol_i,
                            prev_close,
                            ts_unix,
                            quote_quality=quote_quality,
                        )
                    except TypeError:
                        # Legacy 5-arg listeners (no keyword extras at all).
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
    # Tick 49 halt can arrive with no last. Observe before the price-none return.
    _observe_halt(symbol, ticker)
    last = clean(getattr(ticker, "last", None))
    close = clean(getattr(ticker, "close", None))
    # Tick type 14 = session OPEN. IB sends it on the same streaming ticker, so
    # Gap % costs no extra request (the COLD snapshot path already reads it --
    # see ibkr/discovery.py snapshot_quotes).
    open_price = clean(getattr(ticker, "open", None))
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

    last_size, cum_volume = l1_size_fields(ticker)
    volume = cum_volume
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

    volume_increased = False
    if sub is not None and cum_volume is not None:
        prev_cum = sub.get("last_cum_volume")
        if prev_cum is not None and cum_volume > prev_cum:
            volume_increased = True
        sub["last_cum_volume"] = cum_volume

    # Also notify when day High arrives/raises so HOD can seed without a new last.
    # Volume-only RTVolume prints keep l1_minute size honest on a flat last.
    if price_changed or day_high_changed or volume_increased:
        notify_quote_listeners(
            quote_listeners,
            symbol,
            float(price),
            vol_i,
            prev_close,
            ts_unix,
            quote_quality=quote_quality,
            open_price=open_price if open_price and open_price > 0 else None,
            last_size=last_size,
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
