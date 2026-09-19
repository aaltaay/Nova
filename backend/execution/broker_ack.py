"""Ack-wait after the execution send lock is released (extracted from broker_send)."""
from __future__ import annotations

from constants import (
    EXECUTION_ACK_WAIT_SEC,
    IBKR_ERROR_FRACTIONAL_API,
    IBKR_FRACTIONAL_ORDER_API_MSG,
)
from execution import inflight
from execution import store
from execution import telemetry
from execution import verification_gate
from execution.models import ExecutionCommand, ExecutionReceipt
from execution.fill_audit import audit_place_watch
from execution.place_reject_guard import confirm_terminal_reject


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

    if cmd.operation != "cancel":
        is_reject, status = await confirm_terminal_reject(
            watch, int(receipt.order_id),
        )
        receipt.broker_status = status
        if is_reject:
            verification = verification_gate.classify_reject(
                watch.error_code, watch.error_message, cmd.normalized_symbol(),
            )
            if verification is not None:
                receipt.error = verification.message
                receipt.reason_code = verification.reason_code
            elif watch.error_code == IBKR_ERROR_FRACTIONAL_API:
                receipt.error = IBKR_FRACTIONAL_ORDER_API_MSG
                receipt.reason_code = "QTY_FRACTIONAL_API"
            else:
                receipt.error = (
                    watch.error_message
                    or f"Broker rejected/cancelled order ({receipt.broker_status})"
                )
                receipt.reason_code = "BROKER_REJECT"
            receipt.ok = False
            inflight.release_execution(receipt.execution_id)
            store.update_stages(
                receipt.execution_id,
                status="failed",
                error=receipt.error,
                reason_code=receipt.reason_code,
                broker_ack_ns=receipt.timings.broker_ack_ns,
                broker_status=receipt.broker_status,
            )
            audit_place_watch(watch, cmd, receipt.mode or "", receipt.broker_status)
            return receipt

    status = (
        "filled"
        if receipt.timings.filled_ns
        else "acked" if receipt.timings.broker_ack_ns else "sent"
    )
    if status == "filled":
        inflight.release_execution(receipt.execution_id)
    store.update_stages(
        receipt.execution_id,
        status=status,
        broker_ack_ns=receipt.timings.broker_ack_ns,
        filled_ns=receipt.timings.filled_ns,
        broker_status=receipt.broker_status,
    )
    audit_place_watch(watch, cmd, receipt.mode or "", receipt.broker_status)
    return receipt
