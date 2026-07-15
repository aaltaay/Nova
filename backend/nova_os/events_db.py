"""
SQLite connection + schema for the Nova OS event log (Phase P1).

Mirrors journal/db.py's conventions: the DB lives under paths.cache_dir() so it
survives restarts locally, on Railway (mounted volume), and in the Electron
desktop build, without being git-tracked. New connection per call.

One table: `events` — the append-only audit trail. Every Nova OS decision or
action writes exactly one row here and it is NEVER updated or deleted in normal
operation (the "no silent action" contract). There is deliberately no UPDATE or
DELETE helper in events.py; the only maintenance path is retention pruning by
age, kept separate so a routine write path can never mutate history.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from constants import NOVA_OS_EVENTS_DB_FILENAME
from paths import cache_dir

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    policy_version TEXT NOT NULL,
    kind TEXT NOT NULL,
    symbol TEXT,
    decision TEXT,
    action TEXT,
    mode TEXT,
    reason_codes TEXT NOT NULL DEFAULT '[]',
    would_execute INTEGER NOT NULL DEFAULT 0,
    executed INTEGER NOT NULL DEFAULT 0,
    payload_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);
CREATE INDEX IF NOT EXISTS idx_events_symbol ON events(symbol);
"""


def _db_path() -> Path:
    return cache_dir() / NOVA_OS_EVENTS_DB_FILENAME


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    """Create the events table if it does not exist. Safe to call repeatedly."""
    conn = get_connection()
    try:
        conn.executescript(_SCHEMA)
        conn.commit()
    finally:
        conn.close()
