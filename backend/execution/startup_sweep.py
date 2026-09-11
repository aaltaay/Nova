"""Close out ledger rows a previous process left mid-flight (ADR 007).

A `reserved` / `validated` / `sent` / `acked` row whose `boot_id` is not this
process means Nova stopped before the broker outcome landed. Left as-is the
operator sees an execution that never resolved, and a retry after a timeout
looks like a brand-new order instead of the same intent (D-011).

Runs once at startup, after IBKR connects, against the two cached broker
reads Nova already has: `open_orders` (still working) and `closed_orders`
(already terminal). It never guesses — with no broker read, nothing is
rewritten, and a row that neither list explains is marked `abandoned` rather
than invented as filled or failed.

Timings are not back-filled: `perf_counter_ns` stamps from a dead process
cannot be compared with this one (ADR 007 decision 7).
"""
from __future__ import annotations

import logging

from execution import store
from ibkr import client as _client
from ibkr.errors import IbkrAccountError

logger = logging.getLogger(__name__)

__all__ = ["run_startup_sweep"]

_UNRESOLVED = "SWEEP_UNRESOLVED"
_NEVER_SENT = "SWEEP_NEVER_SENT"


def _order_id(row: dict) -> int | None:
    raw = row.get("order_id")
    if raw in (None, 0):
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _read_broker_orders() -> tuple[set[int], dict[int, dict]] | None:
    """Working ids + terminal rows by order id, or None when unreadable."""
    from ibkr import orders as _orders

    try:
        working = {
            int(row["order_id"])
            for row in _orders.open_orders()
            if row.get("order_id") is not None
        }
        terminal = {
            int(row["order_id"]): row
            for row in _orders.closed_orders()
            if row.get("order_id") is not None
        }
    except IbkrAccountError:
        logger.exception("execution sweep: broker order read failed")
        return None
    return working, terminal


def run_startup_sweep() -> dict:
    """Reconcile abandoned ledger rows. Returns a summary for logs / tests."""
    rows = store.non_terminal_rows()
    summary: dict = {
        "scanned": len(rows),
        "broker_checked": False,
        "still_working": [],
        "resolved": [],
        "abandoned": [],
    }
    if not rows:
        return summary

    if not _client.is_connected():
        logger.warning(
            "execution sweep: %d ledger row(s) from a previous run are still "
            "non-terminal and IBKR is disconnected — leaving them untouched",
            len(rows),
        )
        return summary

    broker = _read_broker_orders()
    if broker is None:
        return summary
    working_ids, terminal_by_id = broker
    summary["broker_checked"] = True

    for row in rows:
        execution_id = str(row["id"])
        order_id = _order_id(row)
        if order_id is None:
            store.update_stages(
                execution_id,
                status="abandoned",
                reason_code=_NEVER_SENT,
                error="startup sweep: no broker order id — never reached IBKR",
            )
            summary["abandoned"].append(execution_id)
            continue
        if order_id in working_ids:
            summary["still_working"].append(execution_id)
            continue
        terminal = terminal_by_id.get(order_id)
        if terminal is not None:
            broker_status = str(terminal.get("status") or "")
            store.update_stages(
                execution_id,
                status="filled" if broker_status == "Filled" else "failed",
                broker_status=broker_status,
                reason_code=None if broker_status == "Filled" else _UNRESOLVED,
                error=(
                    None if broker_status == "Filled"
                    else f"startup sweep: broker reports {broker_status}"
                ),
            )
            summary["resolved"].append(execution_id)
            continue
        store.update_stages(
            execution_id,
            status="abandoned",
            reason_code=_UNRESOLVED,
            error=(
                f"startup sweep: order {order_id} is neither working nor in "
                "broker history — outcome unknown"
            ),
        )
        summary["abandoned"].append(execution_id)

    log = logger.error if summary["abandoned"] else logger.warning
    log(
        "execution sweep: scanned=%d still_working=%d resolved=%d abandoned=%d",
        summary["scanned"],
        len(summary["still_working"]),
        len(summary["resolved"]),
        len(summary["abandoned"]),
    )
    return summary
