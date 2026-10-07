"""The execution ledger read by order id (ADR 048 step 6). Read-only; ``execution.store`` owns the file.

Which Live orders Nova sent, and what as: a short entry (``payload.short_entry``) or a day cover
(``payload.origin``). IBKR's open orders carry neither, and an order id alone is never read as Nova's:
a row counts only when the ledger stamped it with the venue it was sent on (``payload.venue``, #713).
"""
from __future__ import annotations

import json
import sqlite3
from typing import Any, Iterable

from execution import store


def _as_dict(row: sqlite3.Row) -> dict[str, Any]:
    out = dict(row)
    out["payload"] = json.loads(out.pop("payload_json") or "{}")
    return out


def rows_by_order_id(order_ids: Iterable[int], *, venue: str, since_ts: float | None = None,
                     mode: str | None = None) -> list[dict[str, Any]]:
    """The place and bracket rows Nova wrote for ``order_ids`` (an entry's own id) on ``venue``, oldest first.
    ``mode`` keeps only the rows sent through that Gateway (``live`` | ``paper``): the legacy paper Gateway also
    serves the Live venue, and its order ids are its own."""
    ids = sorted({int(oid) for oid in order_ids if int(oid) > 0})
    if not ids:
        return []
    store.init_db()
    conn = store.get_connection()
    try:
        marks = ", ".join("?" for _ in ids)
        sql = (f"SELECT * FROM executions WHERE order_id IN ({marks}) AND operation IN ('place', 'bracket')"
               + (" AND created_ts >= ?" if since_ts is not None else "") + " ORDER BY created_ts ASC")
        args: list[Any] = [*ids, *([since_ts] if since_ts is not None else [])]
        rows = [_as_dict(r) for r in conn.execute(sql, args).fetchall()]
    finally:
        conn.close()
    return [r for r in rows if (r.get("payload") or {}).get("venue") == venue
            and (mode is None or r.get("mode") == mode)]


def short_entries(order_ids: Iterable[int], *, venue: str = "live", since_ts: float | None = None,
                  mode: str | None = None) -> dict[int, dict[str, Any]]:
    """``{order id: execution row}`` for each of ``order_ids`` Nova sent on ``venue`` as a short entry
    (``mode``: only through that Gateway)."""
    return {int(r["order_id"]): r for r in rows_by_order_id(order_ids, venue=venue, since_ts=since_ts, mode=mode)
            if (r.get("payload") or {}).get("short_entry")}
