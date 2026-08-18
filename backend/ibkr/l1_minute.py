"""Build live 1Min OHLC from scanner L1 last -- no reqHistoricalData.

Streamed names already pay for ``reqMktData``. Those lasts become live
overlay minutes (source=ibkr_l1) in ``bars_intraday`` so Squeeze seed and
chart 1Min share a path that does not wait on a chart click. Hist fills
own the same candle key and replace the overlay. Producers only mutate
in-memory buckets and enqueue; SQLite stays on the write-queue drain (ADR 010).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from archive.write_queue import enqueue_intraday_bar

logger = logging.getLogger(__name__)

_MINUTE = 60.0


@dataclass
class _Bucket:
    symbol: str
    minute_ts: float
    open: float
    high: float
    low: float
    close: float


_open: dict[str, _Bucket] = {}


def _minute_floor(ts: float) -> float:
    return float(int(ts // _MINUTE) * int(_MINUTE))


def on_last(symbol: str, price: float, ts: float) -> None:
    """Update the open 1Min bucket. Safe to call from the IB loop."""
    sym = (symbol or "").strip().upper()
    if not sym or price <= 0 or ts <= 0:
        return
    minute_ts = _minute_floor(float(ts))
    bucket = _open.get(sym)
    if bucket is None:
        _open[sym] = _Bucket(
            symbol=sym, minute_ts=minute_ts,
            open=float(price), high=float(price),
            low=float(price), close=float(price),
        )
        return
    if minute_ts > bucket.minute_ts:
        _flush(bucket)
        _open[sym] = _Bucket(
            symbol=sym, minute_ts=minute_ts,
            open=float(price), high=float(price),
            low=float(price), close=float(price),
        )
        return
    if minute_ts < bucket.minute_ts:
        return
    bucket.high = max(bucket.high, float(price))
    bucket.low = min(bucket.low, float(price))
    bucket.close = float(price)


def flush_elapsed(now: float) -> None:
    """Persist minutes that already closed even if the name went quiet."""
    cutoff = float(now) - _MINUTE
    for sym, bucket in list(_open.items()):
        if bucket.minute_ts <= cutoff:
            _flush(bucket)
            _open.pop(sym, None)


def _flush(bucket: _Bucket) -> None:
    try:
        enqueue_intraday_bar(
            symbol=bucket.symbol,
            ts=bucket.minute_ts,
            open_=bucket.open,
            high=bucket.high,
            low=bucket.low,
            close=bucket.close,
            volume=0.0,
            timeframe="1Min",
        )
    except Exception:
        logger.exception(
            "l1_minute: enqueue failed for %s @ %s",
            bucket.symbol, bucket.minute_ts,
        )


def reset_for_tests() -> None:
    _open.clear()
