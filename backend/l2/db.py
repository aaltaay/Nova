"""
SQLite connection + schema for local market-data recorders (L2 + tape).

Lives under paths.cache_dir() as l2.db (not git-tracked). WAL mode + batched
writers (l2/batch.py) keep write throughput high for continuous depth sessions
and time & sales. See Local-Market-Data-Recorders.md for the storage decision.

Tables:
  l2_snapshots     -- order-book snapshots (signal windows + continuous depth)
  tape_trades      -- time & sales prints for watched symbols (Alpaca WS)
  record_sessions  -- lightweight session metadata (symbol, reason, wall-clock)
"""
from __future__ import annotations

import logging
import sqlite3
import time
from pathlib import Path

from constants import L2_DB_FILENAME, L2_RETENTION_DAYS
from paths import cache_dir

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS l2_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recording_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    setup TEXT NOT NULL,
    signal_ts REAL NOT NULL,
    ts REAL NOT NULL,
    bids_json TEXT NOT NULL,
    asks_json TEXT NOT NULL,
    l1_fallback INTEGER NOT NULL DEFAULT 0,
    session_id TEXT
);

CREATE INDEX IF NOT EXISTS idx_l2_snapshots_recording ON l2_snapshots(recording_id);
CREATE INDEX IF NOT EXISTS idx_l2_snapshots_symbol_signal_ts ON l2_snapshots(symbol, signal_ts);
CREATE INDEX IF NOT EXISTS idx_l2_snapshots_symbol_ts ON l2_snapshots(symbol, ts);

CREATE TABLE IF NOT EXISTS tape_trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    ts REAL NOT NULL,
    price REAL NOT NULL,
    size REAL NOT NULL,
    exchange TEXT,
    source TEXT NOT NULL,
    session_id TEXT
);

CREATE INDEX IF NOT EXISTS idx_tape_trades_symbol_ts ON tape_trades(symbol, ts);

CREATE TABLE IF NOT EXISTS record_sessions (
    session_id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    reason TEXT NOT NULL,
    setup TEXT,
    signal_ts REAL,
    started_ts REAL NOT NULL,
    ended_ts REAL
);

CREATE INDEX IF NOT EXISTS idx_record_sessions_symbol_started
    ON record_sessions(symbol, started_ts);
"""

_L2_SNAPSHOT_MIGRATIONS = [
    ("session_id", "TEXT"),
]


def _db_path() -> Path:
    return cache_dir() / L2_DB_FILENAME


def get_connection() -> sqlite3.Connection:
    """One connection per call. WAL + NORMAL sync for high local write volume."""
    conn = sqlite3.connect(_db_path(), timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def _migrate_l2_snapshot_columns(conn: sqlite3.Connection) -> None:
    existing = {row[1] for row in conn.execute("PRAGMA table_info(l2_snapshots)")}
    for col, decl in _L2_SNAPSHOT_MIGRATIONS:
        if col not in existing:
            conn.execute(f"ALTER TABLE l2_snapshots ADD COLUMN {col} {decl}")


def init_db() -> None:
    """Create tables if they don't exist yet. Safe to call repeatedly."""
    conn = get_connection()
    try:
        conn.executescript(_SCHEMA)
        _migrate_l2_snapshot_columns(conn)
        conn.commit()
    finally:
        conn.close()


def purge_older_than(retention_days: float | None = None) -> dict:
    """Delete ended-session rows older than retention. Returns delete counts.

    When ``ARCHIVE_REQUIRE_VERIFIED_BEFORE_TRIM`` is True (Nova OS P6 default),
    this is a no-op — unverified hot data must not be timer-purged until P8
    cloud verify. Tests may pass ``retention_days`` and monkeypatch the flag.
    """
    try:
        from constants import ARCHIVE_REQUIRE_VERIFIED_BEFORE_TRIM
        if ARCHIVE_REQUIRE_VERIFIED_BEFORE_TRIM:
            logger.info(
                "l2.db: retention purge skipped "
                "(ARCHIVE_REQUIRE_VERIFIED_BEFORE_TRIM=True; await P8 verify)"
            )
            return {
                "cutoff_ts": None,
                "snapshots": 0,
                "tape": 0,
                "sessions": 0,
                "skipped": True,
                "reason": "ARCHIVE_REQUIRE_VERIFIED_BEFORE_TRIM",
            }
    except Exception:
        logger.exception("l2.db: archive trim-guard check failed; refusing purge")
        return {
            "cutoff_ts": None,
            "snapshots": 0,
            "tape": 0,
            "sessions": 0,
            "skipped": True,
            "reason": "trim_guard_error",
        }

    days = L2_RETENTION_DAYS if retention_days is None else retention_days
    cutoff = time.time() - (days * 86400.0)
    conn = get_connection()
    try:
        snap = conn.execute("DELETE FROM l2_snapshots WHERE ts < ?", (cutoff,)).rowcount
        tape = conn.execute("DELETE FROM tape_trades WHERE ts < ?", (cutoff,)).rowcount
        sess = conn.execute(
            "DELETE FROM record_sessions WHERE started_ts < ? AND ended_ts IS NOT NULL",
            (cutoff,),
        ).rowcount
        conn.commit()
        logger.info(
            "l2.db: retention purge cutoff=%.0f deleted snapshots=%d tape=%d sessions=%d",
            cutoff, snap, tape, sess,
        )
        return {"cutoff_ts": cutoff, "snapshots": snap, "tape": tape, "sessions": sess}
    finally:
        conn.close()
