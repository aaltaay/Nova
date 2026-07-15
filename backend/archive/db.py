"""
SQLite connection + schema for Nova OS archive hot store (P6).

Lives under ``paths.cache_dir()`` as ``ARCHIVE_DB_FILENAME`` (not git-tracked).
WAL mode + NORMAL sync — same conventions as ``l2/db.py`` / ``journal/db.py``.

Tables: bars_1m, bars_1d, tape_ibkr, capture_gaps, incomplete_windows,
integrity_counters.
"""
from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from constants import ARCHIVE_DB_FILENAME
from paths import cache_dir

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS bars_1m (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    ts REAL NOT NULL,
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    volume REAL NOT NULL DEFAULT 0,
    source TEXT NOT NULL,
    session_date TEXT NOT NULL,
    UNIQUE(symbol, ts, source)
);
CREATE INDEX IF NOT EXISTS idx_bars_1m_date ON bars_1m(session_date);
CREATE INDEX IF NOT EXISTS idx_bars_1m_symbol_ts ON bars_1m(symbol, ts);

CREATE TABLE IF NOT EXISTS bars_1d (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    ts REAL NOT NULL,
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    volume REAL NOT NULL DEFAULT 0,
    source TEXT NOT NULL,
    session_date TEXT NOT NULL,
    UNIQUE(symbol, ts, source)
);
CREATE INDEX IF NOT EXISTS idx_bars_1d_date ON bars_1d(session_date);
CREATE INDEX IF NOT EXISTS idx_bars_1d_symbol_ts ON bars_1d(symbol, ts);

CREATE TABLE IF NOT EXISTS tape_ibkr (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    ts REAL NOT NULL,
    price REAL NOT NULL,
    size REAL NOT NULL,
    exchange TEXT,
    conditions TEXT,
    side TEXT,
    bid REAL,
    ask REAL,
    seq INTEGER,
    receive_ts REAL,
    source TEXT NOT NULL,
    session_date TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tape_ibkr_date ON tape_ibkr(session_date);
CREATE INDEX IF NOT EXISTS idx_tape_ibkr_symbol_ts ON tape_ibkr(symbol, ts);

CREATE TABLE IF NOT EXISTS capture_gaps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stream TEXT NOT NULL,
    symbol TEXT,
    start_ts REAL NOT NULL,
    end_ts REAL NOT NULL,
    reason TEXT,
    marked_ts REAL NOT NULL,
    session_date TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_capture_gaps_date ON capture_gaps(session_date);

CREATE TABLE IF NOT EXISTS incomplete_windows (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stream TEXT NOT NULL,
    symbol TEXT,
    start_ts REAL NOT NULL,
    end_ts REAL NOT NULL,
    note TEXT,
    marked_ts REAL NOT NULL,
    session_date TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_incomplete_windows_date ON incomplete_windows(session_date);

CREATE TABLE IF NOT EXISTS integrity_counters (
    name TEXT PRIMARY KEY,
    value INTEGER NOT NULL DEFAULT 0,
    updated_ts REAL NOT NULL
);
"""


def _db_path() -> Path:
    return cache_dir() / ARCHIVE_DB_FILENAME


def get_connection() -> sqlite3.Connection:
    """One connection per call. WAL + NORMAL sync for local write volume."""
    conn = sqlite3.connect(_db_path(), timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def init_db() -> None:
    """Create tables if they don't exist. Safe to call repeatedly."""
    conn = get_connection()
    try:
        conn.executescript(_SCHEMA)
        conn.commit()
    finally:
        conn.close()
    logger.debug("archive.db: schema ready at %s", _db_path())


def table_row_count(conn: sqlite3.Connection, table: str, session_date: str | None = None) -> int:
    """Count rows in a known archive table, optionally filtered by session_date."""
    allowed = {
        "bars_1m", "bars_1d", "tape_ibkr", "capture_gaps", "incomplete_windows",
        "integrity_counters",
    }
    if table not in allowed:
        raise ValueError(f"unknown archive table: {table}")
    if session_date is None or table == "integrity_counters":
        row = conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()
    else:
        row = conn.execute(
            f"SELECT COUNT(*) AS n FROM {table} WHERE session_date = ?",
            (session_date,),
        ).fetchone()
    return int(row["n"] if row else 0)
