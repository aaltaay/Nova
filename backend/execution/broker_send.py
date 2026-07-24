"""Broker send / ack wait helpers for the execution service (ADR 007)."""
from __future__ import annotations

import time
from typing import Callable

from constants import (
    EXECUTOR_ENTRY_SIDE_IBKR,
    EXECUTION_ACK_WAIT_SEC,
    IBKR_ERROR_FRACTIONAL_API,
    IBKR_FRACTIONAL_ORDER_API_MSG,
)
from execution import store
from execution import telemetry
from execution.models import ExecutionCommand, ExecutionReceipt, StageTimings
from ibkr import client as _client
from ibkr import orders as _orders

RejectFn = Callable[
    [str, ExecutionCommand, StageTimings, str, str],
    ExecutionReceipt,
]


async def wait_broker_ack(
    cmd: ExecutionCommand,
    receipt: ExecutionReceipt,
) -> ExecutionReceipt:
    """Wait after the service send lock is released, then persist the outcome."""
    if not receipt.ok or receipt.order_id is None or receipt.timings is None:
        return receipt

    watch = telemetry.watch_order(
        int(receipt.order_id), receipt.execution_id,
    )
    await watch.wait_ack(EXECUTION_ACK_WAIT_SEC)
    receipt.timings.broker_ack_ns = watch.ack_ns
    if watch.filled_ns:
        receipt.timings.filled_ns = watch.filled_ns
    receipt.broker_status = watch.ack_status

    if (
        cmd.operation != "cancel"
        and (receipt.broker_status or "") in telemetry.TERMINAL_REJECT_STATUSES
        and not watch.has_fill()
    ):
        if watch.error_code == IBKR_ERROR_FRACTIONAL_API:
            receipt.error = IBKR_FRACTIONAL_ORDER_API_MSG
            receipt.reason_code = "QTY_FRACTIONAL_API"
        else:
            receipt.error = (
                watch.error_message
                or f"Broker rejected/cancelled order ({receipt.broker_status})"
            )
            receipt.reason_code = "BROKER_REJECT"
        receipt.ok = False
        store.update_stages(
            receipt.execution_id,
            status="failed",
            error=receipt.error,
            reason_code=receipt.reason_code,
            broker_ack_ns=receipt.timings.broker_ack_ns,
            broker_status=receipt.broker_status,
        )
        return receipt

    status = (
        "filled"
        if receipt.timings.filled_ns
        else "acked" if receipt.timings.broker_ack_ns else "sent"
    )
    store.update_stages(
        receipt.execution_id,
        status=status,
        broker_ack_ns=receipt.timings.broker_ack_ns,
        filled_ns=receipt.timings.filled_ns,
        broker_status=receipt.broker_status,
    )
    return receipt


async def send_broker(
    cmd: ExecutionCommand,
    execution_id: str,
    timings: StageTimings,
    *,
    wait_ack: bool = True,
    reject: RejectFn,
) -> ExecutionReceipt:
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
        raw = _orders.cancel_order(cmd.order_id)
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
        store.update_stages(
            execution_id, status="acked" if timings.broker_ack_ns else "sent",
            broker_ack_ns=timings.broker_ack_ns, broker_status=watch.ack_status,
        )
        return ExecutionReceipt(
            ok=True, execution_id=execution_id, operation=cmd.operation,
            source=cmd.source, idempotency_key=cmd.idempotency_key,
            mode=mode, order_id=cmd.order_id,
            broker_status=watch.ack_status, timings=timings,
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
        )
        return await finish_place(
            execution_id, cmd, timings, raw, watch, mode, wait_ack=wait_ack,
        )

    if cmd.operation == "bracket":
        qty = int(cmd.shares or cmd.qty or 0)
        from strategy import risk as _risk
        if qty <= 0:
            qty = int(_risk.position_size_shares())
        timings.broker_sent_ns = time.perf_counter_ns()
        store.update_stages(
            execution_id, status="sent", broker_sent_ns=timings.broker_sent_ns,
            mode=mode, symbol=symbol,
        )
        raw = _orders.place_bracket_order(
            symbol=symbol or "",
            side=EXECUTOR_ENTRY_SIDE_IBKR,
            qty=qty,
            entry_price=float(cmd.entry_price or 0),
            stop_price=float(cmd.stop_price or 0),
            target_price=float(cmd.target_price or 0),
        )
        parent = raw.get("parent_order_id")
        entry_side = EXECUTOR_ENTRY_SIDE_IBKR.upper()
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
    oid = raw.get("order_id")
    if watch is not None and wait_ack:
        await watch.wait_ack(EXECUTION_ACK_WAIT_SEC)
        timings.broker_ack_ns = watch.ack_ns
        if watch.filled_ns:
            timings.filled_ns = watch.filled_ns

    broker_status = watch.ack_status if watch else None
    # Cancelled/ApiCancelled/Inactive without a fill is a broker reject
    # (classic: Error 10243 fractional). Do not report ok=true to Flatten UI.
    if (
        watch is not None
        and wait_ack
        and (broker_status or "") in telemetry.TERMINAL_REJECT_STATUSES
        and not watch.has_fill()
    ):
        if watch.error_code == IBKR_ERROR_FRACTIONAL_API:
            err = IBKR_FRACTIONAL_ORDER_API_MSG
            reason = "QTY_FRACTIONAL_API"
        else:
            err = (
                watch.error_message
                or f"Broker rejected/cancelled order ({broker_status})"
            )
            reason = "BROKER_REJECT"
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
    return ExecutionReceipt(
        ok=True, execution_id=execution_id, operation=cmd.operation,
        source=cmd.source, idempotency_key=cmd.idempotency_key,
        mode=mode, symbol=cmd.normalized_symbol(), order_id=oid,
        broker_status=broker_status, timings=timings,
    )
