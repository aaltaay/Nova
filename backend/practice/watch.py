"""Execution-telemetry bridge for the practice venues (ADR 020).

The practice broker settles its own orders -- a fill, a buying-power cancel, a
DAY expiry -- with no IBKR callback to carry the news, so it tells the
execution telemetry watch itself. Import failures are logged and swallowed:
telemetry is a reader of the venue, never a gate on it.

It also frees the order's in-flight commitment (``execution.inflight``) once
the order is resolved, the way the IBKR callbacks do
(``execution/telemetry_handlers.py``). Without that, every resting practice
SELL that filled kept its shares counted as "already sent", and the last
shares could not be sold or flattened until a restart (QA R7, 2026-09-22).
An order an unwind or reset erased is resolved too (``release_commitments``).
"""
from __future__ import annotations

import logging
import time
from typing import Any, Iterable

from constants_practice import PRACTICE_ORDER_STATUS_EXPIRED

logger = logging.getLogger(__name__)

#: Statuses after which a practice order holds no shares.
_RESOLVED = frozenset({"Filled", "Cancelled", "ApiCancelled", "Inactive", PRACTICE_ORDER_STATUS_EXPIRED})


def release_commitment(order_id: int, row: dict[str, Any]) -> bool:
    """Free the commitment this practice order holds; True when one was freed.

    Practice ids restart at 1 per venue and per reset, so the order id alone
    could name another venue's commitment: the symbol and side must match too.
    """
    try:
        from execution import inflight
    except Exception:
        logger.exception("PRACTICE: execution.inflight unavailable -- commitment for %s kept", order_id)
        return False
    oid = int(order_id)
    symbol = str(row.get("symbol") or "").strip().upper()
    side = str(row.get("side") or "").strip().upper()
    for held in inflight.snapshot():
        if held.get("order_id") != oid:
            continue
        if symbol and held.get("symbol") != symbol:
            continue
        if side and held.get("side") != side:
            continue
        return inflight.release_execution(str(held.get("execution_id")))
    return False


def release_commitments(rows: Iterable[dict[str, Any]]) -> int:
    """Free the commitments of orders that no longer exist (an unwind, a reset); returns how many."""
    freed = 0
    for row in rows:
        try:
            oid = int(row.get("order_id"))
        except (TypeError, ValueError):
            continue
        freed += int(release_commitment(oid, row))
    return freed


def notify_watch(order_id: int, row: dict[str, Any]) -> None:
    """Tell the execution telemetry watch what the practice venue decided."""
    status = str(row.get("status") or "Submitted")
    if status in _RESOLVED:
        release_commitment(int(order_id), row)
    try:
        from execution import telemetry
    except Exception:
        logger.debug("PRACTICE: telemetry import failed", exc_info=True)
        return
    watch = telemetry.watch_order(int(order_id))
    avg = row.get("avg_fill_price")
    watch.note_status(
        status,
        filled=float(row.get("filled_qty") or 0),
        remaining=float(row.get("remaining_qty") or 0),
        average_fill_price=float(avg) if avg else None,
        perm_id=int(order_id),
        callback_perf_ns=time.perf_counter_ns(),
    )
