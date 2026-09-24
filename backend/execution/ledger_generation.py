"""Execution ledger write generation, and the session commission read it keeps (#554).

The account and positions polls and the Live bot breaker each ask for this
session's CommissionReport dollars about once a second, on the HTTP loop. The
answer only changes when the ``executions`` table does, so it is kept in memory
and served until the ledger is written again -- exactly, with no TTL.

- Every write to ``executions`` commits through :func:`commit`, which commits
  and then advances one in-process counter. ``tests/test_execution_ledger_generation.py``
  fails on a write that commits any other way.
- :func:`session_commissions` reads the counter *before* its query and keeps the
  result under that value, the session start and the ledger file's identity. A
  result computed while a write lands is kept under the old value (or not kept
  at all), so the next read queries again. A write that has returned is seen by
  every read after it.

Writers run on the HTTP loop (the send path, routes) and on the
``execution.persist_queue`` worker thread (IB callbacks), so the counter and
the kept result sit behind a lock; the query itself never holds it.

The ledger belongs to this process (operator cache). The one other writer is
``tools/execution_latency_probe.py``, whose rows are ``source = 'benchmark'``,
which the commission read never counts.
"""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Callable

from execution.store_schema import file_key

_lock = threading.Lock()
_generation = 0
# ((generation, since_ts, ledger file identity), {SYMBOL: dollars}) or None.
_commissions: tuple[tuple, dict[str, float]] | None = None


def current() -> int:
    """How many committed writes the ``executions`` table has seen in this process."""
    with _lock:
        return _generation


def commit(conn: sqlite3.Connection) -> None:
    """Commit a write to ``executions``, then advance the generation.

    The generation advances even when the commit raises: a read that queries
    again costs one query, a read that missed a write would be wrong.
    """
    global _generation
    try:
        conn.commit()
    finally:
        with _lock:
            _generation += 1


def session_commissions(
    since_ts: float,
    ledger_path: Path,
    compute: Callable[[], dict[str, float]],
) -> dict[str, float]:
    """``compute()`` once per ledger generation, session start and ledger file.

    Returns a copy; the kept value is never handed out. A ledger file that does
    not exist yet has no identity and is never kept.
    """
    global _commissions
    with _lock:
        generation = _generation
        kept = _commissions
    key = (generation, float(since_ts), file_key(ledger_path))
    if key[2] is not None and kept is not None and kept[0] == key:
        return dict(kept[1])
    totals = compute()
    if key[2] is not None:
        with _lock:
            if _generation == generation:
                _commissions = (key, dict(totals))
    return dict(totals)
