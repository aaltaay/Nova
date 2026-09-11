"""Off-loop persistence for IB-callback ledger writes (ADR 007 + ADR 010).

``orderStatus`` and ``execDetails`` arrive inside ``ib_async`` socket callbacks,
i.e. on the IB connect-loop. Ack / fill / broker-fact rows used to be written
right there: ``sqlite3.connect`` + PRAGMA + UPDATE + ``commit`` in front of every
``reqMktData`` tick. One slow disk during a fill burst stalls L1, scanner leases
and depth for the whole desk -- the same failure class as the 2026-08-18
archive-write wedge.

Producers call :func:`submit` and return immediately. A single daemon worker
drains FIFO, so ack -> facts -> fill ordering is preserved and the ledger still
sees one writer at a time. Off the IB loop (HTTP routes, reconciliation, tests)
``submit`` runs the write inline: those callers are already allowed to block, and
inline keeps read-after-write assertions honest.
"""
from __future__ import annotations

import logging
import threading
import time
from collections import deque
from typing import Callable

logger = logging.getLogger(__name__)

Job = Callable[[], None]

_cv = threading.Condition()
_queue: deque[tuple[str, Job]] = deque()
_busy = 0
_worker: threading.Thread | None = None


def submit(label: str, job: Job) -> bool:
    """Persist ``job``. Returns True when it was deferred to the worker."""
    if not _on_ib_thread():
        _run(label, job)
        return False
    with _cv:
        _queue.append((label, job))
        _ensure_worker_locked()
        _cv.notify()
    return True


def pending() -> int:
    with _cv:
        return len(_queue) + _busy


def flush(timeout: float = 5.0) -> bool:
    """Block until the queue drains. Returns False on timeout."""
    deadline = time.monotonic() + max(0.0, float(timeout))
    with _cv:
        while _queue or _busy:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            _cv.wait(remaining)
    return True


def reset_for_tests() -> None:
    with _cv:
        _queue.clear()


def _on_ib_thread() -> bool:
    try:
        from ibkr.loop_supervisor import is_ib_loop, is_ib_thread

        return is_ib_loop() or is_ib_thread()
    except Exception:
        return False


def _run(label: str, job: Job) -> None:
    try:
        job()
    except Exception:
        logger.exception("execution.persist_queue: %s failed", label)


def _ensure_worker_locked() -> None:
    global _worker
    if _worker is not None and _worker.is_alive():
        return
    _worker = threading.Thread(
        target=_worker_main, name="nova-exec-persist", daemon=True,
    )
    _worker.start()


def _worker_main() -> None:
    global _busy
    logger.info("execution.persist_queue: writer started")
    while True:
        with _cv:
            while not _queue:
                _cv.wait()
            label, job = _queue.popleft()
            _busy += 1
        _run(label, job)
        with _cv:
            _busy -= 1
            _cv.notify_all()
