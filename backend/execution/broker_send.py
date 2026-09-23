"""Broker send / ack wait helpers for the execution service (ADR 007)."""
from __future__ import annotations

import time
from typing import Callable

from constants import (
    EXECUTOR_ENTRY_SIDE_IBKR,
    EXECUTOR_ENTRY_SIDE_IBKR_SHORT,
    EXECUTION_ACK_WAIT_SEC,
    IBKR_ERROR_FRACTIONAL_API,
    IBKR_FRACTIONAL_ORDER_API_MSG,
    IBKR_ORDER_TIF_DEFAULT,
)
from execution import inflight
from execution import store
from execution import telemetry
from execution import verification_gate
from execution.models import ExecutionCommand, ExecutionReceipt, StageTimings
from execution.broker_ack import wait_broker_ack
from execution.fill_audit import audit_place_watch
from execution.nova_placed import persist_nova_placed_at
from execution.place_reject_guard import confirm_terminal_reject
from execution.qty_gate import live_cap_refusal
from execution.store_facts import persist_successful_cancel
from ibkr import client as _client
from ibkr import orders as _orders
from ibkr.cancel_verify import cancel_order_verified_on_ib
from ibkr.order_build import normalize_tif, tif_error

__all__ = ["wait_broker_ack", "send_broker", "finish_place"]

RejectFn = Callable[
    [str, ExecutionCommand, StageTimings, str, str],
    ExecutionReceipt,
]


def _working_tif(row: dict) -> str:
    """TIF to resend on a price-only replace: the working order's own (#91).

    A TIF Nova does not place (blank, IOC, a TWS-set GTD) falls back to the
    default -- what every replace sent before per-order TIF existed.
    """
    tif = normalize_tif(row.get("tif"))
    return tif if tif_error(tif) is None else IBKR_ORDER_TIF_DEFAULT


