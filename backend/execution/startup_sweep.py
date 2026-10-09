"""Close out ledger rows a previous process left mid-flight (ADR 007).

A `reserved` / `validated` / `sent` / `acked` row whose `boot_id` is not this
process means Nova stopped before the broker outcome landed. Left as-is the
operator sees an execution that never resolved, and a retry after a timeout
looks like a brand-new order instead of the same intent (D-011).

Runs at startup for practice rows and after IBKR connects for IBKR rows. Each
row is reconciled only against its own venue, using the broker reads Nova
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

A Live row's reference (``order_ref``) finds its order when the row has no
order id, and vetoes an order id IBKR gave to another order (``execution.
sweep_ref``). A reconnect inside this process runs the sweep over this
process's own Live rows too (``include_current_boot``,
``execution.reconnect_reconcile``): those close only on the broker's evidence
and are never abandoned, since their sends may still be settling.

Timings are not back-filled: `perf_counter_ns` stamps from a dead process
cannot be compared with this one (ADR 007 decision 7).
"""
from __future__ import annotations

import asyncio
import logging

from execution import inflight, store, sweep_ref
from execution.order_outcome import ledger_close
from ibkr import client as _client
from ibkr import completed_orders_state

logger = logging.getLogger(__name__)

__all__ = ["run_startup_sweep"]

_UNRESOLVED = "SWEEP_UNRESOLVED"
_NEVER_SENT = "SWEEP_NEVER_SENT"
_SIM_PROCESS_ENDED = "SWEEP_SIM_PROCESS_ENDED"
_resweep_armed = False
_resweep_running = False
_resweep_current_boot = False


def _row_venue(row: dict) -> str | None:
    """Persisted send venue; the legacy broker label `paper` alone is ambiguous."""
    payload = row.get("payload") or {}
    venue = payload.get("venue") or payload.get("target_venue")
    if venue in ("live", "paper", "sim"):
        return "ibkr" if venue == "live" else venue
    mode = str(row.get("mode") or "live").strip().lower()
    if mode == "sim":
        return "sim"
    if mode != "paper":
        return "ibkr"
    return None


def _order_id(row: dict) -> int | None:
    raw = row.get("order_id")
    if raw in (None, 0):
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _read_broker_orders(mode: str) -> tuple[set[int], dict[int, dict], list[dict]] | None:
    """Working ids + terminal rows by order id + every row, or None when unreadable."""
    from ibkr import orders as _orders

    try:
        if mode == "paper":
            from practice.broker import for_venue

            broker = for_venue(mode)
            open_rows, closed_rows = broker.working_orders(), broker.closed_orders()
        else:
            open_rows = _orders.open_orders(ibkr_only=True)
            closed_rows = _orders.closed_orders(ibkr_only=True)
        working = {
            int(row["order_id"])
            for row in open_rows
            if row.get("order_id") is not None
        }
        terminal = {
            int(row["order_id"]): row
            for row in closed_rows
            if row.get("order_id") is not None
        }
    except Exception:
        logger.exception("execution sweep: %s broker order read failed", mode)
        return None
    return working, terminal, list(open_rows) + list(closed_rows)


def _row_qty(row: dict) -> float:
    """Ordered quantity from the ledger payload, or 0.0 when unknown."""
    payload = row.get("payload") or {}
    try:
        return abs(float(payload.get("qty") or 0))
    except (TypeError, ValueError):
        return 0.0


def _session_fills() -> list | None:
    """The executions IBKR's session holds (they carry ``orderRef``); None when unreadable, never "none"."""
    ib = _client.get_ib()
    fills_fn = getattr(ib, "fills", None) if ib is not None else None
    try:
        return list(fills_fn() or []) if callable(fills_fn) else []
    except Exception:
        logger.warning("execution sweep: ib.fills() read failed -- no reference match by executions", exc_info=True)
        return None


