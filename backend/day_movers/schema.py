"""Day movers store schema (ADR 050; AGENTS.md section 3, "Agents find stock-days and show them in the Sim").

``PRAGMA user_version`` names the schema; a store written by a newer Nova refuses loudly.
"""
from __future__ import annotations

import sqlite3

from constants_day_movers import DAY_MOVERS_SCHEMA_VERSION

SESSION_COLUMNS = ("session_date", "prev_date", "tickers", "rows", "minute_bars", "builder", "built_ts", "note")

MOVER_COLUMNS = (
    "session_date", "symbol", "kind",
    "prev_date", "prev_close", "prev_volume", "split_factor", "split_listed", "split_suspect",
    "open", "high", "low", "close", "volume",
    "pm_high", "pm_low", "pm_volume", "ah_high", "ah_low", "ah_volume",
    "day_high", "day_high_ts", "day_low", "day_low_ts",
    "dollar_volume", "first_ts", "last_ts",
    "high_pct", "low_pct", "close_pct", "gap_pct",
    "up10_ts", "up20_ts", "up50_ts", "up100_ts", "up300_ts",
    "down10_ts", "down20_ts", "down50_ts",
)

SEC_SHARES_COLUMNS = ("symbol", "cik", "as_of", "filed", "shares", "form")
SPLIT_COLUMNS = ("symbol", "execution_date", "split_from", "split_to")

_REAL = {
    "prev_close", "prev_volume", "split_factor", "open", "high", "low", "close", "volume",
    "pm_high", "pm_low", "pm_volume", "ah_high", "ah_low", "ah_volume", "day_high", "day_low",
    "dollar_volume", "high_pct", "low_pct", "close_pct", "gap_pct",
}
_TEXT = {"session_date", "symbol", "kind", "prev_date"}


def _mover_column_sql(name: str) -> str:
    if name in _TEXT:
        return f"{name} TEXT" + (" NOT NULL" if name in ("session_date", "symbol") else "")
    if name in _REAL:
        return f"{name} REAL"
    return f"{name} INTEGER"


DDL = (
    """CREATE TABLE IF NOT EXISTS sessions (
        session_date TEXT PRIMARY KEY,
        prev_date TEXT,
        tickers INTEGER NOT NULL,
        rows INTEGER NOT NULL,
        minute_bars INTEGER NOT NULL,
        builder INTEGER NOT NULL,
        built_ts REAL NOT NULL,
        note TEXT
    )""",
    "CREATE TABLE IF NOT EXISTS movers (\n    "
    + ",\n    ".join(_mover_column_sql(c) for c in MOVER_COLUMNS)
    + ",\n    PRIMARY KEY (session_date, symbol)\n)",
    "CREATE INDEX IF NOT EXISTS movers_by_symbol ON movers (symbol, session_date)",
    "CREATE INDEX IF NOT EXISTS movers_by_high ON movers (high_pct)",
    "CREATE INDEX IF NOT EXISTS movers_by_low ON movers (low_pct)",
    "CREATE INDEX IF NOT EXISTS movers_by_close ON movers (close_pct)",
    "CREATE INDEX IF NOT EXISTS movers_by_gap ON movers (gap_pct)",
    """CREATE TABLE IF NOT EXISTS sec_shares (
        symbol TEXT NOT NULL,
        cik TEXT,
        as_of TEXT NOT NULL,
        filed TEXT NOT NULL,
        shares REAL NOT NULL,
        form TEXT,
        PRIMARY KEY (symbol, as_of, filed)
    )""",
    """CREATE TABLE IF NOT EXISTS splits (
        symbol TEXT NOT NULL,
        execution_date TEXT NOT NULL,
        split_from REAL NOT NULL,
        split_to REAL NOT NULL,
        PRIMARY KEY (symbol, execution_date)
    )""",
)


class UnknownDayMoversSchema(RuntimeError):
    """The store was written by a newer Nova (or something else): never read or migrated as found."""


def initialize(db: sqlite3.Connection) -> None:
    """Create the tables (every statement is ``IF NOT EXISTS``); refuse a store of another version."""
    version = db.execute("PRAGMA user_version").fetchone()[0]
    if version not in (0, DAY_MOVERS_SCHEMA_VERSION):
        raise UnknownDayMoversSchema(
            f"day movers store schema version {version} is not {DAY_MOVERS_SCHEMA_VERSION}")
    with db:
        for statement in DDL:
            db.execute(statement)
        db.execute(f"PRAGMA user_version = {DAY_MOVERS_SCHEMA_VERSION}")