async def send_broker(
    cmd: ExecutionCommand,
    execution_id: str,
    timings: StageTimings,
    *,
    wait_ack: bool = True,
    reject: RejectFn,
) -> ExecutionReceipt:
    from sim.mode import is_practice_venue, venue

    if is_practice_venue():
        # ADR 020: Paper and Sim share one practice send; the venue's broker
        # (live feed or loaded replay) decides where the fill comes from.
        from practice.broker import for_venue
        from sim.execution import send_practice_broker

        return await send_practice_broker(
            cmd, execution_id, timings, broker=for_venue(venue()),
            wait_ack=wait_ack, reject=reject,
        )

    symbol = cmd.normalized_symbol()
    mode = _client.account_mode()

    if cmd.operation == "cancel":
        timings.broker_sent_ns = time.perf_counter_ns()
        store.update_stages(
            execution_id, status="sent", broker_sent_ns=timings.broker_sent_ns,
            order_id=cmd.order_id, mode=mode,
        )
        assert cmd.order_id is not None
        watch = telemetry.watch_order(
            cmd.order_id, execution_id, fresh=True, leg_role="cancel",
        )
        raw = await cancel_order_verified_on_ib(cmd.order_id, watch=watch)
        if not raw.get("ok"):
            store.update_stages(
                execution_id, status="failed", error=str(raw.get("error")),
                reason_code="BROKER_REJECT",
            )
            return ExecutionReceipt(
                ok=False, execution_id=execution_id, operation=cmd.operation,
                source=cmd.source, idempotency_key=cmd.idempotency_key,
                error=raw.get("error"), reason_code="BROKER_REJECT",
                mode=mode, order_id=cmd.order_id, timings=timings,
            )
        if wait_ack:
            await watch.wait_ack(EXECUTION_ACK_WAIT_SEC)
            timings.broker_ack_ns = watch.ack_ns
        inflight.release_order(cmd.order_id)
        broker_status = watch.ack_status or (
            "Cancelled" if raw.get("verified_gone") else None
        )
        persist_successful_cancel(
            execution_id, order_id=cmd.order_id, perm_id=watch.perm_id,
            broker_ack_ns=timings.broker_ack_ns, broker_status=broker_status,
            verified_gone=bool(raw.get("verified_gone")),
        )
        return ExecutionReceipt(
            ok=True, execution_id=execution_id, operation=cmd.operation,
            source=cmd.source, idempotency_key=cmd.idempotency_key,
            mode=mode, order_id=cmd.order_id,
            broker_status=broker_status, timings=timings,
        )

    if cmd.operation == "replace":
        open_rows = {o["order_id"]: o for o in _orders.open_orders()}
        existing = open_rows.get(cmd.order_id)  # type: ignore[arg-type]
        if existing is None:
            return reject(
                execution_id, cmd, timings,
                f"order {cmd.order_id} not open — cannot replace",
                "REPLACE_NOT_OPEN",
            )
        timings.broker_sent_ns = time.perf_counter_ns()
        assert cmd.order_id is not None
        watch = telemetry.watch_order(
            cmd.order_id, execution_id, fresh=True, leg_role="replace",
            side=str(existing["side"]).upper(),
            reference_price=(
                cmd.reference_price
                if cmd.reference_price is not None
                else cmd.limit_price if cmd.limit_price is not None
                else cmd.stop_price
            ),
            reference_source="replace_request",
        )
        store.update_stages(
            execution_id, status="sent", broker_sent_ns=timings.broker_sent_ns,
            order_id=cmd.order_id, mode=mode,
        )
        raw = _orders.place_order(
            symbol=str(existing["symbol"]),
            side=str(existing["side"]),
            qty=float(existing["qty"]),
            order_type=str(existing.get("order_type") or "LMT"),
            limit_price=cmd.limit_price if cmd.limit_price is not None
            else existing.get("limit_price"),
            stop_price=cmd.stop_price if cmd.stop_price is not None
            else existing.get("stop_price"),
            outside_rth=bool(existing.get("outside_rth")),
            order_id=cmd.order_id,
            tif=_working_tif(existing),
        )
        return await finish_place(
            execution_id, cmd, timings, raw, watch, mode, wait_ack=wait_ack,
        )

    if cmd.operation == "bracket":
        qty = int(cmd.shares or cmd.qty or 0)
        from strategy import risk as _risk
        if qty <= 0:
            qty = int(_risk.position_size_shares())
        refusal = live_cap_refusal(cmd, qty)
        if refusal is not None:
            return reject(execution_id, cmd, timings, refusal, "QTY_CAP_LIVE")
        timings.broker_sent_ns = time.perf_counter_ns()
        store.update_stages(
            execution_id, status="sent", broker_sent_ns=timings.broker_sent_ns,
            mode=mode, symbol=symbol,
        )
        entry_side = (
            EXECUTOR_ENTRY_SIDE_IBKR_SHORT
            if getattr(cmd, "short_entry", False)
            else EXECUTOR_ENTRY_SIDE_IBKR
        ).upper()
        raw = _orders.place_bracket_order(
            symbol=symbol or "",
            side=entry_side,
            qty=qty,
            entry_price=float(cmd.entry_price or 0),
            stop_price=float(cmd.stop_price or 0),
            target_price=float(cmd.target_price or 0),
            tif=cmd.tif,
            outside_rth=cmd.outside_rth,
        )
        parent = raw.get("parent_order_id")
        exit_side = "SELL" if entry_side == "BUY" else "BUY"
        watch = (
            telemetry.watch_order(
                int(parent), execution_id, fresh=True, leg_role="parent",
                side=entry_side, reference_price=cmd.entry_price,
                reference_source="bracket_entry", aggregate_eligible=True,
            )
            if parent else None
        )
        for role, child_id, reference in (
            ("target", raw.get("target_order_id"), cmd.target_price),
            ("stop", raw.get("stop_order_id"), cmd.stop_price),
        ):
            if child_id:
                telemetry.watch_order(
                    int(child_id), execution_id, fresh=True, leg_role=role,
                    side=exit_side, reference_price=reference,
                    reference_source=f"bracket_{role}",
                    aggregate_eligible=False,
                )
        if not raw.get("ok"):
            store.update_stages(
                execution_id, status="failed", error=str(raw.get("error")),
                reason_code="BROKER_REJECT",
            )
            return ExecutionReceipt(
                ok=False, execution_id=execution_id, operation=cmd.operation,
                source=cmd.source, idempotency_key=cmd.idempotency_key,
                error=raw.get("error"), reason_code="BROKER_REJECT",
                mode=mode, symbol=symbol, timings=timings,
            )
        persist_nova_placed_at(
            execution_id, raw.get("nova_placed_at") or raw.get("submitted_at")
        )
        if watch is not None and wait_ack:
            await watch.wait_ack(EXECUTION_ACK_WAIT_SEC)
            timings.broker_ack_ns = watch.ack_ns
        store.update_stages(
            execution_id,
            status="acked" if timings.broker_ack_ns else "sent",
            order_id=parent,
            parent_order_id=raw.get("parent_order_id"),
            target_order_id=raw.get("target_order_id"),
            stop_order_id=raw.get("stop_order_id"),
            broker_ack_ns=timings.broker_ack_ns,
            broker_status=watch.ack_status if watch else None,
        )
        return ExecutionReceipt(
            ok=True, execution_id=execution_id, operation=cmd.operation,
            source=cmd.source, idempotency_key=cmd.idempotency_key,
            mode=mode, symbol=symbol, order_id=parent,
            parent_order_id=raw.get("parent_order_id"),
            target_order_id=raw.get("target_order_id"),
            stop_order_id=raw.get("stop_order_id"),
            broker_status=watch.ack_status if watch else None,
            timings=timings,
        )

    # MASTER TEST QTY GATE: nothing above the Live cap reaches IBKR, even a
    # size that got past the clamp (a venue switched to Live mid-command).
    refusal = live_cap_refusal(cmd, cmd.qty)
    if refusal is not None:
        return reject(execution_id, cmd, timings, refusal, "QTY_CAP_LIVE")
    timings.broker_sent_ns = time.perf_counter_ns()
    store.update_stages(
        execution_id, status="sent", broker_sent_ns=timings.broker_sent_ns,
        mode=mode, symbol=symbol,
    )
    raw = _orders.place_order(
        symbol=symbol or "",
        side=(cmd.side or "BUY").upper(),  # type: ignore[arg-type]
        qty=float(cmd.qty or 0),
        order_type=cmd.order_type,  # type: ignore[arg-type]
        limit_price=cmd.limit_price,
        stop_price=cmd.stop_price,
        outside_rth=cmd.outside_rth,
        tif=cmd.tif,
    )
    oid = raw.get("order_id")
    watch = (
        telemetry.watch_order(
            int(oid), execution_id, fresh=True,
            side=(cmd.side or "BUY").upper(),
            reference_price=(
                cmd.reference_price
                if cmd.reference_price is not None
                else cmd.limit_price if cmd.limit_price is not None
                else cmd.stop_price
            ),
            reference_source="execution_command",
        )
        if oid else None
    )
    return await finish_place(
        execution_id, cmd, timings, raw, watch, mode, wait_ack=wait_ack,
    )


