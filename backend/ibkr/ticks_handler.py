"""IBKR L1 ticker-update parsing + quote listener dispatch (split from ticks.py)."""
from __future__ import annotations

import asyncio
import logging
import math
import time
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from constants import IBKR_QUOTE_QUALITY_CLOSE_FALLBACK
from constants_tape import IBKR_LAST_TICK_TYPES
from ibkr.open_tick import todays_open
from metrics.op_metrics import timed_fn

logger = logging.getLogger(__name__)


def _observe_halt(symbol: str, ticker: Any) -> None:
    """Prefer ticker.halted (incoming tick type 49) over tape freeze."""
    from ibkr import halt_status

    _snap, changed = halt_status.observe_from_ticker(symbol, ticker)
    if not changed:
        return
    try:
        # Halt / LULD log (ADR 023): enqueue only -- this can run on the IB loop.
        from leaderboard import halts as _halt_log

        _halt_log.observe_ibkr(symbol, _snap)
    except Exception:
        logger.warning("IBKR halt: event log enqueue failed for %s", symbol, exc_info=True)
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


def _epoch(raw: Any) -> float | None:
    """A ticker timestamp (datetime or epoch seconds / ms) as epoch seconds, else None."""
    if raw is None:
        return None
    if hasattr(raw, "timestamp"):
        try:
            return float(raw.timestamp())
        except (TypeError, ValueError, OSError, OverflowError):
            return None
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return None
    if val > 1e12:  # milliseconds
        val /= 1000.0
    return val if val > 1e9 else None


def note_last_trade(ticker: Any, sub: dict[str, Any] | None) -> None:
    """When the line's last trade happened: IBKR's Last Timestamp (tick 45, or 88 delayed).

    A Last tick arriving is not a new trade -- IBKR sends the current last when
    a line opens, hours after it printed -- and ``last_update_ts`` moves on any
    quote change. Paper fills need the trade's own time (#541). Unknown stays
    unknown: without a timestamp the practice broker falls back to the tape.
    """
    if sub is None:
        return
    for attr in ("lastTimestamp", "delayedLastTimestamp"):
        stamp = _epoch(getattr(ticker, attr, None))
        if stamp is not None:
            sub["last_trade_ts"] = stamp
            return


def reportable_last(ticker: Any, sub: dict[str, Any] | None) -> float | None:
    """IBKR's Last (tick 4 / 68) from this update, else the last one this line delivered.

    ib_async keeps one Ticker per contract and writes ``ticker.last`` from
    tick 4, from RTVolume 233 (unreported trades included) and from every
    AllLast print, so an odd lot or an average-price print $2 away became the
    desk's last and painted a candle wick (2026-09-23). Only tick 4 is a last.
    A line that has not delivered one yet (a seed) keeps ``ticker.last``.
    """
    fresh = None
    for tick in getattr(ticker, "ticks", None) or ():
        if getattr(tick, "tickType", None) in IBKR_LAST_TICK_TYPES:
            price = clean(getattr(tick, "price", None))
            if price is not None and price > 0:
                fresh = price
    if fresh is not None:
        if sub is not None:
            sub["reportable_last"] = fresh
        return fresh
    if sub is not None and sub.get("reportable_last") is not None:
        return sub["reportable_last"]
    return clean(getattr(ticker, "last", None))


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


@timed_fn("ib.l1")
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
    # ticker.halted can arrive with no last. Observe before the price-none return.
    _observe_halt(symbol, ticker)
    last = reportable_last(ticker, sub)
    close = clean(getattr(ticker, "close", None))
    # Tick type 14 = session OPEN. IB sends it on the same streaming ticker, so
    # Gap % costs no extra request (the COLD snapshot path already reads it --
    # see ibkr/discovery.py snapshot_quotes). Before 09:30 ET it is the
    # previous session's open, so it is dropped until today's session opens.
    open_price = todays_open(clean(getattr(ticker, "open", None)))
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
    note_last_trade(ticker, sub)

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
    if sub is not None:
        if price_changed:
            sub["last_price"] = price
        # Readers of ``last_price`` must know it is IBKR's prior close, not a trade (#541).
        sub["quote_quality"] = quote_quality

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
    if close_fallback:
        # Nothing has traded: the prior close is not a trade update, and a chart
        # tip painted from it drew a candle no exchange printed (#541).
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
