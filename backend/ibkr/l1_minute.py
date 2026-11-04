"""Build live 1Min OHLC from scanner L1 last -- no reqHistoricalData.

Streamed names already pay for ``reqMktData``. Those lasts become live
overlay minutes (source=ibkr_l1) in ``bars_intraday`` so Squeeze seed and
chart 1Min share a path that does not wait on a chart click. Hist fills
own the same candle key and replace the overlay. Producers only mutate
in-memory buckets and enqueue; SQLite stays on the write-queue drain (ADR 010).

Volume is a delta of the shared L1 line (lastSize / RTVolume 233 / tick-8),
not a second ``reqMktData`` and not a dumped day total (D-049 / D-020).

Only a last inside Nova's trading session makes a minute (04:00-20:00 ET on an
exchange day, ``market.in_trading_session``). After the 20:00 close IBKR keeps
the same lines moving with its overnight session (20:00-03:50 ET), trades it
dates to the next trading day; as minutes they drew candles no IBKR bar holds
and fed the setup scanner a "new high of day" at 20:48 (OM, 2026-10-01).

Every write is the minute's whole count (operator report, 2026-11-04). An update
lands in the minute of IBKR's last-trade second, which trails its arrival (CRIS:
0.76 s at the median, 13 s at most), while a quiet minute is written by the desk's
clock once it ends. So the newest minute stays in memory after it is written: an
update that arrives later joins it and the whole minute is written again. It used
to open a fresh bucket holding only that update, whose write replaced the minute's
volume -- 174 of CRIS's 271 minutes that morning showed one or two updates' shares
(04:00: 641 where IBKR's day volume grew 130,136). An update stamped before the
newest minute never reopens a closed candle; its shares count in the newest one.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Callable
from zoneinfo import ZoneInfo

from archive.write_queue import enqueue_intraday_bar
from market import in_trading_session

logger = logging.getLogger(__name__)

_MINUTE = 60.0
_ET = ZoneInfo("America/New_York")


@dataclass
class _Bucket:
    symbol: str
    minute_ts: float
    open: float
    high: float
    low: float
    close: float
    volume: float
    # Changed since it was last written. A written minute stays here until a newer one opens.
    dirty: bool = True
    # Listeners heard it close: they hear a minute once, later shares only rewrite the stored row.
    heard: bool = False


_open: dict[str, _Bucket] = {}
_last_cum_volume: dict[str, float] = {}
# Consumers of live minutes (the setup scanner, ADR 022). Called on the IB loop:
# a listener must only enqueue -- never block, never touch SQLite (ADR 010).
Listener = Callable[[str, str, dict], None]
_listeners: list[Listener] = []


def add_listener(fn: Listener) -> None:
    """Hear ``("last", SYM, {price, ts, bar_open})`` and ``("bar", SYM, {t,o,h,l,c,v})``."""
    if fn not in _listeners:
        _listeners.append(fn)


def remove_listener(fn: Listener) -> None:
    if fn in _listeners:
        _listeners.remove(fn)


def _emit(kind: str, symbol: str, payload: dict) -> None:
    for fn in list(_listeners):
        try:
            fn(kind, symbol, payload)
        except Exception:
            logger.exception("l1_minute: listener failed for %s %s", kind, symbol)


def _minute_floor(ts: float) -> float:
    return float(int(ts // _MINUTE) * int(_MINUTE))


def volume_increment(
    prior_cum: float | None,
    *,
    size: float | None,
    cum_volume: float | None,
) -> tuple[float, float | None]:
    """Return ``(increment, new_prior_cum)`` for one L1 print.

    The first cumulative print is a baseline so a 5M day total cannot land
    on the open minute. After that, only the delta counts. A drop in the
    cumulative (session reset) re-baselines and keeps this print's size.
    lastSize is the fallback when there is no cumulative yet, or right
    after a reset / first observation.
    """
    size_f = float(size) if size is not None and size > 0 else 0.0
    if cum_volume is None or cum_volume < 0:
        return size_f, prior_cum
    cum = float(cum_volume)
    if prior_cum is None:
        return size_f, cum
    if cum < prior_cum:
        return size_f, cum
    if cum > prior_cum:
        return cum - prior_cum, cum
    return 0.0, cum


def on_last(
    symbol: str,
    price: float,
    ts: float,
    *,
    size: float | None = None,
    cum_volume: float | None = None,
) -> None:
    """Update the symbol's newest 1Min bucket. Safe to call from the IB loop.

    A last outside the trading session is no minute of Nova's (the module note): it opens no
    bucket, reaches no listener and drops the volume baseline, so the next session's first
    print is a baseline again.
    """
    sym = (symbol or "").strip().upper()
    if not sym or price <= 0 or ts <= 0:
        return
    if not in_trading_session(float(ts)):
        _last_cum_volume.pop(sym, None)
        return
    increment, new_cum = volume_increment(
        _last_cum_volume.get(sym),
        size=size,
        cum_volume=cum_volume,
    )
    if new_cum is None:
        _last_cum_volume.pop(sym, None)
    else:
        _last_cum_volume[sym] = new_cum
    minute_ts = _minute_floor(float(ts))
    bucket = _open.get(sym)
    if bucket is None or minute_ts > bucket.minute_ts:
        if bucket is not None and bucket.dirty:
            _flush(bucket)
        _open[sym] = _Bucket(
            symbol=sym, minute_ts=minute_ts,
            open=float(price), high=float(price),
            low=float(price), close=float(price),
            volume=increment,
        )
        _emit_last(sym, price, ts)
        return
    if minute_ts < bucket.minute_ts:
        # Its candle is closed and never reopened; the shares are real and count in the newest minute.
        if increment > 0:
            bucket.volume += increment
            bucket.dirty = True
        return
    # The newest minute, written already or not: it takes the update, and its next write is whole.
    bucket.high = max(bucket.high, float(price))
    bucket.low = min(bucket.low, float(price))
    bucket.close = float(price)
    bucket.volume += increment
    bucket.dirty = True
    _emit_last(sym, price, ts)


def _emit_last(sym: str, price: float, ts: float) -> None:
    if _listeners:
        bucket = _open.get(sym)
        _emit("last", sym, {"price": float(price), "ts": float(ts),
                            "bar_open": bucket.open if bucket else float(price)})


def flush_elapsed(now: float) -> None:
    """Write minutes that ended and changed since their last write, even if the name went quiet.

    A written minute stays for an update that arrives after it. One from an earlier day than
    ``now`` is let go: IBKR repeats a line's last trade on the new day's first update, and that
    stale stamp must not add a trade's shares to yesterday's last minute.
    """
    cutoff = float(now) - _MINUTE
    day = datetime.fromtimestamp(float(now), _ET).date()
    midnight = datetime(day.year, day.month, day.day, tzinfo=_ET).timestamp()
    for sym, bucket in list(_open.items()):
        if bucket.dirty and bucket.minute_ts <= cutoff:
            _flush(bucket)
        if not bucket.dirty and bucket.minute_ts < midnight:
            _open.pop(sym, None)


def _flush(bucket: _Bucket) -> None:
    bucket.dirty = False
    if not bucket.heard:
        bucket.heard = True
        if _listeners:
            _emit("bar", bucket.symbol, {"t": bucket.minute_ts, "o": bucket.open, "h": bucket.high,
                                         "l": bucket.low, "c": bucket.close, "v": float(bucket.volume)})
    try:
        enqueue_intraday_bar(
            symbol=bucket.symbol,
            ts=bucket.minute_ts,
            open_=bucket.open,
            high=bucket.high,
            low=bucket.low,
            close=bucket.close,
            volume=float(bucket.volume),
            timeframe="1Min",
        )
    except Exception:
        logger.exception(
            "l1_minute: enqueue failed for %s @ %s",
            bucket.symbol, bucket.minute_ts,
        )


def reset_for_tests() -> None:
    _open.clear()
    _last_cum_volume.clear()
