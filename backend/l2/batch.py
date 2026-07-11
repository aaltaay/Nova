"""
Batched SQLite writers for L2 snapshots and tape trades.

Rows enqueue in memory and flush via executemany when the queue hits
L2_BATCH_SIZE / TAPE_BATCH_SIZE or when the background flush loop ticks.
Call flush() after a recording window ends so tests and shutdown stay durable.
"""
from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any

from constants import (
    L2_BATCH_FLUSH_INTERVAL_SEC,
    L2_BATCH_SIZE,
    TAPE_BATCH_FLUSH_INTERVAL_SEC,
    TAPE_BATCH_SIZE,
)
from l2.db import get_connection

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_l2_queue: list[tuple[Any, ...]] = []
_tape_queue: list[tuple[Any, ...]] = []

_L2_INSERT = """
INSERT INTO l2_snapshots
    (recording_id, symbol, setup, signal_ts, ts, bids_json, asks_json, l1_fallback, session_id)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

_TAPE_INSERT = """
INSERT INTO tape_trades (symbol, ts, price, size, exchange, source, session_id)
VALUES (?, ?, ?, ?, ?, ?, ?)
"""


def enqueue_snapshot(row: tuple[Any, ...]) -> None:
    with _lock:
        _l2_queue.append(row)
        should_flush = len(_l2_queue) >= L2_BATCH_SIZE
    if should_flush:
        flush()


def enqueue_trade(row: tuple[Any, ...]) -> None:
    with _lock:
        _tape_queue.append(row)
        should_flush = len(_tape_queue) >= TAPE_BATCH_SIZE
    if should_flush:
        flush()


def pending_counts() -> dict[str, int]:
    with _lock:
        return {"snapshots": len(_l2_queue), "tape": len(_tape_queue)}


def flush() -> dict[str, int]:
    """Write all pending rows. Safe to call from any thread."""
    with _lock:
        l2_rows = _l2_queue[:]
        tape_rows = _tape_queue[:]
        _l2_queue.clear()
        _tape_queue.clear()
    if not l2_rows and not tape_rows:
        return {"snapshots": 0, "tape": 0}
    conn = get_connection()
    try:
        if l2_rows:
            conn.executemany(_L2_INSERT, l2_rows)
        if tape_rows:
            conn.executemany(_TAPE_INSERT, tape_rows)
        conn.commit()
    except Exception:
        # Re-queue so a transient lock failure does not drop data silently.
        with _lock:
            _l2_queue[0:0] = l2_rows
            _tape_queue[0:0] = tape_rows
        logger.exception("l2.batch: flush failed; re-queued %d/%d rows", len(l2_rows), len(tape_rows))
        raise
    finally:
        conn.close()
    return {"snapshots": len(l2_rows), "tape": len(tape_rows)}


def clear_queues_for_tests() -> None:
    with _lock:
        _l2_queue.clear()
        _tape_queue.clear()


async def flush_loop() -> None:
    """Background task: periodic flush of both queues."""
    interval = min(L2_BATCH_FLUSH_INTERVAL_SEC, TAPE_BATCH_FLUSH_INTERVAL_SEC)
    while True:
        try:
            await asyncio.sleep(interval)
            flush()
        except asyncio.CancelledError:
            flush()
            raise
        except Exception:
            logger.exception("l2.batch: flush_loop error")
