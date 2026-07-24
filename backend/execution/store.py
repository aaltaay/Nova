"""SQLite execution ledger — durable reservation + stage timestamps (ADR 007)."""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from pathlib import Path

from constants import EXECUTION_LEDGER_DB_FILENAME, EXECUTION_METRICS_QUERY_LIMIT
from paths import cache_dir

_BOOT_ID = uuid.uuid4().hex

_SCHEMA = """
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
    payload_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_exec_symbol ON executions(symbol);
CREATE INDEX IF NOT EXISTS idx_exec_created ON executions(created_ts);
"""


def _db_path() -> Path:
    return cache_dir() / EXECUTION_LEDGER_DB_FILENAME


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path(), timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    conn = get_connection()
    try:
        conn.executescript(_SCHEMA)
        columns = {
            str(row["name"])
            for row in conn.execute("PRAGMA table_info(executions)").fetchall()
        }
        if "boot_id" not in columns:
            # Legacy monotonic stamps cannot safely mix with this process.
            try:
                conn.execute("ALTER TABLE executions ADD COLUMN boot_id TEXT")
            except sqlite3.OperationalError:
                # A concurrent startup may have completed the same migration
                # after our PRAGMA read. Re-check; propagate every other error.
                refreshed = {
                    str(row["name"])
                    for row in conn.execute("PRAGMA table_info(executions)").fetchall()
                }
                if "boot_id" not in refreshed:
                    raise
        from execution import evidence_store
        evidence_store.init_db(conn)
        conn.commit()
    finally:
        conn.close()


def current_boot_id() -> str:
    return _BOOT_ID


def reserve(
    *,
    idempotency_key: str,
    operation: str,
    source: str,
    symbol: str | None,
    received_ns: int,
    payload: dict | None = None,
) -> tuple[str, bool]:
    """Insert a reserved row. Returns (execution_id, is_new).

    Unique idempotency_key makes concurrent duplicate requests fail closed —
    the second insert raises IntegrityError and we return the existing row.
    """
    init_db()
    execution_id = str(uuid.uuid4())
    now = time.time()
    conn = get_connection()
    try:
        try:
            conn.execute(
                """
                INSERT INTO executions (
                    id, idempotency_key, operation, source, symbol, status,
                    boot_id, received_ns, created_ts, updated_ts, payload_json
                ) VALUES (?, ?, ?, ?, ?, 'reserved', ?, ?, ?, ?, ?)
                """,
                (
                    execution_id,
                    idempotency_key,
                    operation,
                    source,
                    symbol,
                    _BOOT_ID,
                    received_ns,
                    now,
                    now,
                    json.dumps(payload or {}),
                ),
            )
            conn.commit()
            return execution_id, True
        except sqlite3.IntegrityError:
            row = conn.execute(
                "SELECT id FROM executions WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
            if row is None:
                raise
            return str(row["id"]), False
    finally:
        conn.close()


def update_stages(
    execution_id: str,
    *,
    status: str | None = None,
    reason_code: str | None = None,
    error: str | None = None,
    mode: str | None = None,
    symbol: str | None = None,
    order_id: int | None = None,
    parent_order_id: int | None = None,
    target_order_id: int | None = None,
    stop_order_id: int | None = None,
    broker_status: str | None = None,
    validation_completed_ns: int | None = None,
    persisted_ns: int | None = None,
    broker_sent_ns: int | None = None,
    broker_ack_ns: int | None = None,
    filled_ns: int | None = None,
    payload: dict | None = None,
) -> None:
    fields: list[str] = ["updated_ts = ?"]
    values: list = [time.time()]
    mapping = {
        "status": status,
        "reason_code": reason_code,
        "error": error,
        "mode": mode,
        "symbol": symbol,
        "order_id": order_id,
        "parent_order_id": parent_order_id,
        "target_order_id": target_order_id,
        "stop_order_id": stop_order_id,
        "broker_status": broker_status,
        "validation_completed_ns": validation_completed_ns,
        "persisted_ns": persisted_ns,
        "broker_sent_ns": broker_sent_ns,
        "broker_ack_ns": broker_ack_ns,
        "filled_ns": filled_ns,
    }
    for col, val in mapping.items():
        if val is not None:
            fields.append(f"{col} = ?")
            values.append(val)
    if payload is not None:
        fields.append("payload_json = ?")
        values.append(json.dumps(payload))
    values.append(execution_id)
    conn = get_connection()
    try:
        conn.execute(
            f"UPDATE executions SET {', '.join(fields)} WHERE id = ?",
            values,
        )
        conn.commit()
    finally:
        conn.close()


def get_by_id(execution_id: str) -> dict | None:
    init_db()
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM executions WHERE id = ?", (execution_id,)
        ).fetchone()
        return _row_to_dict(row) if row else None
    finally:
        conn.close()


