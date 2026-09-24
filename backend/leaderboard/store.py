"""SQLite store for the scanner leaderboard (ADR 023). Blocking -- never on the IB loop.

Owner: backend/leaderboard/. Schema: ``leaderboard.schema``. Rows are history
and immutable; a reconstruction rebuild replaces only its own (date, source).
The catalyst tables (schema 2, #498) are written only by
``research/catalysts/export_leaderboard.py``, which replaces a symbol-day whole.
"""
from __future__ import annotations

import logging
import os
import sqlite3
from collections.abc import Iterable, Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from constants_leaderboard import (
    LEADERBOARD_DB_FILENAME,
    LEADERBOARD_DEFAULT_ROOT_WIN,
    LEADERBOARD_DIR_ENV,
    LEADERBOARD_SCHEMA_VERSION,
    LEADERBOARD_SOURCE_RECONSTRUCTED,
    LEADERBOARD_SOURCE_RECORDED,
    LEADERBOARD_SQLITE_TIMEOUT_SEC,
)
from leaderboard.schema import (
    CATALYST_CHECK_COLUMNS,
    CATALYST_ITEM_COLUMNS,
    COVERAGE_COLUMNS,
    HALT_COLUMNS,
    MINUTE_COLUMNS,
    ROW_COLUMNS,
    READABLE_VERSIONS,
    UnknownLeaderboardSchema,
    initialize,
)

logger = logging.getLogger(__name__)


def _durable_archive_available() -> bool:
    return Path("F:/").exists()


def root() -> Path:
    """``NOVA_LEADERBOARD_DIR``; else ``F:\\Nova\\leaderboard``; else ``<cache>/leaderboard``."""
    configured = (os.environ.get(LEADERBOARD_DIR_ENV) or "").strip()
    if configured:
        return Path(configured)
    if _durable_archive_available():
        return Path(LEADERBOARD_DEFAULT_ROOT_WIN)
    from paths import cache_dir

    return Path(cache_dir()) / "leaderboard"


def path() -> Path:
    return root() / LEADERBOARD_DB_FILENAME


@contextmanager
def connect(database: Path | None = None) -> Iterator[sqlite3.Connection]:
    target = database or path()
    target.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(target, timeout=LEADERBOARD_SQLITE_TIMEOUT_SEC)
    db.row_factory = sqlite3.Row
    try:
        initialize(db)
        yield db
    finally:
        db.close()


def read_only(database: Path | None = None) -> sqlite3.Connection | None:
    """The store opened read-only, or ``None`` when there is none yet.

    For readers outside the recorder (the replay's previous close, #542): a read
    never creates the store, its directory or its tables, and never migrates it --
    so a store not yet migrated (``READABLE_VERSIONS``) is read as found, and its
    readers query only the ``rows`` table every version holds. A store written by
    a newer Nova raises ``UnknownLeaderboardSchema``, as ``connect`` does.
    """
    target = database or path()
    if not target.is_file():
        return None
    db = sqlite3.connect(f"{target.resolve().as_uri()}?mode=ro", uri=True,
                         timeout=LEADERBOARD_SQLITE_TIMEOUT_SEC)
    try:
        version = db.execute("PRAGMA user_version").fetchone()[0]
    except sqlite3.Error:
        db.close()
        raise
    if version in READABLE_VERSIONS:
        return db
    db.close()
    if version == 0:
        return None  # Created but never initialized: nothing has been written.
    raise UnknownLeaderboardSchema(
        f"leaderboard store schema version {version} is not {LEADERBOARD_SCHEMA_VERSION}")


def _insert_sql(table: str, columns: Sequence[str], verb: str = "INSERT OR REPLACE") -> str:
    marks = ", ".join("?" for _ in columns)
    return f"{verb} INTO {table} ({', '.join(columns)}) VALUES ({marks})"


def _tuples(items: Iterable[dict[str, Any]], columns: Sequence[str]) -> list[tuple]:
    return [tuple(item.get(column) for column in columns) for item in items]


# ── Writes ──────────────────────────────────────────────────────────────────

def write_batch(
    db: sqlite3.Connection,
    *,
    rows: Iterable[dict[str, Any]] = (),
    coverage: Iterable[dict[str, Any]] = (),
    minutes: Iterable[dict[str, Any]] = (),
    halts: Iterable[dict[str, Any]] = (),
) -> dict[str, int]:
    """One transaction. Rows / coverage / minutes upsert; halt events are idempotent."""
    row_t = _tuples(rows, ROW_COLUMNS)
    cov_t = _tuples(coverage, COVERAGE_COLUMNS)
    min_t = _tuples(minutes, MINUTE_COLUMNS)
    halt_t = _tuples(halts, HALT_COLUMNS)
    with db:
        if row_t:
            db.executemany(_insert_sql("rows", ROW_COLUMNS), row_t)
        if cov_t:
            db.executemany(_insert_sql("coverage", COVERAGE_COLUMNS), cov_t)
        if min_t:
            db.executemany(_insert_sql("minutes", MINUTE_COLUMNS), min_t)
        if halt_t:
            db.executemany(_insert_sql("halt_events", HALT_COLUMNS, "INSERT OR IGNORE"), halt_t)
    return {"rows": len(row_t), "coverage": len(cov_t), "minutes": len(min_t), "halts": len(halt_t)}


