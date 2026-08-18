"""Write IB durable ids and fill qty onto an existing execution row."""
from __future__ import annotations

import time

from execution import store


def record_broker_facts(
    execution_id: str,
    *,
    perm_id: int | None = None,
    filled_qty: float | None = None,
    avg_fill_price: float | None = None,
) -> bool:
    """Update permId / fill size / avg without touching stage clocks."""
    if not execution_id:
        return False
    fields: list[str] = ["updated_ts = ?"]
    values: list = [time.time()]
    if perm_id is not None and int(perm_id) > 0:
        fields.append("perm_id = ?")
        values.append(int(perm_id))
    if filled_qty is not None:
        fields.append("filled_qty = ?")
        values.append(float(filled_qty))
    if avg_fill_price is not None and float(avg_fill_price) != 0.0:
        fields.append("avg_fill_price = ?")
        values.append(float(avg_fill_price))
    if len(fields) == 1:
        return False
    values.append(execution_id)
    store.init_db()
    conn = store.get_connection()
    try:
        cur = conn.execute(
            f"UPDATE executions SET {', '.join(fields)} WHERE id = ?",
            values,
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def lookup_symbol_for_order_id(order_id: int) -> str | None:
    """Most recent ledger symbol for this client order id (cancel backfill)."""
    if order_id <= 0:
        return None
    store.init_db()
    conn = store.get_connection()
    try:
        row = conn.execute(
            """
            SELECT symbol FROM executions
            WHERE order_id = ? AND symbol IS NOT NULL AND symbol != ''
            ORDER BY created_ts DESC LIMIT 1
            """,
            (int(order_id),),
        ).fetchone()
        if row is None:
            return None
        symbol = str(row["symbol"] or "").strip().upper()
        return symbol or None
    finally:
        conn.close()


def list_session_placed(*, since_ts: float, limit: int = 300) -> list[dict]:
    """Place/bracket rows from this session that reached a closed broker state."""
    store.init_db()
    conn = store.get_connection()
    try:
        rows = conn.execute(
            """
            SELECT * FROM executions
            WHERE created_ts >= ?
              AND operation IN ('place', 'bracket')
              AND IFNULL(source, '') != 'benchmark'
              AND (
                status = 'filled'
                OR broker_status IN (
                    'Filled', 'Cancelled', 'ApiCancelled', 'Inactive'
                )
              )
            ORDER BY created_ts DESC
            LIMIT ?
            """,
            (float(since_ts), int(limit)),
        ).fetchall()
        return [store._row_to_dict(r) for r in rows]
    finally:
        conn.close()


def list_session_fills(*, since_ts: float, limit: int = 500) -> list[dict]:
    """Place/bracket rows with a recorded fill, oldest first (round-trip replay)."""
    store.init_db()
    conn = store.get_connection()
    try:
        rows = conn.execute(
            """
            SELECT * FROM executions
            WHERE created_ts >= ?
              AND operation IN ('place', 'bracket')
              AND IFNULL(source, '') NOT IN ('benchmark', 'ib_recovered')
              AND IFNULL(filled_qty, 0) > 0
            ORDER BY created_ts ASC
            LIMIT ?
            """,
            (float(since_ts), int(limit)),
        ).fetchall()
        return [store._row_to_dict(r) for r in rows]
    finally:
        conn.close()
