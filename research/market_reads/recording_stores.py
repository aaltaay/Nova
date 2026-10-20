"""The desk cache's recordings, read without touching the live writers (ADR 059, #1064).

``l2.db`` (``backend/l2/db.py``: ``l2_snapshots``, ``record_sessions``) and ``archive.db`` (``backend/archive/db.py``:
``tape_ibkr``, ``integrity_counters``) are written all session by the desk, in WAL mode. This module only reads them:

* the connection is ``file:...?mode=ro`` with ``PRAGMA query_only=ON``: no ``journal_mode`` change (the desk's own
  ``get_connection`` sets WAL, which is a write), no table made, no writer queue flushed;
* every statement is bounded -- one row, or at most ``CHUNK_ROWS`` -- and its rows are fetched at once, so the read
  transaction lasts milliseconds and a WAL checkpoint is never held behind a research read;
* a store that is not there is ``LookupError`` (``connect`` never creates one).
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, tzinfo
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

BUSY_MS = 5000
CHUNK_ROWS = 20_000
SESSION_ROWS = 50


@contextmanager
def connect(path: Path) -> Iterator[sqlite3.Connection]:
    """A read-only connection to ``path``, closed on leaving the block."""
    if not path.is_file():
        raise LookupError(f"{path} is not on disk")
    conn = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True, timeout=BUSY_MS / 1000)
    try:
        conn.execute("PRAGMA query_only=ON")
        conn.execute(f"PRAGMA busy_timeout={BUSY_MS}")
        conn.row_factory = sqlite3.Row
        yield conn
    finally:
        conn.close()


def _levels(raw: str) -> list[dict[str, Any]]:
    try:
        rows = json.loads(raw)
    except (TypeError, ValueError):
        return []
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def book_at_or_before(conn: sqlite3.Connection, symbol: str, at_ts: float, min_ts: float) -> dict[str, Any] | None:
    """The newest depth snapshot with ``min_ts <= ts <= at_ts``; a top-of-book-only (``l1_fallback``) row is skipped."""
    row = conn.execute(
        "SELECT ts, bids_json, asks_json, setup, session_id FROM l2_snapshots "
        "WHERE symbol = ? AND ts <= ? AND ts >= ? AND l1_fallback = 0 ORDER BY ts DESC LIMIT 1",
        (symbol, at_ts, min_ts)).fetchone()
    if row is None:
        return None
    return {"ts": row["ts"], "bids": _levels(row["bids_json"]), "asks": _levels(row["asks_json"]),
            "setup": row["setup"], "session_id": row["session_id"]}


def span(conn: sqlite3.Connection, table: str, symbol: str, lo: float, hi: float) -> tuple[float | None, float | None]:
    """``(first ts, last ts)`` of ``symbol``'s rows in ``[lo, hi)``: two index seeks on ``(symbol, ts)``, never a scan of
    the range (``MIN`` and ``MAX`` in one statement read every row between)."""
    if table not in ("l2_snapshots", "tape_ibkr"):
        raise ValueError(f"no span of {table}")
    where = f"FROM {table} WHERE symbol = ? AND ts >= ? AND ts < ? ORDER BY ts"
    first = conn.execute(f"SELECT ts {where} LIMIT 1", (symbol, lo, hi)).fetchone()
    last = conn.execute(f"SELECT ts {where} DESC LIMIT 1", (symbol, lo, hi)).fetchone()
    return (None if first is None else first["ts"]), (None if last is None else last["ts"])


def sessions(conn: sqlite3.Connection, symbol: str, lo: float, hi: float) -> tuple[list[dict[str, Any]], bool]:
    """``(sessions, truncated)``: depth sessions of ``symbol`` open at any time in ``[lo, hi)``, oldest first, at most
    ``SESSION_ROWS``; ``truncated`` says more overlapped (a busy symbol-day has many short signal windows)."""
    rows = conn.execute(
        "SELECT session_id, reason, setup, started_ts, ended_ts FROM record_sessions "
        "WHERE symbol = ? AND started_ts < ? AND (ended_ts IS NULL OR ended_ts >= ?) "
        "ORDER BY started_ts LIMIT ?", (symbol, hi, lo, SESSION_ROWS + 1)).fetchall()
    return [dict(row) for row in rows[:SESSION_ROWS]], len(rows) > SESSION_ROWS


def session(conn: sqlite3.Connection, session_id: str) -> dict[str, Any] | None:
    """One depth session by id (the session a served book came from), or None."""
    row = conn.execute("SELECT session_id, reason, setup, started_ts, ended_ts FROM record_sessions "
                       "WHERE session_id = ?", (session_id,)).fetchone()
    return None if row is None else dict(row)


def counter(conn: sqlite3.Connection, name: str) -> int | None:
    row = conn.execute("SELECT value FROM integrity_counters WHERE name = ?", (name,)).fetchone()
    return None if row is None else int(row["value"])


def tape_rows(conn: sqlite3.Connection, symbol: str, lo: float, hi: float, limit: int) -> tuple[list[dict], bool]:
    """``(rows, capped)``: ``tape_ibkr`` prints of ``symbol`` with ``lo <= ts < hi``, oldest first, at most ``limit``.

    Read in ``CHUNK_ROWS`` keyset pages on ``(ts, id)``, each its own short statement, so no read transaction lasts
    longer than one page."""
    columns = "id, ts, receive_ts, price, size, exchange, conditions, side, bid, ask, seq"
    out: list[dict] = []
    after: tuple[float, int] | None = None
    while True:
        want = min(CHUNK_ROWS, limit + 1 - len(out))
        if after is None:
            page = conn.execute(f"SELECT {columns} FROM tape_ibkr WHERE symbol = ? AND ts < ? AND ts >= ? "
                                "ORDER BY ts, id LIMIT ?", (symbol, hi, lo, want)).fetchall()
        else:
            page = conn.execute(f"SELECT {columns} FROM tape_ibkr WHERE symbol = ? AND ts < ? "
                                "AND (ts > ? OR (ts = ? AND id > ?)) ORDER BY ts, id LIMIT ?",
                                (symbol, hi, after[0], after[0], after[1], want)).fetchall()
        for row in page:
            if len(out) >= limit:
                return out, True
            out.append(dict(row))
        if len(page) < want:
            return out, False
        after = (page[-1]["ts"], page[-1]["id"])


def recent_days(conn: sqlite3.Connection, table: str, symbol: str, count: int, tz: tzinfo) -> list[str]:
    """The newest ``count`` calendar days (in ``tz``) ``symbol`` has rows on, newest first: one index seek per day."""
    if table not in ("l2_snapshots", "tape_ibkr"):
        raise ValueError(f"no days of {table}")
    days: list[str] = []
    before = 1e12
    while len(days) < count:
        row = conn.execute(f"SELECT ts FROM {table} WHERE symbol = ? AND ts < ? ORDER BY ts DESC LIMIT 1",
                           (symbol, before)).fetchone()
        if row is None:
            break
        day = datetime.fromtimestamp(row["ts"], tz).date()
        days.append(day.isoformat())
        before = datetime(day.year, day.month, day.day, tzinfo=tz).timestamp()
    return days