def replace_day(db: sqlite3.Connection, session_date: str, source: str) -> None:
    """Drop one (date, source) before a rebuild writes it again."""
    with db:
        db.execute("DELETE FROM rows WHERE session_date = ? AND source = ?", (session_date, source))
        db.execute("DELETE FROM coverage WHERE session_date = ? AND source = ?", (session_date, source))


def replace_catalysts(
    db: sqlite3.Connection,
    checks: Iterable[dict[str, Any]],
    items: Iterable[dict[str, Any]],
) -> dict[str, int]:
    """One transaction: each check's symbol-day loses its old items, then gets the new check and items."""
    check_t = _tuples(checks, CATALYST_CHECK_COLUMNS)
    item_t = _tuples(items, CATALYST_ITEM_COLUMNS)
    with db:
        db.executemany(
            "DELETE FROM catalyst_items WHERE session_date = ? AND symbol = ?",
            [(row[0], row[1]) for row in check_t],
        )
        if check_t:
            db.executemany(_insert_sql("catalyst_checks", CATALYST_CHECK_COLUMNS), check_t)
        if item_t:
            db.executemany(_insert_sql("catalyst_items", CATALYST_ITEM_COLUMNS), item_t)
    return {"checks": len(check_t), "items": len(item_t)}


def start_run(db: sqlite3.Connection, run_id: str, ts: float) -> None:
    with db:
        db.execute(
            "INSERT OR REPLACE INTO runs (run_id, started_ts, last_beat_ts, stopped_ts, stop_reason)"
            " VALUES (?, ?, ?, NULL, NULL)",
            (run_id, ts, ts),
        )


def beat_run(db: sqlite3.Connection, run_id: str, ts: float) -> None:
    with db:
        db.execute("UPDATE runs SET last_beat_ts = ? WHERE run_id = ?", (ts, run_id))


def stop_run(db: sqlite3.Connection, run_id: str, ts: float, reason: str) -> None:
    with db:
        db.execute(
            "UPDATE runs SET stopped_ts = ?, stop_reason = ?, last_beat_ts = MAX(last_beat_ts, ?)"
            " WHERE run_id = ?",
            (ts, reason, ts, run_id),
        )


# ── Reads ───────────────────────────────────────────────────────────────────

def days(db: sqlite3.Connection, limit: int) -> list[dict[str, Any]]:
    """Per (date, source): minute count, first / last minute and the boards seen."""
    out = db.execute(
        "SELECT session_date, source, COUNT(DISTINCT minute_ts) AS minutes,"
        " MIN(minute_ts) AS first_ts, MAX(minute_ts) AS last_ts,"
        " GROUP_CONCAT(DISTINCT board) AS boards"
        " FROM coverage GROUP BY session_date, source"
        " ORDER BY session_date DESC LIMIT ?",
        (int(limit) * 2,),
    ).fetchall()
    return [dict(row) for row in out]


def latest_minute(db: sqlite3.Connection, session_date: str, source: str, at_or_before: int) -> int | None:
    row = db.execute(
        "SELECT MAX(minute_ts) FROM coverage WHERE session_date = ? AND source = ? AND minute_ts <= ?",
        (session_date, source, int(at_or_before)),
    ).fetchone()
    return int(row[0]) if row and row[0] is not None else None


def has_source(db: sqlite3.Connection, session_date: str, source: str) -> bool:
    row = db.execute(
        "SELECT 1 FROM coverage WHERE session_date = ? AND source = ? LIMIT 1",
        (session_date, source),
    ).fetchone()
    return row is not None


def coverage_at(db: sqlite3.Connection, session_date: str, source: str, minute_ts: int) -> list[dict[str, Any]]:
    out = db.execute(
        "SELECT board, state, row_count, run_id FROM coverage"
        " WHERE session_date = ? AND source = ? AND minute_ts = ? ORDER BY board",
        (session_date, source, int(minute_ts)),
    ).fetchall()
    return [dict(row) for row in out]


