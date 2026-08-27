"""Build live 10-second OHLCV from IBKR tape prints -- no reqHistoricalData.

Trader symbols already pay for ``reqTickByTickData`` (AllLast) once a chart
tab is open (``tape_stream.py``). Those prints become live overlay 10Sec
candles (source=``ibkr_l1``) in ``bars_intraday`` so the 10Sec pane paints
within a few seconds of open instead of waiting on the paced 4-hour IB
historical fill (ADR 012). The hist fill still lands and always replaces the
same candle key (``bars_store._HIST_UPSERT_SQL``) -- provisional bars never
fake completeness: ``store_series_complete("10Sec", n)`` needs >=
``IBKR_BARS_STORE_MIN_BARS["10Sec"]`` (100) bars, which tape-only buckets
will not reach for a quiet name.

Producers (``tape_stream._on_tape_update``, on the IB socket callback) only
mutate in-memory buckets and enqueue; SQLite stays on the write-queue drain
(ADR 010) -- see PROBLEM_LOG 2026-08-18 archive-write IB-loop starvation for
why a synchronous write here is forbidden.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from archive.write_queue import enqueue_intraday_bar

logger = logging.getLogger(__name__)

_BUCKET_SEC = 10.0
_TIMEFRAME = "10Sec"


@dataclass
class _Bucket:
    symbol: str
    bucket_ts: float
    open: float
    high: float
    low: float
    close: float
    volume: float


_open: dict[str, _Bucket] = {}


def _bucket_floor(ts: float) -> float:
    return float(int(ts // _BUCKET_SEC) * int(_BUCKET_SEC))


def on_print(symbol: str, price: float, size: float, ts: float) -> None:
    """Update the open 10Sec bucket from one tape print. Safe on the IB loop."""
    sym = (symbol or "").strip().upper()
    if not sym or price <= 0 or ts <= 0:
        return
    size = max(0.0, float(size or 0.0))
    bucket_ts = _bucket_floor(float(ts))
    bucket = _open.get(sym)
    if bucket is None:
        _open[sym] = _Bucket(
            symbol=sym, bucket_ts=bucket_ts,
            open=float(price), high=float(price),
            low=float(price), close=float(price), volume=size,
        )
        return
    if bucket_ts > bucket.bucket_ts:
        _flush(bucket)
        _open[sym] = _Bucket(
            symbol=sym, bucket_ts=bucket_ts,
            open=float(price), high=float(price),
            low=float(price), close=float(price), volume=size,
        )
        return
    if bucket_ts < bucket.bucket_ts:
        return
    bucket.high = max(bucket.high, float(price))
    bucket.low = min(bucket.low, float(price))
    bucket.close = float(price)
    bucket.volume += size


def flush_elapsed(now: float) -> None:
    """Persist buckets that already closed even if the symbol went quiet."""
    cutoff = float(now) - _BUCKET_SEC
    for sym, bucket in list(_open.items()):
        if bucket.bucket_ts <= cutoff:
            _flush(bucket)
            _open.pop(sym, None)


def _flush(bucket: _Bucket) -> None:
    try:
        enqueue_intraday_bar(
            symbol=bucket.symbol,
            ts=bucket.bucket_ts,
            open_=bucket.open,
            high=bucket.high,
            low=bucket.low,
            close=bucket.close,
            volume=bucket.volume,
            timeframe=_TIMEFRAME,
        )
    except Exception:
        logger.exception(
            "tape_10sec: enqueue failed for %s @ %s",
            bucket.symbol, bucket.bucket_ts,
        )


def reset_for_tests() -> None:
    _open.clear()
