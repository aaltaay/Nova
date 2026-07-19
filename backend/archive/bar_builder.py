"""Build 1-minute OHLCV bars from IBKR tape prints (archive integrity).

Tape was already archived; bars_1m had no production writer. This module
aggregates prints into minute buckets and flushes completed minutes via
``record_bar``. Also supports offline backfill from ``tape_ibkr``.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

from archive.capture import record_bar, session_date_for_ts
from constants import ARCHIVE_SOURCE_IBKR

logger = logging.getLogger(__name__)

_MINUTE = 60.0


@dataclass
class _Bucket:
    symbol: str
    minute_ts: float  # floor of epoch minute
    open: float
    high: float
    low: float
    close: float
    volume: float
    source: str


_open: dict[tuple[str, str], _Bucket] = {}  # (symbol, source) → current minute


def _minute_floor(ts: float) -> float:
    return float(int(ts // _MINUTE) * int(_MINUTE))


def on_tape_print(
    *,
    symbol: str,
    ts: float,
    price: float,
    size: float = 0.0,
    source: str = ARCHIVE_SOURCE_IBKR,
) -> None:
    """Update the open 1m bucket; flush prior minute when the clock rolls."""
    symbol = symbol.upper()
    if price <= 0 or ts <= 0:
        return
    key = (symbol, source)
    minute_ts = _minute_floor(ts)
    bucket = _open.get(key)
    if bucket is None:
        _open[key] = _Bucket(
            symbol=symbol, minute_ts=minute_ts,
            open=price, high=price, low=price, close=price,
            volume=max(0.0, float(size)), source=source,
        )
        return
    if minute_ts > bucket.minute_ts:
        _flush(bucket)
        _open[key] = _Bucket(
            symbol=symbol, minute_ts=minute_ts,
            open=price, high=price, low=price, close=price,
            volume=max(0.0, float(size)), source=source,
        )
        return
    if minute_ts < bucket.minute_ts:
        # Late print for an older minute — write a one-print bar (idempotent upsert).
        record_bar(
            symbol=symbol, ts=minute_ts, open_=price, high=price,
            low=price, close=price, volume=max(0.0, float(size)),
            timeframe="1m", source=source,
        )
        return
    bucket.high = max(bucket.high, price)
    bucket.low = min(bucket.low, price)
    bucket.close = price
    bucket.volume += max(0.0, float(size))


def flush_symbol(symbol: str, *, source: str = ARCHIVE_SOURCE_IBKR) -> None:
    key = (symbol.upper(), source)
    bucket = _open.pop(key, None)
    if bucket is not None:
        _flush(bucket)


def flush_all() -> int:
    n = 0
    for key in list(_open.keys()):
        bucket = _open.pop(key, None)
        if bucket is not None:
            _flush(bucket)
            n += 1
    return n


def _flush(bucket: _Bucket) -> None:
    try:
        record_bar(
            symbol=bucket.symbol,
            ts=bucket.minute_ts,
            open_=bucket.open,
            high=bucket.high,
            low=bucket.low,
            close=bucket.close,
            volume=bucket.volume,
            timeframe="1m",
            source=bucket.source,
            session_date=session_date_for_ts(bucket.minute_ts),
        )
    except Exception:
        logger.exception(
            "archive.bar_builder: failed to flush 1m bar %s @ %s",
            bucket.symbol, bucket.minute_ts,
        )


def backfill_from_tape_rows(rows: list[dict[str, Any]]) -> int:
    """Build bars from ordered tape rows. Returns number of bars flushed."""
    reset_for_tests()
    # Sort by symbol then ts so buckets roll correctly.
    ordered = sorted(
        rows,
        key=lambda r: (str(r.get("symbol") or ""), float(r.get("ts") or 0)),
    )
    for r in ordered:
        try:
            on_tape_print(
                symbol=str(r["symbol"]),
                ts=float(r["ts"]),
                price=float(r["price"]),
                size=float(r.get("size") or 0),
                source=str(r.get("source") or ARCHIVE_SOURCE_IBKR),
            )
        except (KeyError, TypeError, ValueError):
            continue
    return flush_all()


def backfill_session_date(session_date: str) -> int:
    """Read hot ``tape_ibkr`` for a session date and write ``bars_1m``."""
    from archive import db as archive_db

    conn = archive_db.get_connection()
    try:
        cur = conn.execute(
            """
            SELECT symbol, ts, price, size, source
            FROM tape_ibkr
            WHERE session_date = ?
            ORDER BY symbol, ts
            """,
            (session_date,),
        )
        rows = [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()
    if not rows:
        return 0
    return backfill_from_tape_rows(rows)


def reset_for_tests() -> None:
    _open.clear()
