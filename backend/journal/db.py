"""
SQLite connection + schema for the trading journal.

The database lives under paths.cache_dir() (same convention as cache.py) so
it survives restarts locally, on Railway (mounted volume), and in the
Electron desktop build, without being git-tracked.

Two tables for now:
  signals -- every setup the bot detected as eligible (from setups_stream.py),
             whether or not a human or Phase D ever acted on it.
  trades  -- closed round-trips. Empty until Phase D (paper execution) starts
             calling store.record_trade(). Metrics honestly report "no data
             yet" rather than fabricating a win rate from zero trades.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from constants import JOURNAL_DB_FILENAME
from paths import cache_dir

_SCHEMA = """
CREATE TABLE IF NOT EXISTS signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    symbol TEXT NOT NULL,
    setup TEXT NOT NULL,
    entry_price REAL,
    stop_price REAL,
    target_price REAL,
    payload_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_signals_ts ON signals(ts);

CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    opened_ts REAL NOT NULL,
    closed_ts REAL,
    symbol TEXT NOT NULL,
    setup TEXT,
    side TEXT NOT NULL,
    qty INTEGER NOT NULL,
    entry_price REAL NOT NULL,
    exit_price REAL,
    stop_price REAL,
    target_price REAL,
    pnl REAL,
    adherent INTEGER,
    notes TEXT,
    is_mock INTEGER NOT NULL DEFAULT 0,
    tags TEXT NOT NULL DEFAULT '[]'
);

CREATE INDEX IF NOT EXISTS idx_trades_closed_ts ON trades(closed_ts);
"""

# Columns added after the tables above first shipped. init_db() ALTERs them in
# if missing, so an existing journal.db from before this column existed still
# works -- no destructive migration, no data loss.
_TRADES_MIGRATIONS = [
    ("is_mock", "INTEGER NOT NULL DEFAULT 0"),
    ("tags", "TEXT NOT NULL DEFAULT '[]'"),
]


def _db_path() -> Path:
    return cache_dir() / JOURNAL_DB_FILENAME


def get_connection() -> sqlite3.Connection:
    """New connection per call -- SQLite handles this fine at journal write
    volumes (one row per signal / trade), and it avoids cross-thread reuse
    issues since this is called from both the asyncio scan loop and FastAPI
    request handlers."""
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _migrate_trades_columns(conn: sqlite3.Connection) -> None:
    existing = {row[1] for row in conn.execute("PRAGMA table_info(trades)")}
    for name, ddl in _TRADES_MIGRATIONS:
        if name not in existing:
            conn.execute(f"ALTER TABLE trades ADD COLUMN {name} {ddl}")


def init_db() -> None:
    """Create tables if they don't exist yet and apply column migrations.
    Safe to call repeatedly."""
    conn = get_connection()
    try:
        conn.executescript(_SCHEMA)
        _migrate_trades_columns(conn)
        conn.commit()
    finally:
        conn.close()