def rows_at(db: sqlite3.Connection, session_date: str, source: str, minute_ts: int) -> list[dict[str, Any]]:
    out = db.execute(
        f"SELECT {', '.join(ROW_COLUMNS)} FROM rows"
        " WHERE session_date = ? AND source = ? AND minute_ts = ? ORDER BY board, rank",
        (session_date, source, int(minute_ts)),
    ).fetchall()
    return [dict(row) for row in out]


def minute_row(db: sqlite3.Connection, session_date: str, minute_ts: int) -> dict[str, Any] | None:
    row = db.execute(
        f"SELECT {', '.join(MINUTE_COLUMNS)} FROM minutes WHERE session_date = ? AND minute_ts = ?",
        (session_date, int(minute_ts)),
    ).fetchone()
    return dict(row) if row else None


def minutes_for_day(db: sqlite3.Connection, session_date: str) -> list[dict[str, Any]]:
    out = db.execute(
        f"SELECT {', '.join(MINUTE_COLUMNS)} FROM minutes WHERE session_date = ? ORDER BY minute_ts",
        (session_date,),
    ).fetchall()
    return [dict(row) for row in out]


def coverage_minutes(db: sqlite3.Connection, session_date: str, source: str) -> list[int]:
    out = db.execute(
        "SELECT DISTINCT minute_ts FROM coverage WHERE session_date = ? AND source = ? ORDER BY minute_ts",
        (session_date, source),
    ).fetchall()
    return [int(row[0]) for row in out]


def runs_between(db: sqlite3.Connection, start: float, end: float) -> list[dict[str, Any]]:
    out = db.execute(
        "SELECT run_id, started_ts, last_beat_ts, stopped_ts, stop_reason FROM runs"
        " WHERE started_ts <= ? AND last_beat_ts >= ? ORDER BY started_ts",
        (float(end), float(start)),
    ).fetchall()
    return [dict(row) for row in out]


def prev_close_for(db: sqlite3.Connection, session_date: str, symbol: str) -> float | None:
    """The symbol's prior close on that day's rows: recorded (IBKR tick 9) before rebuilt.

    The most common positive value, so one odd minute cannot outvote the day;
    ties go to the value seen latest.
    """
    for source in (LEADERBOARD_SOURCE_RECORDED, LEADERBOARD_SOURCE_RECONSTRUCTED):
        row = db.execute(
            "SELECT prev_close FROM rows"
            " WHERE session_date = ? AND source = ? AND symbol = ? AND prev_close > 0"
            " GROUP BY prev_close ORDER BY COUNT(*) DESC, MAX(minute_ts) DESC LIMIT 1",
            (session_date, source, symbol.strip().upper()),
        ).fetchone()
        if row is not None:
            return float(row[0])
    return None


def day_prev_close(session_date: str, symbol: str, database: Path | None = None) -> float | None:
    """``prev_close_for`` on the store as found; ``None`` when absent, unreadable or silent."""
    try:
        db = read_only(database)
        if db is None:
            return None
        try:
            return prev_close_for(db, session_date, symbol)
        finally:
            db.close()
    except (sqlite3.Error, OSError, ValueError):
        logger.warning("LEADERBOARD: prior close unread for %s %s", symbol, session_date, exc_info=True)
        return None


def halt_events(
    db: sqlite3.Connection,
    session_date: str,
    *,
    until: float | None = None,
    symbols: Sequence[str] | None = None,
) -> list[dict[str, Any]]:
    sql = f"SELECT {', '.join(HALT_COLUMNS)} FROM halt_events WHERE session_date = ?"
    args: list[Any] = [session_date]
    if until is not None:
        sql += " AND ts <= ?"
        args.append(float(until))
    if symbols:
        sql += f" AND symbol IN ({', '.join('?' for _ in symbols)})"
        args.extend(symbols)
    sql += " ORDER BY ts, symbol"
    return [dict(row) for row in db.execute(sql, args).fetchall()]


def catalyst_checks(db: sqlite3.Connection, session_date: str) -> list[dict[str, Any]]:
    """Every symbol the day's catalyst export checked (an empty list: nothing exported for the day)."""
    out = db.execute(
        f"SELECT {', '.join(CATALYST_CHECK_COLUMNS)} FROM catalyst_checks WHERE session_date = ? ORDER BY symbol",
        (session_date,),
    ).fetchall()
    return [dict(row) for row in out]


def catalyst_items(db: sqlite3.Connection, session_date: str, *, until: float) -> list[dict[str, Any]]:
    """The day's exported items published at or before ``until`` -- never one after it."""
    out = db.execute(
        f"SELECT {', '.join(CATALYST_ITEM_COLUMNS)} FROM catalyst_items"
        " WHERE session_date = ? AND published_ts <= ? ORDER BY symbol, published_ts",
        (session_date, float(until)),
    ).fetchall()
    return [dict(row) for row in out]