def get_by_idempotency(idempotency_key: str) -> dict | None:
    init_db()
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM executions WHERE idempotency_key = ?",
            (idempotency_key,),
        ).fetchone()
        return _row_to_dict(row) if row else None
    finally:
        conn.close()


def list_recent(limit: int = 100) -> list[dict]:
    init_db()
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM executions ORDER BY created_ts DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


def latency_rows(
    limit: int = EXECUTION_METRICS_QUERY_LIMIT,
    *,
    idempotency_prefix: str | None = None,
) -> list[dict]:
    """Same-boot rows that reached broker_sent, optionally scoped to one run."""
    init_db()
    conn = get_connection()
    try:
        where = ["broker_sent_ns IS NOT NULL", "boot_id = ?"]
        values: list = [_BOOT_ID]
        if idempotency_prefix is not None:
            where.append("substr(idempotency_key, 1, length(?)) = ?")
            values.extend((idempotency_prefix, idempotency_prefix))
        values.append(limit)
        rows = conn.execute(
            f"""
            SELECT * FROM executions
            WHERE {' AND '.join(where)}
            ORDER BY created_ts DESC
            LIMIT ?
            """,
            values,
        ).fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


def mark_ack_by_order_id(
    order_id: int, ack_ns: int, broker_status: str | None = None,
    *, execution_id: str | None = None,
) -> bool:
    """Persist first real broker ack after send (including wait_ack=False paths)."""
    init_db()
    conn = get_connection()
    try:
        fields = [
            "broker_ack_ns = ?",
            "updated_ts = ?",
            "status = CASE WHEN status IN ('sent', 'acked') THEN 'acked' ELSE status END",
        ]
        values: list = [ack_ns, time.time()]
        if broker_status is not None:
            fields.append("broker_status = ?")
            values.append(broker_status)
        values.extend((execution_id, order_id))
        cur = conn.execute(
            f"""
            UPDATE executions
            SET {', '.join(fields)}
            WHERE id = COALESCE(
                ?,
                (
                    SELECT id FROM executions
                    WHERE order_id = ? AND boot_id = ?
                    ORDER BY created_ts DESC LIMIT 1
                )
            )
              AND boot_id = ? AND broker_ack_ns IS NULL
            """,
            [*values, _BOOT_ID, _BOOT_ID],
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def mark_filled_by_order_id(
    order_id: int, filled_ns: int, *, execution_id: str | None = None,
) -> bool:
    """Persist fill timing for a prior send (late IBKR callbacks)."""
    init_db()
    conn = get_connection()
    try:
        cur = conn.execute(
            """
            UPDATE executions
            SET filled_ns = ?, status = 'filled', updated_ts = ?
            WHERE id = COALESCE(
                ?,
                (
                    SELECT id FROM executions
                    WHERE order_id = ? AND boot_id = ?
                    ORDER BY created_ts DESC LIMIT 1
                )
            )
              AND boot_id = ?
              AND (filled_ns IS NULL OR filled_ns = 0)
            """,
            (
                filled_ns, time.time(), execution_id, order_id,
                _BOOT_ID, _BOOT_ID,
            ),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["payload"] = json.loads(d.pop("payload_json") or "{}")
    return d
