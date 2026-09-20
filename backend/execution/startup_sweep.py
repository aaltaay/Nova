"""Close out ledger rows a previous process left mid-flight (ADR 007).

A `reserved` / `validated` / `sent` / `acked` row whose `boot_id` is not this
process means Nova stopped before the broker outcome landed. Left as-is the
operator sees an execution that never resolved, and a retry after a timeout
looks like a brand-new order instead of the same intent (D-011).

Runs once at startup, after IBKR connects, against the broker reads Nova
already has: `open_orders` (still working), `closed_orders` (already
terminal), and `ib.fills()` (executions — the one history read that keeps
answering while `reqCompletedOrders` is stuck). It never guesses — with no
broker read, nothing is rewritten, and a row that none of them explains is
marked `abandoned` rather than invented as filled or failed. Absence only
counts once completed orders actually loaded on this connection; while the
Gateway is not answering `reqCompletedOrders` such rows stay `unverified`
(PROBLEM_LOG 2026-09-19).

`unverified` is not a resting place (D-077): the sweep registers a one-shot
listener so that the moment completed orders do load — a re-probe minutes
later, or the post-READY warm on a reconnect — it runs again and those rows
resolve, instead of sitting non-terminal until the next API restart.

Timings are not back-filled: `perf_counter_ns` stamps from a dead process
cannot be compared with this one (ADR 007 decision 7).
"""
from __future__ import annotations

import asyncio
import logging

from execution import store
from ibkr import client as _client
from ibkr import completed_orders_state
from ibkr.errors import IbkrAccountError

logger = logging.getLogger(__name__)

__all__ = ["run_startup_sweep"]

_UNRESOLVED = "SWEEP_UNRESOLVED"
_NEVER_SENT = "SWEEP_NEVER_SENT"
_resweep_armed = False
_resweep_running = False


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


def _row_qty(row: dict) -> float:
    """Ordered quantity from the ledger payload, or 0.0 when unknown."""
    payload = row.get("payload") or {}
    try:
        return abs(float(payload.get("qty") or 0))
    except (TypeError, ValueError):
        return 0.0


def _executed_shares_by_order() -> dict[int, float]:
    """Executed shares per broker order id, from ``ib.fills()``.

    `reqExecutions` still answers while `reqCompletedOrders` is stuck, so this
    is the only proof of a fill available during that window (D-077). Uses
    each execution's cumulative quantity where IB provides it, and falls back
    to summing per-execution shares.
    """
    ib = _client.get_ib()
    fills_fn = getattr(ib, "fills", None) if ib is not None else None
    if not callable(fills_fn):
        return {}
    try:
        fills = list(fills_fn() or [])
    except Exception:
        logger.warning("execution sweep: ib.fills() read failed", exc_info=True)
        return {}
    cumulative: dict[int, float] = {}
    summed: dict[int, float] = {}
    for fill in fills:
        execution = getattr(fill, "execution", None)
        raw_id = getattr(execution, "orderId", None)
        if raw_id in (None, 0):
            continue
        try:
            order_id = int(raw_id)
            shares = abs(float(getattr(execution, "shares", 0) or 0))
            cum_qty = abs(float(getattr(execution, "cumQty", 0) or 0))
        except (TypeError, ValueError):
            continue
        summed[order_id] = summed.get(order_id, 0.0) + shares
        cumulative[order_id] = max(cumulative.get(order_id, 0.0), cum_qty)
    return {
        order_id: max(total, cumulative.get(order_id, 0.0))
        for order_id, total in summed.items()
    }


def run_startup_sweep() -> dict:
    """Reconcile abandoned ledger rows. Returns a summary for logs / tests."""
    rows = store.non_terminal_rows()
    summary: dict = {
        "scanned": len(rows),
        "broker_checked": False,
        "still_working": [],
        "resolved": [],
        "abandoned": [],
        "unverified": [],
        "resolved_by_executions": [],
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
    history_loaded = completed_orders_state.loaded_for(_client.get_ib())
    executed_shares = _executed_shares_by_order()

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
        executed = executed_shares.get(order_id, 0.0)
        ordered = _row_qty(row)
        if executed > 0.0 and ordered > 0.0 and executed + 1e-9 >= ordered:
            # Executions prove the fill even when completed orders never
            # answered — a filled order must never be called abandoned. Same
            # write as the closed-orders path (no `error` text: a non-empty
            # error makes the receipt read as failed — execution.service).
            store.update_stages(
                execution_id,
                status="filled",
                broker_status="Filled",
            )
            summary["resolved"].append(execution_id)
            summary["resolved_by_executions"].append(execution_id)
            continue
        if not history_loaded or executed > 0.0:
            # No history, or a partial execution with no terminal record:
            # something happened at the broker, so this is unknown, not
            # abandoned.
            summary["unverified"].append(execution_id)
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

    if summary["unverified"] and not history_loaded:
        _arm_history_resweep()

    log = logger.error if summary["abandoned"] else logger.warning
    log(
        "execution sweep: scanned=%d still_working=%d resolved=%d "
        "(%d from executions) abandoned=%d unverified=%d "
        "(completed orders loaded=%s)",
        summary["scanned"],
        len(summary["still_working"]),
        len(summary["resolved"]),
        len(summary["resolved_by_executions"]),
        len(summary["abandoned"]),
        len(summary["unverified"]),
        history_loaded,
    )
    return summary


def _arm_history_resweep() -> None:
    """Re-run the sweep the next time completed orders load (D-077)."""
    global _resweep_armed
    if _resweep_armed:
        return
    completed_orders_state.add_load_listener(_on_history_loaded)
    _resweep_armed = True
    logger.info(
        "execution sweep: armed a re-run for when completed orders answer"
    )


def _on_history_loaded() -> None:
    """Listener on ``completed_orders_state.mark_loaded`` — fires once.

    Runs on whichever loop just finished the IBKR request (the IB loop).
    Deferred with ``call_soon`` so the sweep's SQLite work happens after the
    completed-orders cold slot is released, never inside it.
    """
    global _resweep_armed
    completed_orders_state.remove_load_listener(_on_history_loaded)
    _resweep_armed = False
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        _run_history_resweep()
        return
    loop.call_soon(_run_history_resweep)


def _run_history_resweep() -> None:
    global _resweep_running
    if _resweep_running:
        return
    _resweep_running = True
    try:
        logger.warning(
            "execution sweep: completed orders answered — re-running the "
            "startup sweep for rows left unverified"
        )
        summary = run_startup_sweep()
        if summary["scanned"] and not summary["broker_checked"]:
            # The socket dropped between the answer and this run. Stay armed,
            # or the rows would sit unverified until the next API restart --
            # the exact thing D-077 exists to prevent.
            _arm_history_resweep()
    except Exception:
        logger.exception("execution sweep: completed-orders re-run failed")
    finally:
        _resweep_running = False


def reset_for_testing() -> None:
    global _resweep_armed, _resweep_running
    completed_orders_state.remove_load_listener(_on_history_loaded)
    _resweep_armed = False
    _resweep_running = False
