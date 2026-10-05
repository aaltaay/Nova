"""Broker send / ack wait helpers for the execution service (ADR 007).

The practice venues' sends go to ``sim.execution``; Live's place, replace and bracket to
``execution.live_send``, which awaits the IB loop without holding this one (#725).
"""
from __future__ import annotations

import time

from constants import (
    EXECUTION_ACK_WAIT_SEC,
    IBKR_ERROR_FRACTIONAL_API,
    IBKR_FRACTIONAL_ORDER_API_MSG,
)
from execution import inflight
from execution import live_send
from execution.live_send import RejectFn
from execution import store
from execution import telemetry
from execution import verification_gate
from execution.models import ExecutionCommand, ExecutionReceipt, StageTimings
from execution.broker_ack import wait_broker_ack
from execution.fill_audit import audit_place_watch
from execution.nova_placed import persist_nova_placed_at
from execution.place_reject_guard import confirm_terminal_reject
from execution.store_facts import persist_successful_cancel
from ibkr import client as _client
from ibkr.cancel_verify import cancel_order_verified_on_ib

__all__ = ["RejectFn", "wait_broker_ack", "send_broker", "finish_place"]


async def send_broker(
    cmd: ExecutionCommand,
    execution_id: str,
    timings: StageTimings,
    *,
    wait_ack: bool = True,
    reject: RejectFn,
    venue: str | None = None,
) -> ExecutionReceipt:
    """Send to the venue's broker: ``venue`` (the one the execution door validated on), else the desk's now."""
    from constants_sim import DESK_PRACTICE_VENUES
    from sim.mode import venue as desk_venue

    venue = venue or desk_venue()
    if venue in DESK_PRACTICE_VENUES:
        # ADR 020: Paper and Sim share one practice send; the venue's broker
        # (live feed or loaded replay) decides where the fill comes from.
        from practice.broker import for_venue
        from sim.execution import send_practice_broker

        return await send_practice_broker(
            cmd, execution_id, timings, broker=for_venue(venue),
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
        if cmd.target_venue:
            # The kill switch's sweep aims at Live from any desk: IBKR itself, not the
            # desk-venue cancel of ``ibkr.orders`` (spec D, #656).
            from execution.live_cancel import cancel_verified

            raw = await cancel_verified(cmd.order_id, watch=watch)
        else:
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
        inflight.release_order(cmd.order_id, "live")      # only Live sends to IBKR
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

    # Live place / replace / bracket await the IB loop without holding this one (#725).
    if cmd.operation == "replace":
        return await live_send.replace(
            cmd, execution_id, timings, mode=mode, wait_ack=wait_ack, reject=reject,
        )
    if cmd.operation == "bracket":
        return await live_send.bracket(
            cmd, execution_id, timings, mode=mode, symbol=symbol, wait_ack=wait_ack, reject=reject,
        )
    return await live_send.place(
        cmd, execution_id, timings, mode=mode, symbol=symbol, wait_ack=wait_ack, reject=reject,
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
