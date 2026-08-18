"""Non-blocking archive writes -- keep SQLite off the IB event loop (ADR 010).

Tape prints and L1 ticks arrive *inside* ``ib_async`` socket callbacks, i.e. on
the IB event loop. Writing them straight to SQLite there placed a full
``sqlite3.connect`` + 3 PRAGMAs + INSERT + ``commit`` -- twice per row, counting
the integrity counter -- in front of every ``reqMktData`` tick. One
high-print runner was enough to starve L1 for the whole desk
(2026-08-18 wedge: ``ib_loop_lag_ms`` 45,094ms while the HTTP loop idled at
11ms; scanner prices and chart live tips froze).

Split the responsibility:

* **Producers** (IB loop) call ``enqueue_*``: pure in-memory, O(1), and the
  lock is held for microseconds -- never for disk I/O.
* **One writer** drains batches off the IB loop, using a single connection and
  a single transaction per batch.

The queue is bounded. Overflow drops the *oldest* rows and counts them under
``ARCHIVE_COUNTER_TAPE_DROPPED`` so loss stays visible instead of silently
growing RAM or wedging the loop again.
"""
from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections import deque

from constants import (
    ARCHIVE_COUNTER_BARS_1D,
    ARCHIVE_COUNTER_BARS_1M,
    ARCHIVE_COUNTER_L1_TICKS,
    ARCHIVE_COUNTER_TAPE_DROPPED,
    ARCHIVE_COUNTER_TAPE_RECEIVED,
    ARCHIVE_SOURCE_IBKR,
    ARCHIVE_WRITE_BATCH_MAX,
    ARCHIVE_WRITE_FLUSH_SEC,
    ARCHIVE_WRITE_QUEUE_MAX,
)

logger = logging.getLogger(__name__)

_TAPE_SQL = """
INSERT INTO tape_ibkr
    (symbol, ts, price, size, exchange, conditions, side,
     bid, ask, seq, receive_ts, source, session_date)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

_L1_SQL = """
INSERT INTO l1_ticks
    (symbol, ts, price, volume, day_high, session_date)
VALUES (?, ?, ?, ?, ?, ?)
"""

_COUNTER_SQL = """
INSERT INTO integrity_counters (name, value, updated_ts)
VALUES (?, ?, ?)
ON CONFLICT(name) DO UPDATE SET
    value = value + excluded.value,
    updated_ts = excluded.updated_ts
