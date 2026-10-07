"""SQLite store for the day movers index (ADR 050). Blocking -- never on the IB loop.

Owner: backend/day_movers/. Schema: ``day_movers.schema``. Lives beside the Massive files it is built from
(``<NOVA_MARKET_DATA_DIR>/movers/day_movers.sqlite3``). ``research/movers/build_movers.py`` writes a session
whole through ``replace_session`` and ``export_sec_shares.py`` replaces ``sec_shares``; the backend only reads
(``read_only`` never creates the store, its folder or its tables).
"""
from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from constants_day_movers import (
    DAY_MOVERS_DB_FILENAME,
    DAY_MOVERS_SCHEMA_VERSION,
    DAY_MOVERS_SQLITE_TIMEOUT_SEC,
    DAY_MOVERS_SUBDIR,
)
from day_movers.schema import (
    MOVER_COLUMNS,
    SEC_SHARES_COLUMNS,
    SESSION_COLUMNS,
    SPLIT_COLUMNS,
    UnknownDayMoversSchema,
    initialize,
)


def root() -> Path:
    """``<NOVA_MARKET_DATA_DIR>/movers`` -- the Massive root the Sim reads (ADR 046)."""
    from sim.massive_files import root as massive_root

    return massive_root() / DAY_MOVERS_SUBDIR


def path() -> Path:
    return root() / DAY_MOVERS_DB_FILENAME


@contextmanager
def connect(database: Path | None = None) -> Iterator[sqlite3.Connection]:
    """The store for writing (the builders): created and initialized when new, WAL so readers never wait."""
    target = database or path()
    target.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(target, timeout=DAY_MOVERS_SQLITE_TIMEOUT_SEC)
    db.row_factory = sqlite3.Row
    try:
        db.execute("PRAGMA journal_mode=WAL")
        initialize(db)
        yield db
    finally:
        db.close()


def read_only(database: Path | None = None) -> sqlite3.Connection | None:
    """The store opened read-only, or ``None`` when it has not been built yet.

    A store of another schema version raises ``UnknownDayMoversSchema``; one created but never initialized
    holds nothing and reads as ``None``.
    """
    target = database or path()
    if not target.is_file():
        return None
    db = sqlite3.connect(f"{target.resolve().as_uri()}?mode=ro", uri=True, timeout=DAY_MOVERS_SQLITE_TIMEOUT_SEC)
    db.row_factory = sqlite3.Row
    try:
        version = db.execute("PRAGMA user_version").fetchone()[0]
    except sqlite3.Error:
        db.close()
        raise
    if version == DAY_MOVERS_SCHEMA_VERSION:
        return db
    db.close()
    if version == 0:
        return None
    raise UnknownDayMoversSchema(f"day movers store schema version {version} is not {DAY_MOVERS_SCHEMA_VERSION}")


def _insert_sql(table: str, columns: Sequence[str]) -> str:
    marks = ", ".join("?" for _ in columns)
    return f"INSERT OR REPLACE INTO {table} ({', '.join(columns)}) VALUES ({marks})"


def _tuples(items: Iterable[dict[str, Any]], columns: Sequence[str]) -> list[tuple]:
    return [tuple(item.get(column) for column in columns) for item in items]


def replace_session(db: sqlite3.Connection, session: dict[str, Any], rows: Iterable[dict[str, Any]]) -> int:
    """One session whole, in one transaction: its old rows go, the new ones and its ``sessions`` row land."""
    mover_t = _tuples(rows, MOVER_COLUMNS)
    with db:
        db.execute("DELETE FROM movers WHERE session_date = ?", (session["session_date"],))
        if mover_t:
            db.executemany(_insert_sql("movers", MOVER_COLUMNS), mover_t)
        db.execute(_insert_sql("sessions", SESSION_COLUMNS), _tuples([session], SESSION_COLUMNS)[0])
    return len(mover_t)


def replace_sec_shares(db: sqlite3.Connection, rows: Iterable[dict[str, Any]]) -> int:
    """The whole ``sec_shares`` table, in one transaction (an export reads every filing again)."""
    share_t = _tuples(rows, SEC_SHARES_COLUMNS)
    with db:
        db.execute("DELETE FROM sec_shares")
        if share_t:
            db.executemany(_insert_sql("sec_shares", SEC_SHARES_COLUMNS), share_t)
    return len(share_t)


def replace_splits(db: sqlite3.Connection, rows: Iterable[dict[str, Any]]) -> int:
    """The whole ``splits`` table -- the list the builder adjusted prices by -- in one transaction."""
    split_t = _tuples(rows, SPLIT_COLUMNS)
    with db:
        db.execute("DELETE FROM splits")
        if split_t:
            db.executemany(_insert_sql("splits", SPLIT_COLUMNS), split_t)
    return len(split_t)


def sessions(db: sqlite3.Connection) -> list[dict[str, Any]]:
    """Every session built, oldest first."""
    return [dict(row) for row in db.execute(
        f"SELECT {', '.join(SESSION_COLUMNS)} FROM sessions ORDER BY session_date")]
