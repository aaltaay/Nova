"""Enqueue-only writes for the leaderboard (ADR 010, ADR 023).

Producers -- the minute recorder on the HTTP loop and the halt hooks, which
can fire inside ``ib_async`` callbacks on the IB loop -- only append to a
bounded in-memory queue. One drain writes batches from a worker thread, so no
loop ever waits on SQLite. Overflow drops the oldest items and counts them;
a failed write is kept as the recorder's error so the desk can say so.
"""
from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections import deque
from typing import Any

from constants_leaderboard import (
    LEADERBOARD_QUEUE_MAX,
    LEADERBOARD_WRITE_BATCH_MAX,
    LEADERBOARD_WRITE_FLUSH_SEC,
)

logger = logging.getLogger(__name__)

_KINDS = ("rows", "coverage", "minutes", "halts")
_lock = threading.Lock()
_queues: dict[str, deque] = {kind: deque() for kind in _KINDS}
_dropped = 0
_last_error: str | None = None
_error_since: float | None = None
_last_ok_ts: float | None = None


def enqueue(kind: str, items: list[dict[str, Any]]) -> None:
    """O(1)-per-item append; safe from any thread or loop."""
    global _dropped
    if kind not in _queues or not items:
        return
    with _lock:
        queue = _queues[kind]
        for item in items:
            if len(queue) >= LEADERBOARD_QUEUE_MAX:
                queue.popleft()
                _dropped += 1
            queue.append(item)


def pending() -> int:
    with _lock:
        return sum(len(q) for q in _queues.values())


def health() -> dict[str, Any]:
    with _lock:
        return {
            "ok": _last_error is None,
            "error": _last_error,
            "since": _error_since,
            "last_ok_ts": _last_ok_ts,
            "pending": sum(len(q) for q in _queues.values()),
            "dropped": _dropped,
        }


def _take() -> dict[str, list[dict[str, Any]]]:
    with _lock:
        return {
            kind: [queue.popleft() for _ in range(min(len(queue), LEADERBOARD_WRITE_BATCH_MAX))]
            for kind, queue in _queues.items()
        }


def drain_once() -> dict[str, int]:
    """Write one batch. BLOCKING SQLite -- a worker thread or shutdown only."""
    global _last_error, _error_since, _last_ok_ts
    batch = _take()
    if not any(batch.values()):
        return {kind: 0 for kind in _KINDS}
    from leaderboard import store

    try:
        with store.connect() as db:
            written = store.write_batch(db, **batch)
    except Exception as exc:
        with _lock:
            if _last_error is None:
                _error_since = time.time()
            _last_error = f"{type(exc).__name__}: {exc}"
        logger.exception(
            "leaderboard: batch write failed -- lost %s",
            {kind: len(items) for kind, items in batch.items()},
        )
        return {kind: 0 for kind in _KINDS}
    with _lock:
        if _last_error is not None:
            logger.info("leaderboard: store writable again after %s", _last_error)
        _last_error = None
        _error_since = None
        _last_ok_ts = time.time()
    return written


def flush_blocking(max_batches: int = 50) -> None:
    for _ in range(max_batches):
        drain_once()
        if pending() == 0:
            return


async def drain_loop() -> None:
    while True:
        await asyncio.sleep(LEADERBOARD_WRITE_FLUSH_SEC)
        try:
            await asyncio.to_thread(drain_once)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("leaderboard: drain iteration failed")


def reset_for_tests() -> None:
    global _dropped, _last_error, _error_since, _last_ok_ts
    with _lock:
        for queue in _queues.values():
            queue.clear()
        _dropped = 0
        _last_error = None
        _error_since = None
        _last_ok_ts = None
