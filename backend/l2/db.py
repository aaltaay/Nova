"""
SQLite connection + schema for recorded Level 2 order-book snapshots.

Mirrors journal/db.py's pattern exactly: lives under paths.cache_dir(), one
connection per call, no destructive migrations.

One table:
  l2_snapshots -- every book snapshot taken during a recording window. Rows
                  sharing the same recording_id belong to one signal's
                  recording (see l2/recorder.py). labeling.py later joins
                  these against journal.trades by symbol + closest opened_ts.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from constants import L2_DB_FILENAME
from paths import cache_dir

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
    l1_fallback INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_l2_snapshots_recording ON l2_snapshots(recording_id);
CREATE INDEX IF NOT EXISTS idx_l2_snapshots_symbol_signal_ts ON l2_snapshots(symbol, signal_ts);
"""


def _db_path() -> Path:
    return cache_dir() / L2_DB_FILENAME


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    """Create tables if they don't exist yet. Safe to call repeatedly."""
    conn = get_connection()
    try:
        conn.executescript(_SCHEMA)
        conn.commit()
    finally:
        conn.close()
