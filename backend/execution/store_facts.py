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
    commission: float | None = None,
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
    if commission is not None:
        fields.append("commission = ?")
        values.append(float(commission))
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


def session_commission_by_symbol(*, since_ts: float) -> dict[str, float]:
    """Sum real CommissionReport dollars per symbol this session. Never invent."""
    totals: dict[str, float] = {}
    for row in list_session_placed(since_ts=since_ts, limit=500):
        try:
            value = float(row.get("commission"))
        except (TypeError, ValueError):
            continue
        if value == 0.0 and row.get("commission") is None:
            continue
        if row.get("commission") is None:
            continue
        try:
            filled = float(row.get("filled_qty") or 0)
        except (TypeError, ValueError):
            filled = 0.0
        if filled <= 0:
            continue
        symbol = str(row.get("symbol") or "").strip().upper()
        if not symbol:
            continue
        totals[symbol] = totals.get(symbol, 0.0) + value
    return totals


_PLACE_OPS = ("place", "bracket")
_CANCEL_STATUSES = frozenset({"Cancelled", "ApiCancelled"})
_KEEP_CLOSED = frozenset({"Filled", "Cancelled", "ApiCancelled", "Inactive"})


def _as_int(value: object) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


def mark_place_cancelled(
    *,
    order_id: int | None = None,
    perm_id: int | None = None,
    broker_status: str = "Cancelled",
) -> str | None:
    """Set the matching place/bracket ``broker_status`` to Cancelled.

    Overlay ``list_session_placed`` / ``_usable_ledger`` only admit place rows
    that are filled or already closed. A user cancel writes a separate
    ``operation=cancel`` row and leaves the place row ``PreSubmitted`` /
    ``acked``, so Time Placed cannot join after restart. This updates the
    place row only. It does not invent clocks and does not overwrite a fill.
    """
    oid = _as_int(order_id)
    pid = _as_int(perm_id)
    if oid <= 0 and pid <= 0:
        return None
    status = str(broker_status or "Cancelled").strip() or "Cancelled"
    if status not in _CANCEL_STATUSES:
        status = "Cancelled"
    store.init_db()
    conn = store.get_connection()
    try:
        clauses = [
            "operation IN ('place', 'bracket')",
            "IFNULL(source, '') != 'benchmark'",
        ]
        values: list = []
        id_or: list[str] = []
        if oid > 0:
            id_or.append("order_id = ?")
            values.append(oid)
        if pid > 0:
            id_or.append("perm_id = ?")
            values.append(pid)
        clauses.append(f"({' OR '.join(id_or)})")
        row = conn.execute(
            f"""
            SELECT * FROM executions
            WHERE {' AND '.join(clauses)}
            ORDER BY created_ts DESC
            LIMIT 1
            """,
            values,
        ).fetchone()
        if row is None:
            return None
        led = store._row_to_dict(row)
        exec_id = str(led.get("id") or "")
        if not exec_id:
            return None
        if str(led.get("status") or "") == "filled":
            return None
        if str(led.get("broker_status") or "") == "Filled":
            return None
        try:
            if float(led.get("filled_qty") or 0) > 0:
                return None
        except (TypeError, ValueError):
            pass
        fields = ["updated_ts = ?"]
        update_values: list = [time.time()]
        current = str(led.get("broker_status") or "")
        if current not in _KEEP_CLOSED:
            fields.append("broker_status = ?")
            update_values.append(status)
        if pid > 0 and _as_int(led.get("perm_id")) <= 0:
            fields.append("perm_id = ?")
            update_values.append(pid)
        if len(fields) == 1:
            return exec_id
        update_values.append(exec_id)
        conn.execute(
            f"UPDATE executions SET {', '.join(fields)} WHERE id = ?",
            update_values,
        )
        conn.commit()
        return exec_id
    finally:
        conn.close()


def persist_successful_cancel(
    execution_id: str,
    *,
    order_id: int,
    perm_id: int | None,
    broker_ack_ns: int | None,
    broker_status: str | None,
    verified_gone: bool,
) -> str | None:
    """Persist the cancel execution, then close the matching place row."""
    store.update_stages(
        execution_id,
        status="acked" if broker_ack_ns else "sent",
        broker_ack_ns=broker_ack_ns,
        broker_status=broker_status,
    )
    closed = str(broker_status or "") in _CANCEL_STATUSES
    if not (verified_gone or closed):
        return None
    return mark_place_cancelled(
        order_id=order_id,
        perm_id=perm_id,
        broker_status=broker_status or "Cancelled",
    )


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