async def finish_place(
    execution_id: str,
    cmd: ExecutionCommand,
    timings: StageTimings,
    raw: dict,
    watch: telemetry.OrderWatch | None,
    mode: str,
    *,
    wait_ack: bool = True,
) -> ExecutionReceipt:
    if not raw.get("ok"):
        store.update_stages(
            execution_id, status="failed", error=str(raw.get("error")),
            reason_code="BROKER_REJECT",
        )
        return ExecutionReceipt(
            ok=False, execution_id=execution_id, operation=cmd.operation,
            source=cmd.source, idempotency_key=cmd.idempotency_key,
            error=raw.get("error"), reason_code="BROKER_REJECT",
            mode=mode, symbol=cmd.normalized_symbol(), timings=timings,
        )
    persist_nova_placed_at(execution_id, raw.get("nova_placed_at"))
    oid = raw.get("order_id")
    if watch is not None and wait_ack:
        await watch.wait_ack(EXECUTION_ACK_WAIT_SEC)
        timings.broker_ack_ns = watch.ack_ns
        if watch.filled_ns:
            timings.filled_ns = watch.filled_ns

    broker_status = watch.ack_status if watch else None
    # Cancelled/ApiCancelled/Inactive without a fill is a broker reject
    # (classic: Error 10243 fractional). Grace + open_orders heal Error 10349.
    if watch is not None and wait_ack:
        is_reject, broker_status = await confirm_terminal_reject(
            watch, int(oid) if oid is not None else None,
        )
        if is_reject:
            verification = verification_gate.classify_reject(
                watch.error_code, watch.error_message, cmd.normalized_symbol(),
            )
            if verification is not None:
                err = verification.message
                reason = verification.reason_code
            elif watch.error_code == IBKR_ERROR_FRACTIONAL_API:
                err = IBKR_FRACTIONAL_ORDER_API_MSG
                reason = "QTY_FRACTIONAL_API"
            else:
                err = (
                    watch.error_message
                    or f"Broker rejected/cancelled order ({broker_status})"
                )
                reason = "BROKER_REJECT"
            inflight.release_execution(execution_id)
            store.update_stages(
                execution_id,
                status="failed",
                error=err,
                reason_code=reason,
                order_id=oid,
                broker_ack_ns=timings.broker_ack_ns,
                broker_status=broker_status,
                mode=mode,
            )
            audit_place_watch(watch, cmd, mode, broker_status)
            return ExecutionReceipt(
                ok=False, execution_id=execution_id, operation=cmd.operation,
                source=cmd.source, idempotency_key=cmd.idempotency_key,
                error=err, reason_code=reason,
                mode=mode, symbol=cmd.normalized_symbol(), order_id=oid,
                broker_status=broker_status, timings=timings,
            )

    store.update_stages(
        execution_id,
        status="acked" if timings.broker_ack_ns else "sent",
        order_id=oid,
        broker_ack_ns=timings.broker_ack_ns,
        filled_ns=timings.filled_ns,
        broker_status=broker_status,
        mode=mode,
    )
    audit_place_watch(watch, cmd, mode, broker_status)
    return ExecutionReceipt(
        ok=True, execution_id=execution_id, operation=cmd.operation,
        source=cmd.source, idempotency_key=cmd.idempotency_key,
        mode=mode, symbol=cmd.normalized_symbol(), order_id=oid,
        broker_status=broker_status, timings=timings,
    )