"""


def _bar_sql(table: str) -> str:
    return f"""
    INSERT INTO {table}
        (symbol, ts, open, high, low, close, volume, source, session_date)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(symbol, ts, source) DO UPDATE SET
        open = excluded.open,
        high = excluded.high,
        low = excluded.low,
        close = excluded.close,
        volume = excluded.volume,
        session_date = excluded.session_date
    """


_lock = threading.Lock()
_tape: deque[tuple] = deque()
_l1: deque[tuple] = deque()
_bars_1m: deque[tuple] = deque()
_bars_1d: deque[tuple] = deque()
_dropped = 0

_QUEUES: tuple[deque, ...] = (_tape, _l1, _bars_1m, _bars_1d)


def _append(queue: deque, row: tuple) -> None:
    """Bounded append. Caller must be cheap -- this runs on the IB loop."""
    global _dropped
    with _lock:
        if sum(len(q) for q in _QUEUES) >= ARCHIVE_WRITE_QUEUE_MAX:
            # Shed the longest queue so one noisy stream cannot evict another.
            victim = max(_QUEUES, key=len)
            if victim:
                victim.popleft()
                _dropped += 1
        queue.append(row)


def enqueue_tape_print(
    *,
    symbol: str,
    ts: float,
    price: float,
    size: float,
    exchange: str = "",
    conditions: str = "",
    side: str | None = None,
    bid: float | None = None,
    ask: float | None = None,
    seq: int | None = None,
    receive_ts: float | None = None,
    source: str = ARCHIVE_SOURCE_IBKR,
    session_date: str | None = None,
) -> None:
    """Queue one time & sales print. Safe to call from the IB loop."""
    from archive.capture import session_date_for_ts

    recv = receive_ts if receive_ts is not None else time.time()
    _append(_tape, (
        symbol.upper(), float(ts), float(price), float(size),
        exchange or "", conditions or "", side,
        bid, ask, seq, float(recv), source,
        session_date or session_date_for_ts(ts),
    ))


def enqueue_l1_tick(
    *,
    symbol: str,
    ts: float,
    price: float,
    volume: float | None = None,
    day_high: float | None = None,
    session_date: str | None = None,
) -> None:
    """Queue one HOD-decision L1 tick. Safe to call from the IB loop."""
    if ts <= 0:
        return
    from archive.capture import session_date_for_ts

    _append(_l1, (
        symbol.upper(), float(ts), float(price),
        float(volume) if volume is not None else None,
        float(day_high) if day_high is not None else None,
        session_date or session_date_for_ts(ts),
    ))


def enqueue_bar(
    *,
    symbol: str,
    ts: float,
    open_: float,
    high: float,
    low: float,
    close: float,
    volume: float = 0.0,
    timeframe: str = "1m",
    source: str = ARCHIVE_SOURCE_IBKR,
    session_date: str | None = None,
) -> None:
    """Queue one OHLC bar. Safe to call from the IB loop (minute rollover)."""
    from archive.capture import session_date_for_ts

    if timeframe == "1m":
        queue = _bars_1m
    elif timeframe == "1d":
        queue = _bars_1d
    else:
        raise ValueError(f"unsupported bar timeframe: {timeframe}")
    _append(queue, (
        symbol.upper(), float(ts), float(open_), float(high), float(low),
        float(close), float(volume), source,
        session_date or session_date_for_ts(ts),
    ))


def pending() -> int:
    with _lock:
        return sum(len(q) for q in _QUEUES)


def stats() -> dict[str, int]:
    with _lock:
        return {
            "tape": len(_tape),
            "l1": len(_l1),
            "bars_1m": len(_bars_1m),
            "bars_1d": len(_bars_1d),
            "dropped_pending": _dropped,
        }


def _take(queue: deque, budget: int) -> list[tuple]:
    return [queue.popleft() for _ in range(min(len(queue), budget))]


def drain_once() -> dict[str, int]:
    """Write one batch. BLOCKING SQLite -- never call this on the IB loop."""
    global _dropped
    with _lock:
        tape = _take(_tape, ARCHIVE_WRITE_BATCH_MAX)
        l1 = _take(_l1, ARCHIVE_WRITE_BATCH_MAX)
        bars_1m = _take(_bars_1m, ARCHIVE_WRITE_BATCH_MAX)
        bars_1d = _take(_bars_1d, ARCHIVE_WRITE_BATCH_MAX)
        dropped = _dropped
        _dropped = 0

    written = {
        "tape": len(tape), "l1": len(l1),
        "bars_1m": len(bars_1m), "bars_1d": len(bars_1d),
        "dropped": dropped,
    }
    if not any(written.values()):
        return written
    try:
        _write_batch(tape, l1, bars_1m, bars_1d, dropped)
    except Exception:
        # Non-fatal for live UI (archive policy) but must never be silent.
        logger.exception(
            "archive.write_queue: batch write failed -- lost %d tape / %d l1 / "
            "%d 1m / %d 1d rows",
            len(tape), len(l1), len(bars_1m), len(bars_1d),
        )
        return {**written, "failed": sum(
            (len(tape), len(l1), len(bars_1m), len(bars_1d)),
        )}
    return written


def _write_batch(
    tape: list[tuple],
    l1: list[tuple],
    bars_1m: list[tuple],
    bars_1d: list[tuple],
    dropped: int,
) -> None:
    from archive import db as archive_db

    conn = archive_db.get_connection()
    try:
        if tape:
            conn.executemany(_TAPE_SQL, tape)
        if l1:
            conn.executemany(_L1_SQL, l1)
        if bars_1m:
            conn.executemany(_bar_sql("bars_1m"), bars_1m)
        if bars_1d:
            conn.executemany(_bar_sql("bars_1d"), bars_1d)
        counters: list[tuple[str, int, float]] = []
        now = time.time()
        for name, count in (
            (ARCHIVE_COUNTER_TAPE_RECEIVED, len(tape)),
            (ARCHIVE_COUNTER_L1_TICKS, len(l1)),
            (ARCHIVE_COUNTER_BARS_1M, len(bars_1m)),
            (ARCHIVE_COUNTER_BARS_1D, len(bars_1d)),
            (ARCHIVE_COUNTER_TAPE_DROPPED, dropped),
        ):
            if count:
                counters.append((name, int(count), now))
        if counters:
            conn.executemany(_COUNTER_SQL, counters)
        conn.commit()
    finally:
        conn.close()


def flush_blocking(max_batches: int = 200) -> dict[str, int]:
    """Drain until empty (shutdown / tests). Blocking -- off the IB loop only."""
    total: dict[str, int] = {}
    for _ in range(max_batches):
        result = drain_once()
        for key, value in result.items():
            total[key] = total.get(key, 0) + value
        if pending() == 0:
            break
    return total


async def drain_loop() -> None:
    """HTTP-loop task: SQLite runs in a worker thread so neither loop blocks."""
    logger.info(
        "archive.write_queue: drain loop started (every %.1fs, batch<=%d, cap=%d)",
        ARCHIVE_WRITE_FLUSH_SEC, ARCHIVE_WRITE_BATCH_MAX, ARCHIVE_WRITE_QUEUE_MAX,
    )
    while True:
        await asyncio.sleep(ARCHIVE_WRITE_FLUSH_SEC)
        try:
            await asyncio.to_thread(drain_once)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("archive.write_queue: drain iteration failed")


def reset_for_tests() -> None:
    global _dropped
    with _lock:
        for queue in _QUEUES:
            queue.clear()
        _dropped = 0
