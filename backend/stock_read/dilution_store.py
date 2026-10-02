"""The dilution reads kept on disk: one row per symbol, the last read of SEC EDGAR for it.

``reads (symbol, fetched_at, body)``: ``fetched_at`` is when the submissions file was fetched (for a symbol
SEC's ticker list does not hold, when that list was); ``body`` is the read as JSON --
``{status: "read" | "no_cik", cik, name, filings, more, unread_to}`` (``stock_read/dilution.py``).

Owner: ``stock_read/dilution_reader.py``, through this module; nothing else reads or writes the file.
``PRAGMA user_version = 1``; an unknown version, or an unversioned file that already holds tables, refuses
to open -- the reader then keeps its reads in memory and logs why. Invalidation: the reader serves a read
for its session day and reads EDGAR again after it; a row older than ``STOCK_READ_DILUTION_KEEP_DAYS`` is
deleted.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from constants_stock_read import (
    STOCK_READ_DILUTION_DB_DIRNAME,
    STOCK_READ_DILUTION_DB_FILENAME,
    STOCK_READ_DILUTION_DB_SCHEMA_VERSION,
    STOCK_READ_DILUTION_SQLITE_TIMEOUT_SEC,
)

_DDL = "CREATE TABLE IF NOT EXISTS reads (symbol TEXT PRIMARY KEY, fetched_at REAL NOT NULL, body TEXT NOT NULL)"


def path() -> Path:
    from paths import cache_dir

    return cache_dir() / STOCK_READ_DILUTION_DB_DIRNAME / STOCK_READ_DILUTION_DB_FILENAME


def connect(database: Path | None = None) -> sqlite3.Connection:
    target = database or path()
    target.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(target, timeout=STOCK_READ_DILUTION_SQLITE_TIMEOUT_SEC, check_same_thread=False)
    version = db.execute("PRAGMA user_version").fetchone()[0]
    tables = db.execute("SELECT count(*) FROM sqlite_master WHERE type = 'table'").fetchone()[0]
    if version not in (0, STOCK_READ_DILUTION_DB_SCHEMA_VERSION) or (version == 0 and tables):
        db.close()
        raise RuntimeError(f"{target}: schema version {version} is not {STOCK_READ_DILUTION_DB_SCHEMA_VERSION}; "
                           "refusing to open")
    db.execute(_DDL)
    db.execute(f"PRAGMA user_version = {STOCK_READ_DILUTION_DB_SCHEMA_VERSION}")
    db.execute("PRAGMA journal_mode = WAL")
    return db


def _well_formed(record: Any) -> bool:
    """A body this version wrote: a known status and filings that each name their kind, form and date."""
    if not isinstance(record, dict) or record.get("status") not in ("read", "no_cik"):
        return False
    filings = record.get("filings")
    return isinstance(filings, list) and all(
        isinstance(f, dict) and all(isinstance(f.get(key), str) for key in ("kind", "form", "date")) for f in filings)


def load(db: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    """Every kept read, by symbol. A row whose body is not a read is left out: its symbol is read again,
    never answered from a body that cannot be trusted."""
    out: dict[str, dict[str, Any]] = {}
    for symbol, fetched_at, body in db.execute("SELECT symbol, fetched_at, body FROM reads"):
        try:
            record = json.loads(body)
        except ValueError:
            record = None
        if _well_formed(record):
            out[symbol] = {**record, "fetched_at": float(fetched_at)}
    return out


def put(db: sqlite3.Connection, symbol: str, record: dict[str, Any]) -> None:
    body = {k: v for k, v in record.items() if k != "fetched_at"}
    with db:
        db.execute("INSERT OR REPLACE INTO reads (symbol, fetched_at, body) VALUES (?, ?, ?)",
                   (symbol, float(record["fetched_at"]), json.dumps(body, separators=(",", ":"))))


def prune(db: sqlite3.Connection, before: float) -> None:
    with db:
        db.execute("DELETE FROM reads WHERE fetched_at < ?", (before,))
