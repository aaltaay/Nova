"""Execution ledger CREATE + column migrations, and which ledger file has them."""
from __future__ import annotations

import sqlite3
from pathlib import Path

# The ledger file (``_file_key``) whose schema ``store.init_db`` last ensured.
_ensured: tuple | None = None


def _file_key(path: Path) -> tuple | None:
    try:
        st = path.stat()
    except OSError:
        return None
    born = getattr(st, "st_birthtime_ns", None) or st.st_ctime_ns
    return (str(path), st.st_dev, st.st_ino, born)


def schema_ensured(path: Path) -> bool:
    """Whether this process already ensured this ledger file's schema. A new or
    replaced file -- another cache dir, a ledger rebuilt at the same path -- is
    a different file and is ensured again."""
    return _ensured is not None and _ensured == _file_key(path)


def mark_schema_ensured(path: Path) -> None:
    global _ensured
    _ensured = _file_key(path)

SCHEMA = """
CREATE TABLE IF NOT EXISTS executions (
    id TEXT PRIMARY KEY,
    idempotency_key TEXT NOT NULL UNIQUE,
    operation TEXT NOT NULL,
    source TEXT NOT NULL,
    symbol TEXT,
    status TEXT NOT NULL,
    reason_code TEXT,
    error TEXT,
    mode TEXT,
    order_id INTEGER,
    parent_order_id INTEGER,
    target_order_id INTEGER,
    stop_order_id INTEGER,
    broker_status TEXT,
    boot_id TEXT NOT NULL,
    received_ns INTEGER NOT NULL,
    validation_completed_ns INTEGER,
    persisted_ns INTEGER,
    broker_sent_ns INTEGER,
    broker_ack_ns INTEGER,
    filled_ns INTEGER,
    created_ts REAL NOT NULL,
    updated_ts REAL NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    perm_id INTEGER,
    filled_qty REAL,
    avg_fill_price REAL,
    commission REAL
);
CREATE INDEX IF NOT EXISTS idx_exec_symbol ON executions(symbol);
CREATE INDEX IF NOT EXISTS idx_exec_created ON executions(created_ts);
"""

_EXEC_COLUMN_MIGRATIONS = (
    ("boot_id", "TEXT"),
    ("perm_id", "INTEGER"),
    ("filled_qty", "REAL"),
    ("avg_fill_price", "REAL"),
    ("commission", "REAL"),
)


def ensure_executions_columns(conn: sqlite3.Connection) -> None:
    """ALTER in columns added after the first ledger ship. Idempotent."""
    columns = {
        str(row["name"])
        for row in conn.execute("PRAGMA table_info(executions)").fetchall()
    }
    for name, sql_type in _EXEC_COLUMN_MIGRATIONS:
        if name in columns:
            continue
        try:
            conn.execute(f"ALTER TABLE executions ADD COLUMN {name} {sql_type}")
        except sqlite3.OperationalError:
            refreshed = {
                str(row["name"])
                for row in conn.execute("PRAGMA table_info(executions)").fetchall()
            }
            if name not in refreshed:
                raise
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_exec_order_id ON executions(order_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_exec_perm_id ON executions(perm_id)"
    )