def _executed_shares_by_order() -> dict[int, float] | None:
    """Executed shares per broker order id, from ``ib.fills()``; None when unreadable.

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
        # None, not {}: "no executions" would let the sweep call a filled order
        # abandoned. The caller treats every unresolved row as unverified.
        logger.warning("execution sweep: ib.fills() read failed", exc_info=True)
        return None
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


def _swept(terminal: dict) -> dict:
    """The ledger fields for a row whose order the broker lists as closed.

    Filled reads ``filled``, a cancel or an expiry ``cancelled`` (it read
    ``failed`` until 2026-10-04: TNMG's bot entry and its cancel, 2026-10-02),
    anything else ``failed`` with the broker's word.
    """
    broker_status = str(terminal.get("status") or "")
    outcome = ledger_close(broker_status, reason_code=terminal.get("reason_code"))
    if outcome is not None and outcome["status"] in ("filled", "cancelled"):
        return {"status": outcome["status"], "broker_status": broker_status, "reason_code": outcome["reason_code"]}
    return {
        "status": "failed",
        "broker_status": broker_status,
        "reason_code": _UNRESOLVED,
        "error": f"startup sweep: broker reports {broker_status}",
    }


def run_startup_sweep(*, include_current_boot: bool = False) -> dict:
    """Reconcile abandoned ledger rows. Returns a summary for logs / tests.

    ``include_current_boot`` (a reconnect): this process's Live rows too, on evidence only.
    """
    rows = store.non_terminal_rows(exclude_current_boot=not include_current_boot)
    if include_current_boot:
        # This process's practice rows are its own brokers' to close, never the sweep's.
        boot = store.current_boot_id()
        rows = [r for r in rows if r.get("boot_id") != boot or _row_venue(r) == "ibkr"]
    summary: dict = {
        "scanned": len(rows),
        "broker_checked": False,
        "ibkr_scanned": 0,
        "ibkr_checked": False,
        "still_working": [],
        "resolved": [],
        "abandoned": [],
        "unverified": [],
        "resolved_by_executions": [],
    }
    if not rows:
        return summary

    groups: dict[str, list[dict]] = {}
    for row in rows:
        key = _row_venue(row)
        if key is None:
            summary["unverified"].append(str(row["id"]))
            logger.warning("execution sweep: ambiguous legacy Paper venue for %s; leaving untouched", row["id"])
            continue
        groups.setdefault(key, []).append(row)
    summary["ibkr_scanned"] = len(groups.get("ibkr", []))
    for mode, venue_rows in groups.items():
        if mode == "sim":
            for row in venue_rows:
                execution_id = str(row["id"])
                store.update_stages(
                    execution_id, status="abandoned", reason_code=_SIM_PROCESS_ENDED,
                    error="startup sweep: previous process's Sim scratch ledger no longer exists",
                )
                summary["abandoned"].append(execution_id)
            continue
        if mode == "ibkr" and not _client.is_connected():
            logger.warning("execution sweep: IBKR disconnected; leaving %d IBKR rows untouched", len(venue_rows))
            continue
        broker = _read_broker_orders(mode)
        if broker is None:
            continue
        summary["broker_checked"] = True
        if mode == "ibkr":
            summary["ibkr_checked"] = True
        history_loaded = mode == "paper" or completed_orders_state.loaded_for(_client.get_ib())
        executed_shares = {} if mode == "paper" else _executed_shares_by_order()
        fills = [] if mode == "paper" else _session_fills()
        _reconcile_rows(venue_rows, broker, history_loaded, executed_shares, summary, fills)

    log = logger.error if summary["abandoned"] else logger.warning
    log(
        "execution sweep: scanned=%d still_working=%d resolved=%d abandoned=%d unverified=%d",
        summary["scanned"], len(summary["still_working"]), len(summary["resolved"]),
        len(summary["abandoned"]), len(summary["unverified"]),
    )
    return summary


def _reconcile_rows(
    rows: list[dict], broker: tuple[set[int], dict[int, dict], list[dict]],
    history_loaded: bool, executed_shares: dict[int, float] | None, summary: dict,
    fills: list | None = None,
) -> None:
    """Resolve one venue's rows using evidence exclusively from that venue."""
    working_ids, terminal_by_id, all_rows = broker
    boot = store.current_boot_id()
    for row in rows:
        execution_id = str(row["id"])
        current = row.get("boot_id") == boot
        if current and _order_id(row) is None and row.get("reason_code") != "SEND_UNKNOWN":
            continue  # this process's send on its way: its own path writes the order id
        verdict, order_id = sweep_ref.decide(row, _order_id(row), all_rows, fills or [])
        unknown_stays = current or not history_loaded or _order_id(row) or fills is None
        if verdict == "ambiguous" or (verdict == "unknown" and unknown_stays):
            # An id IBKR gave another order reached IBKR all the same: unknown, never "never sent".
            summary["unverified"].append(execution_id)
            continue
        if order_id is None:
            store.update_stages(
                execution_id,
                status="abandoned",
                reason_code=_NEVER_SENT,
                error=("startup sweep: IBKR has no order under its reference — never reached IBKR"
                       if row.get("order_ref") else "startup sweep: no broker order id — never reached its broker"),
            )
            summary["abandoned"].append(execution_id)
            continue
        if order_id in working_ids:
            summary["still_working"].append(execution_id)
            continue
        terminal = terminal_by_id.get(order_id)
        if terminal is not None:
            store.update_stages(execution_id, **_swept(terminal))
            inflight.release_execution(execution_id)
            summary["resolved"].append(execution_id)
            continue
        executed = (executed_shares or {}).get(order_id, 0.0)
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
            inflight.release_execution(execution_id)
            summary["resolved"].append(execution_id)
            summary["resolved_by_executions"].append(execution_id)
            continue
        if current or not history_loaded or executed > 0.0 or executed_shares is None:
            # No history, a partial execution with no terminal record, or no
            # executions to check: something may have happened at the broker,
            # so this is unknown, not abandoned. Nor is this process's own row.
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
        _arm_history_resweep(current_boot=any(r.get("boot_id") == boot for r in rows))


def _arm_history_resweep(*, current_boot: bool = False) -> None:
    """Re-run the sweep the next time completed orders load (D-077), over the same rows."""
    global _resweep_armed, _resweep_current_boot
    _resweep_current_boot = _resweep_current_boot or current_boot
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
        global _resweep_current_boot
        current_boot, _resweep_current_boot = _resweep_current_boot, False
        summary = run_startup_sweep(include_current_boot=True) if current_boot else run_startup_sweep()
        if summary["ibkr_scanned"] and not summary["ibkr_checked"]:
            # The socket dropped between the answer and this run. Stay armed,
            # or the rows would sit unverified until the next API restart --
            # the exact thing D-077 exists to prevent.
            _arm_history_resweep(current_boot=current_boot)
    except Exception:
        logger.exception("execution sweep: completed-orders re-run failed")
    finally:
        _resweep_running = False


def reset_for_testing() -> None:
    global _resweep_armed, _resweep_running, _resweep_current_boot
    completed_orders_state.remove_load_listener(_on_history_loaded)
    _resweep_armed = False
    _resweep_running = False
    _resweep_current_boot = False
