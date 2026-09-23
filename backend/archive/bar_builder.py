"""Build 1-minute OHLCV bars from IBKR tape prints (archive integrity).

Tape was already archived; bars_1m had no production writer. This module
aggregates prints into minute buckets and flushes completed minutes via
``record_bar``. Also supports offline backfill from ``tape_ibkr``.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from archive.capture import record_bar, session_date_for_ts
from constants import ARCHIVE_SOURCE_IBKR
from sale_conditions import row_sets_price

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
    queued: bool = False,
) -> None:
    """Update the open 1m bucket; flush prior minute when the clock rolls.

    Live tape callers pass ``queued=True`` -- they run on the IB loop and must
    not block on SQLite (ADR 010).
    """
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
        _flush(bucket, queued=queued)
        _open[key] = _Bucket(
            symbol=symbol, minute_ts=minute_ts,
            open=price, high=price, low=price, close=price,
            volume=max(0.0, float(size)), source=source,
        )
        return
    if minute_ts < bucket.minute_ts:
        # Late print for an older minute — write a one-print bar (idempotent upsert).
        _flush(
            _Bucket(
                symbol=symbol, minute_ts=minute_ts, open=price, high=price,
                low=price, close=price, volume=max(0.0, float(size)),
                source=source,
            ),
            queued=queued,
        )
        return
    bucket.high = max(bucket.high, price)
    bucket.low = min(bucket.low, price)
    bucket.close = price
    bucket.volume += max(0.0, float(size))


def flush_elapsed(now: float, *, queued: bool = True) -> int:
    """Flush minutes that already closed even if the tape went quiet (D-024)."""
    cutoff = float(now) - _MINUTE
    n = 0
    for key, bucket in list(_open.items()):
        if bucket.minute_ts <= cutoff:
            _open.pop(key, None)
            _flush(bucket, queued=queued)
            n += 1
    return n


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


def _flush(bucket: _Bucket, *, queued: bool = False) -> None:
    """Persist a completed minute.

    ``queued=True`` is the live path: minute rollover is reached from the IB
    socket callback, where a blocking SQLite write starves market data
    (ADR 010). Offline backfill/rollup keeps the direct write so callers can
    read the rows back immediately.
    """
    try:
        if queued:
            from archive.write_queue import enqueue_bar

            write = enqueue_bar
        else:
            write = record_bar
        write(
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
    """Build bars from ordered tape rows. Returns number of bars flushed.

    Only prints that set a price make a bar (``sale_conditions.py``), as live.
    """
    reset_for_tests()
    # Sort by symbol then ts so buckets roll correctly.
    ordered = sorted(
        (r for r in rows if row_sets_price(r)),
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
            SELECT symbol, ts, price, size, conditions, source
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


def rollup_daily(session_date: str) -> int:
    """Aggregate ``bars_1m`` for one session into ``bars_1d``. Returns bars written."""
    from archive import db as archive_db

    if not session_date:
        return 0
    conn = archive_db.get_connection()
    try:
        rows = conn.execute(
            """
            SELECT symbol, ts, open, high, low, close, volume, source
            FROM bars_1m
            WHERE session_date = ?
            ORDER BY symbol, source, ts
            """,
            (session_date,),
        ).fetchall()
    finally:
        conn.close()
    groups: dict[tuple[str, str], dict] = {}
    for row in rows:
        key = (str(row["symbol"]), str(row["source"] or ARCHIVE_SOURCE_IBKR))
        bucket = groups.get(key)
        ts = float(row["ts"])
        high = float(row["high"])
        low = float(row["low"])
        close = float(row["close"])
        volume = float(row["volume"] or 0)
        if bucket is None:
            groups[key] = {
                "ts": ts,
                "open": float(row["open"]),
                "high": high,
                "low": low,
                "close": close,
                "volume": volume,
            }
            continue
        bucket["high"] = max(bucket["high"], high)
        bucket["low"] = min(bucket["low"], low)
        bucket["close"] = close
        bucket["volume"] += volume
    for (symbol, source), bucket in groups.items():
        record_bar(
            symbol=symbol,
            ts=bucket["ts"],
            open_=bucket["open"],
            high=bucket["high"],
            low=bucket["low"],
            close=bucket["close"],
            volume=bucket["volume"],
            timeframe="1d",
            source=source,
            session_date=session_date,
        )
    return len(groups)


def reset_for_tests() -> None:
    _open.clear()
