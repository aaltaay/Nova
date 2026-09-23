"""The borrow market record (ADR 028): IBKR's short-stock file, one row per change.

``polls (ts, file_ts, rows)`` holds every poll that read a complete file. ``changes (symbol, ts, listed,
fee_rate, rebate_rate, available, capped)`` holds a symbol's row whenever its listing, fee or availability
differs from the last one written; a symbol that leaves the file is written ``listed = 0`` (nothing to
lend). A symbol's value at time t is its last change at or before t, known from the first poll on; a
symbol with no row at all was never listed.

Owner: this module. ``PRAGMA user_version = 1``; an unknown version, or an unversioned file that already
holds tables, refuses to open. Invalidation: rows older than ``MOVE_BORROW_RETENTION_DAYS`` are pruned,
except each symbol's last row before the cutoff (it is still the symbol's value).
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Iterable

from constants_move_reason import (
    MOVE_BORROW_DB_DIRNAME,
    MOVE_BORROW_DB_FILENAME,
    MOVE_BORROW_SCHEMA_VERSION,
    MOVE_BORROW_SQLITE_TIMEOUT_SEC,
)

VALUE_COLUMNS = ("listed", "fee_rate", "rebate_rate", "available", "capped")
_DDL = """
CREATE TABLE IF NOT EXISTS polls (ts REAL PRIMARY KEY, file_ts REAL, rows INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS changes (
    symbol TEXT NOT NULL, ts REAL NOT NULL, listed INTEGER NOT NULL, fee_rate REAL, rebate_rate REAL,
    available INTEGER, capped INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (symbol, ts));
"""


def path() -> Path:
    from paths import cache_dir

    return cache_dir() / MOVE_BORROW_DB_DIRNAME / MOVE_BORROW_DB_FILENAME


def connect(database: Path | None = None) -> sqlite3.Connection:
    target = database or path()
    target.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(target, timeout=MOVE_BORROW_SQLITE_TIMEOUT_SEC, check_same_thread=False)
    version = db.execute("PRAGMA user_version").fetchone()[0]
    tables = db.execute("SELECT count(*) FROM sqlite_master WHERE type = 'table'").fetchone()[0]
    if version not in (0, MOVE_BORROW_SCHEMA_VERSION) or (version == 0 and tables):
        db.close()
        raise RuntimeError(f"{target}: schema version {version} is not {MOVE_BORROW_SCHEMA_VERSION}; refusing to open")
    db.executescript(_DDL)
    db.execute(f"PRAGMA user_version = {MOVE_BORROW_SCHEMA_VERSION}")
    db.execute("PRAGMA journal_mode = WAL")
    return db


def _value(row: Iterable[Any]) -> dict[str, Any]:
    listed, fee, rebate, available, capped = row
    return {"listed": bool(listed), "fee_rate": fee, "rebate_rate": rebate, "available": available,
            "capped": bool(capped)}


def last_values(db: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    """Every symbol's latest written row: the state the next poll is compared with."""
    rows = db.execute(
        "SELECT c.symbol, c.listed, c.fee_rate, c.rebate_rate, c.available, c.capped FROM changes c "
        "JOIN (SELECT symbol, MAX(ts) AS ts FROM changes GROUP BY symbol) m ON m.symbol = c.symbol AND m.ts = c.ts")
    return {sym: _value(rest) for sym, *rest in rows}


def put_poll(db: sqlite3.Connection, ts: float, file_ts: float | None, n_rows: int,
             changes: list[tuple[str, dict[str, Any]]]) -> None:
    with db:
        db.execute("INSERT OR REPLACE INTO polls (ts, file_ts, rows) VALUES (?, ?, ?)", (ts, file_ts, n_rows))
        db.executemany(
            "INSERT OR REPLACE INTO changes (symbol, ts, listed, fee_rate, rebate_rate, available, capped) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            [(sym, ts, int(v["listed"]), v["fee_rate"], v["rebate_rate"], v["available"], int(v["capped"]))
             for sym, v in changes])


def first_poll(db: sqlite3.Connection, at_or_after: float | None = None) -> float | None:
    if at_or_after is None:
        return db.execute("SELECT MIN(ts) FROM polls").fetchone()[0]
    return db.execute("SELECT MIN(ts) FROM polls WHERE ts >= ?", (at_or_after,)).fetchone()[0]


def last_poll(db: sqlite3.Connection, before: float | None = None) -> tuple[float, float | None] | None:
    sql, args = "SELECT ts, file_ts FROM polls", ()
    if before is not None:
        sql, args = sql + " WHERE ts < ?", (before,)
    row = db.execute(sql + " ORDER BY ts DESC LIMIT 1", args).fetchone()
    return (row[0], row[1]) if row else None


def value_at(db: sqlite3.Connection, symbol: str, ts: float) -> dict[str, Any] | None:
    """The symbol's value at ``ts``: None before the first poll; ``listed: False`` if never listed."""
    known = db.execute("SELECT 1 FROM polls WHERE ts <= ? LIMIT 1", (ts,)).fetchone()
    if not known:
        return None
    row = db.execute(
        f"SELECT {', '.join(VALUE_COLUMNS)} FROM changes WHERE symbol = ? AND ts <= ? ORDER BY ts DESC LIMIT 1",
        (symbol, ts)).fetchone()
    return _value(row) if row else {"listed": False, "fee_rate": None, "rebate_rate": None, "available": None,
                                    "capped": False}


def changes_between(db: sqlite3.Connection, symbol: str, start: float, end: float) -> list[dict[str, Any]]:
    rows = db.execute(
        f"SELECT ts, {', '.join(VALUE_COLUMNS)} FROM changes WHERE symbol = ? AND ts > ? AND ts <= ? ORDER BY ts",
        (symbol, start, end))
    return [{"ts": ts, **_value(rest)} for ts, *rest in rows]


def prune(db: sqlite3.Connection, before: float) -> None:
    with db:
        db.execute(
            "DELETE FROM changes WHERE ts < ? AND (symbol, ts) NOT IN "
            "(SELECT symbol, MAX(ts) FROM changes WHERE ts < ? GROUP BY symbol)", (before, before))
        db.execute("DELETE FROM polls WHERE ts < ?", (before,))
