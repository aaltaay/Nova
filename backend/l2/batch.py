"""
Batched SQLite writer for L2 snapshots.

Rows enqueue in memory and flush via executemany when the queue hits
L2_BATCH_SIZE or when the background flush loop ticks. Call flush() after a
recording window ends so tests and shutdown stay durable. Tape prints are not
batched here: the recording worker writes each one with its conditions and
IBKR's ``unreported`` flag (``l2.tape.persist_print``).
"""
from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any

from constants import L2_BATCH_FLUSH_INTERVAL_SEC, L2_BATCH_SIZE
from l2.db import get_connection
from metrics.op_metrics import timed_fn

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_l2_queue: list[tuple[Any, ...]] = []

_L2_INSERT = """
INSERT INTO l2_snapshots
    (recording_id, symbol, setup, signal_ts, ts, bids_json, asks_json, l1_fallback, session_id)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


def enqueue_snapshot(row: tuple[Any, ...]) -> None:
    with _lock:
        _l2_queue.append(row)
        should_flush = len(_l2_queue) >= L2_BATCH_SIZE
    if should_flush:
        flush()


def pending_counts() -> dict[str, int]:
    with _lock:
        return {"snapshots": len(_l2_queue)}


@timed_fn("l2.flush")
def flush() -> dict[str, int]:
    """Write all pending rows. Safe to call from any thread."""
    with _lock:
        l2_rows = _l2_queue[:]
        _l2_queue.clear()
    if not l2_rows:
        return {"snapshots": 0}
    conn = get_connection()
    try:
        conn.executemany(_L2_INSERT, l2_rows)
        conn.commit()
    except Exception:
        # Re-queue so a transient lock failure does not drop data silently.
        with _lock:
            _l2_queue[0:0] = l2_rows
        logger.exception("l2.batch: flush failed; re-queued %d rows", len(l2_rows))
        raise
    finally:
        conn.close()
    return {"snapshots": len(l2_rows)}


def clear_queues_for_tests() -> None:
    with _lock:
        _l2_queue.clear()


async def flush_loop() -> None:
    """Background task: periodic flush of the snapshot queue.

    The write runs on a worker thread: opening ``l2.db`` and committing on the
    HTTP loop stalled every socket and route behind it (perf stall reports,
    2026-09-23). The shutdown flush below stays inline so it finishes first.
    """
    while True:
        try:
            await asyncio.sleep(L2_BATCH_FLUSH_INTERVAL_SEC)
            await asyncio.to_thread(flush)
        except asyncio.CancelledError:
            flush()
            raise
        except Exception:
            logger.exception("l2.batch: flush_loop error")
