"""Versioned historical schema, initialized once per database file identity."""
from __future__ import annotations

import sqlite3
import threading
from collections import OrderedDict
from pathlib import Path

from constants_sim import SIM_HISTORY_SCHEMA_CACHE_ENTRIES

SCHEMA_VERSION = 1
_lock = threading.Lock()
_initialized = OrderedDict()


def initialize(db: sqlite3.Connection, path: Path):
    """Legacy v0 is known; a replaced DB cannot reuse the old initialization proof."""
    stat = path.stat()
    identity = (stat.st_dev, stat.st_ino, getattr(stat, 'st_birthtime_ns', None))
    key = str(path.resolve())
    with _lock:
        # Inodes can be reused and birth time is not available on every platform.
        # Validate this connection before trusting any cached initialization proof.
        version = db.execute('PRAGMA user_version').fetchone()[0]
        if version not in (0, SCHEMA_VERSION):
            raise sqlite3.DatabaseError(f'Unsupported historical schema version {version}')
        if version == SCHEMA_VERSION and _initialized.get(key) == identity:
            _initialized.move_to_end(key)
            return
        db.execute('PRAGMA journal_mode=WAL')
        db.executescript('''
            BEGIN;
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS prints (
                job_id TEXT NOT NULL, ordinal INTEGER NOT NULL,
                ts INTEGER NOT NULL, payload TEXT NOT NULL,
                PRIMARY KEY(job_id, ordinal));
            CREATE INDEX IF NOT EXISTS prints_time ON prints(job_id, ts);
            CREATE TABLE IF NOT EXISTS candles (
                job_id TEXT NOT NULL, ts INTEGER NOT NULL, payload TEXT NOT NULL,
                PRIMARY KEY(job_id, ts));
            CREATE TABLE IF NOT EXISTS pacing (id INTEGER PRIMARY KEY, sent REAL);
        ''')
        db.execute(f'PRAGMA user_version={SCHEMA_VERSION}')
        db.commit()
        _initialized[key] = identity
        _initialized.move_to_end(key)
        while len(_initialized) > SIM_HISTORY_SCHEMA_CACHE_ENTRIES:
            _initialized.popitem(last=False)
