"""The book watcher's worker (ADR 033): the IBKR callbacks enqueue, one thread judges.

``enqueue_book`` / ``enqueue_print`` / ``enqueue_reset`` run inside ib_async
socket callbacks, so they only stamp the arrival time and put a tuple on a
bounded queue (ADR 010); a full queue drops the item and counts it. One daemon
thread feeds each symbol's ``SymbolWatch``, judges settled drops every
``BOOK_WATCH_TICK_SEC`` and hands events to the journal. Only the live IBKR
depth and AllLast handlers call in -- never a Sim replay.

Owner: this module's in-memory state (one watch per held depth line, dropped
after ``BOOK_WATCH_FORGET_SEC`` without a book). Not persisted; schema_version
n/a. ``NOVA_BOOK_WATCH=0`` turns the watcher off.
"""
from __future__ import annotations

import logging
import os
import queue
import threading
import time
from typing import Any

from book_watch import journal
from book_watch.book import lit_print
from book_watch.constants_book_watch import (
    BOOK_WATCH_ENV,
    BOOK_WATCH_FORGET_SEC,
    BOOK_WATCH_IDLE_SEC,
    BOOK_WATCH_QUEUE_MAX,
    BOOK_WATCH_TICK_SEC,
)
from book_watch.detector import SymbolWatch

logger = logging.getLogger(__name__)

_q: queue.Queue = queue.Queue(maxsize=BOOK_WATCH_QUEUE_MAX)
_lock = threading.Lock()
_thread_lock = threading.Lock()
_thread: threading.Thread | None = None
_watches: dict[str, SymbolWatch] = {}
_counts = {"queued": 0, "dropped": 0, "processed": 0, "errors": 0}


def enabled() -> bool:
    return (os.environ.get(BOOK_WATCH_ENV) or "1").strip() != "0"


def _num_rows() -> int:
    from constants import IBKR_DEPTH_NUM_ROWS

    return int(IBKR_DEPTH_NUM_ROWS)


def _put(item: tuple) -> None:
    try:
        _q.put_nowait(item)
    except queue.Full:
        _counts["dropped"] += 1
        return
    _counts["queued"] += 1
    _ensure_thread()


def enqueue_book(symbol: str, book: dict[str, Any]) -> None:
    """A live IBKR depth book. An L1-only book is not depth: the next depth book starts fresh."""
    if not enabled() or not symbol or not isinstance(book, dict):
        return
    if book.get("l1_fallback"):
        _put(("reset", symbol.upper(), time.time()))
        return
    _put(("book", symbol.upper(), time.time(), book.get("bids") or [], book.get("asks") or []))


def enqueue_reset(symbol: str) -> None:
    """IBKR restarted the symbol's book (a new depth request, or error 317)."""
    if enabled() and symbol:
        _put(("reset", symbol.upper(), time.time()))


def enqueue_print(payload: Any) -> None:
    """A live AllLast print, stamped with its arrival (``receive_ts``)."""
    if not enabled():
        return
    try:
        symbol = str(payload["symbol"]).upper()
        ts = float(payload.get("receive_ts") or time.time())
        _put(("print", symbol, ts, payload.get("price"), payload.get("size"), lit_print(payload)))
    except (KeyError, TypeError, ValueError):
        _counts["dropped"] += 1


def _ensure_thread() -> None:
    global _thread
    if _thread is not None and _thread.is_alive():
        return
    with _thread_lock:
        if _thread is not None and _thread.is_alive():
            return
        _thread = threading.Thread(target=_run, name="book-watch", daemon=True)
        _thread.start()


def _apply(item: tuple) -> list[dict[str, Any]]:
    kind, symbol = item[0], item[1]
    watch = _watches.get(symbol)
    if kind == "reset":
        if watch is not None:
            watch.reset()
        return []
    if watch is None:
        if kind != "book":
            return []  # prints before the first book: nothing to judge them against yet
        watch = _watches[symbol] = SymbolWatch(symbol, num_rows=_num_rows())
    if kind == "book":
        return watch.on_book(item[2], item[3], item[4])
    return watch.on_print(item[2], item[3], item[4], lit=item[5])


def process(item: tuple) -> list[dict[str, Any]]:
    """Apply one queued item under the lock (the worker's step; tests call it directly)."""
    with _lock:
        _counts["processed"] += 1
        return _apply(item)


def tick(now: float | None = None) -> list[dict[str, Any]]:
    """Judge every settled drop; forget lines idle past ``BOOK_WATCH_FORGET_SEC``."""
    now = time.time() if now is None else now
    out: list[dict[str, Any]] = []
    with _lock:
        for symbol, watch in list(_watches.items()):
            out += watch.tick(now)
            if watch.last_book_ts is not None and now - watch.last_book_ts > BOOK_WATCH_FORGET_SEC:
                out += watch.flush()
                del _watches[symbol]
    return out


def _run() -> None:
    last_tick = 0.0
    while True:
        try:
            item = _q.get(timeout=BOOK_WATCH_TICK_SEC)
        except queue.Empty:
            item = None
        events: list[dict[str, Any]] = []
        try:
            if item is not None:
                events += process(item)
            now = time.time()
            # Each item already judges up to its own arrival time; the wall clock
            # judges only once the queue is drained, so a backlog never settles a
            # drop before the prints still queued behind it have been seen.
            if now - last_tick >= BOOK_WATCH_TICK_SEC and _q.empty():
                events += tick(now)
                last_tick = now
        except Exception:
            _counts["errors"] += 1
            logger.exception("book watch: could not process %s", item[:2] if item else "a tick")
        if events:
            journal.record_many(events)


def snapshot(symbol: str, now: float | None = None) -> dict[str, Any] | None:
    """One symbol's reading, or None when Nova holds no depth line the watcher has seen."""
    now = time.time() if now is None else now
    with _lock:
        watch = _watches.get((symbol or "").upper())
        if watch is None:
            return None
        return {
            "watching": watch.last_book_ts is not None and now - watch.last_book_ts <= BOOK_WATCH_IDLE_SEC,
            "since": watch.since,
            "feed": watch.feed(now),
            **watch.totals(now),
            "flags": list(reversed(watch.flags)),
            "pulls": list(reversed(watch.pulls)),
        }


def flags_since(since: float, symbol: str | None = None) -> list[dict[str, Any]]:
    """Every kept flag newer than ``since``, oldest first, for a poller."""
    sym = (symbol or "").upper() or None
    with _lock:
        rows = [f for s, w in _watches.items() if sym in (None, s) for f in w.flags if f["ts"] > since]
    return sorted(rows, key=lambda f: f["ts"])


def status() -> dict[str, Any]:
    with _lock:
        symbols = sorted(_watches)
    return {"enabled": enabled(), "symbols": symbols, "queue_depth": _q.qsize(), **_counts,
            "journal": journal.status()}


def reset_for_tests() -> None:
    with _lock:
        _watches.clear()
    while True:
        try:
            _q.get_nowait()
        except queue.Empty:
            break
    for key in _counts:
        _counts[key] = 0
