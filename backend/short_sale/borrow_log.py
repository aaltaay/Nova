"""Borrow, recorded: every tick-236 read Nova makes, kept for good (ADR 048 decision 4).

A past-day Sim replay shorts only where IBKR's borrow was recorded for that moment: the replay
reads the newest read at or before its playhead, and a read older than the shortability TTL is
stale there exactly as it is live. Sim at the live edge and Paper use the live read
(``ibkr.shortability``).

**Store.** ``<root>/borrow.sqlite3``: ``NOVA_BORROW_DIR``; else ``F:\\Nova\\borrow`` while F: is
mounted; else ``<cache>/borrow``. ``PRAGMA user_version = 1`` (an unknown version refuses, and
nothing is written or read). One table, ``reads (symbol, ts, shares, state, source)``: ``ts`` epoch
seconds of IBKR's answer, ``shares`` its shortable-shares estimate (null when IBKR gave none),
``state`` the Nova state it read as (``ibkr.shortability.state_from_shares``), ``source`` where the
read came from (``ibkr``). Nothing prunes it.

**Writes never wait.** ``note`` enqueues (``fetch_shortability`` runs on worker threads, never a
loop); one daemon thread writes batches. A full queue drops the read and counts it. A write that
fails is logged and counted, and the thread keeps going. ``NOVA_BORROW_LOG=0`` turns it off.
"""
from __future__ import annotations

import logging
import os
import queue
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from constants_shorts import (
    BORROW_DB_FILENAME,
    BORROW_DEFAULT_ROOT_WIN,
    BORROW_DIR_ENV,
    BORROW_LOG_BATCH,
    BORROW_LOG_ENV,
    BORROW_LOG_QUEUE_MAX,
    BORROW_SCHEMA_VERSION,
    BORROW_SQLITE_TIMEOUT_SEC,
)

logger = logging.getLogger(__name__)

_q: queue.Queue[tuple[str, float, float | None, str, str]] = queue.Queue(maxsize=BORROW_LOG_QUEUE_MAX)
_thread: threading.Thread | None = None
_thread_lock = threading.Lock()
counts = {"written": 0, "dropped": 0, "failed": 0}
last_error: str | None = None


class UnknownBorrowSchema(RuntimeError):
    """The store says a version this code does not know."""


def enabled() -> bool:
    return (os.environ.get(BORROW_LOG_ENV) or "1").strip() != "0"


def root() -> Path:
    configured = (os.environ.get(BORROW_DIR_ENV) or "").strip()
    if configured:
        return Path(configured)
    if Path("F:/").exists():
        return Path(BORROW_DEFAULT_ROOT_WIN)
    from paths import cache_dir

    return Path(cache_dir()) / "borrow"


def path() -> Path:
    return root() / BORROW_DB_FILENAME


def _initialize(db: sqlite3.Connection) -> None:
    version = int(db.execute("PRAGMA user_version").fetchone()[0])
    if version == BORROW_SCHEMA_VERSION:
        return
    if version != 0:
        raise UnknownBorrowSchema(f"{path()} is borrow store version {version}; this Nova reads {BORROW_SCHEMA_VERSION}")
    db.execute("CREATE TABLE IF NOT EXISTS reads (symbol TEXT NOT NULL, ts REAL NOT NULL, shares REAL, "
               "state TEXT NOT NULL, source TEXT NOT NULL)")
    db.execute("CREATE INDEX IF NOT EXISTS reads_symbol_ts ON reads (symbol, ts)")
    db.execute(f"PRAGMA user_version = {BORROW_SCHEMA_VERSION}")
    db.commit()


def _connect() -> sqlite3.Connection:
    target = path()
    target.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(target, timeout=BORROW_SQLITE_TIMEOUT_SEC)
    _initialize(db)
    return db


def note(symbol: str, snapshot: dict[str, Any]) -> bool:
    """Queue one read for the store; False when recording is off or the queue is full."""
    if not enabled():
        return False
    sym = (symbol or "").strip().upper()
    if not sym or not snapshot:
        return False
    shares = snapshot.get("shortable_shares")
    row = (sym, float(snapshot.get("fetched_at") or time.time()),
           float(shares) if isinstance(shares, (int, float)) else None,
           str(snapshot.get("state") or "unknown"), "ibkr")
    try:
        _q.put_nowait(row)
    except queue.Full:
        counts["dropped"] += 1
        return False
    _ensure_thread()
    return True


def _ensure_thread() -> None:
    global _thread
    with _thread_lock:
        if _thread is not None and _thread.is_alive():
            return
        _thread = threading.Thread(target=_run, name="nova-borrow-log", daemon=True)
        _thread.start()


def write_pending(first: tuple | None = None) -> int:
    """Write one batch of what is queued (``first`` leading it); the number written."""
    global last_error
    batch: list[tuple] = [first] if first is not None else []
    while len(batch) < BORROW_LOG_BATCH:
        try:
            batch.append(_q.get_nowait())
        except queue.Empty:
            break
    if not batch:
        return 0
    try:
        db = _connect()
        try:
            db.executemany("INSERT INTO reads (symbol, ts, shares, state, source) VALUES (?, ?, ?, ?, ?)", batch)
            db.commit()
        finally:
            db.close()
    except Exception as exc:  # a full disk or a refused version: count it, say it, keep going
        counts["failed"] += len(batch)
        last_error = str(exc)
        logger.warning("borrow log: %d read(s) not written: %s", len(batch), exc)
        return 0
    counts["written"] += len(batch)
    last_error = None
    return len(batch)


def _run() -> None:
    while True:
        try:
            row = _q.get(timeout=5.0)
        except queue.Empty:
            continue
        write_pending(row)
        while write_pending():
            pass


def at(symbol: str, ts: float) -> dict[str, Any] | None:
    """The newest recorded read of ``symbol`` at or before ``ts``: ``{ts, shares, state}``; None when none.

    Raises ``UnknownBorrowSchema`` for a store of another version; a store not on disk is no read.
    """
    target = path()
    if not target.exists():
        return None
    db = sqlite3.connect(f"file:{target}?mode=ro", uri=True, timeout=BORROW_SQLITE_TIMEOUT_SEC)
    try:
        version = int(db.execute("PRAGMA user_version").fetchone()[0])
        if version != BORROW_SCHEMA_VERSION:
            raise UnknownBorrowSchema(f"{target} is borrow store version {version}; this Nova reads {BORROW_SCHEMA_VERSION}")
        row = db.execute("SELECT ts, shares, state FROM reads WHERE symbol = ? AND ts <= ? ORDER BY ts DESC LIMIT 1",
                         ((symbol or "").strip().upper(), float(ts))).fetchone()
    finally:
        db.close()
    if row is None:
        return None
    return {"ts": float(row[0]), "shares": row[1], "state": str(row[2])}


def status() -> dict[str, Any]:
    return {"enabled": enabled(), "path": str(path()), "queued": _q.qsize(), **counts, "error": last_error}


def reset_for_tests() -> None:
    global last_error
    while True:
        try:
            _q.get_nowait()
        except queue.Empty:
            break
    for key in counts:
        counts[key] = 0
    last_error = None
