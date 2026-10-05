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

One clock (#721): a print lands in the candle of IBKR's own second for it
(``exchange_ts``), the clock IBKR's historical 10-second bars use, so the hist
fill that replaces these candles moves none of them; the arrival time is the
fallback when IBKR's second is missing. IBKR delivers prints in the order of that
second (1,219,396 recorded prints in October, none out of order), so a candle never
takes a print after the next one opened. A quiet symbol's bucket is flushed
TAPE_10SEC_FLUSH_GRACE_SEC after its ten seconds end, and a print for a bucket
already flushed is dropped: it never reopens a closed candle.

Producers (``tape_stream._on_tape_update``, on the IB socket callback) only
mutate in-memory buckets and enqueue; SQLite stays on the write-queue drain
(ADR 010) -- see PROBLEM_LOG 2026-08-18 archive-write IB-loop starvation for
why a synchronous write here is forbidden.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from archive.write_queue import enqueue_intraday_bar
from constants_tape import TAPE_10SEC_FLUSH_GRACE_SEC

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
# symbol -> the newest bucket already flushed: a later print for it, or for an older one, is dropped.
_closed: dict[str, float] = {}


def _bucket_floor(ts: float) -> float:
    return float(int(ts // _BUCKET_SEC) * int(_BUCKET_SEC))


def on_print(symbol: str, price: float, size: float, ts: float, exchange_ts: float | None = None) -> None:
    """Update the open 10Sec bucket from one tape print. Safe on the IB loop.

    ``exchange_ts`` is IBKR's own second for the print; ``ts`` (arrival) keys it when that is missing.
    """
    sym = (symbol or "").strip().upper()
    key_ts = exchange_ts if isinstance(exchange_ts, (int, float)) and exchange_ts > 0 else ts
    if not sym or price <= 0 or key_ts <= 0:
        return
    size = max(0.0, float(size or 0.0))
    bucket_ts = _bucket_floor(float(key_ts))
    if bucket_ts <= _closed.get(sym, float("-inf")):
        return  # its candle is closed and stored: never reopened
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
    """Persist buckets that already closed even if the symbol went quiet (after the late-print grace)."""
    cutoff = float(now) - _BUCKET_SEC - TAPE_10SEC_FLUSH_GRACE_SEC
    for sym, bucket in list(_open.items()):
        if bucket.bucket_ts <= cutoff:
            _flush(bucket)
            _open.pop(sym, None)


def _flush(bucket: _Bucket) -> None:
    _closed[bucket.symbol] = max(_closed.get(bucket.symbol, float("-inf")), bucket.bucket_ts)
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
    _closed.clear()
