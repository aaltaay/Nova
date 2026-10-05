"""The place rows the Closed blotter joins to IB's closed orders (ADR 045).

``store_facts.list_session_placed`` stays closed-only, so commissions and leftovers never treat a
working order as a Closed row; this overlay also keeps the rows IB may report Cancelled or Filled
while the ledger still says PreSubmitted (a restart mid-cancel). The orders polls ask for it two or
three times every 5 s, so the read is kept until the ledger is written again
(``ledger_generation.session_place_overlay``).
"""
from __future__ import annotations

from execution import ledger_generation, store


def list_session_place_overlay(*, since_ts: float, limit: int = 300) -> list[dict]:
    """Place / bracket rows since ``since_ts``, newest first, still-PreSubmitted ids included.

    The overlay matches IB's Cancelled / Filled by ``order_id`` or ``perm_id``.
    """
    store.init_db()
    return ledger_generation.session_place_overlay(
        since_ts, limit, store._db_path(), lambda: _read_place_overlay(since_ts, limit),
    )


def _read_place_overlay(since_ts: float, limit: int) -> list[dict]:
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
                OR IFNULL(order_id, 0) > 0
                OR IFNULL(perm_id, 0) > 0
              )
            ORDER BY created_ts DESC
            LIMIT ?
            """,
            (float(since_ts), int(limit)),
        ).fetchall()
        return [store._row_to_dict(r) for r in rows]
    finally:
        conn.close()
