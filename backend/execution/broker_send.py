"""Broker send / ack wait helpers for the execution service (ADR 007)."""
from __future__ import annotations

import time
from typing import Callable

from constants import EXECUTOR_ENTRY_SIDE_IBKR, EXECUTION_ACK_WAIT_SEC
from execution import store
from execution import telemetry
from execution.models import ExecutionCommand, ExecutionReceipt, StageTimings
from ibkr import client as _client
from ibkr import orders as _orders

RejectFn = Callable[
    [str, ExecutionCommand, StageTimings, str, str],
    ExecutionReceipt,
]


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
        watch = telemetry.watch_order(cmd.order_id)
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
        watch = telemetry.watch_order(cmd.order_id)
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
        watch = telemetry.watch_order(int(parent)) if parent else None
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
    watch = telemetry.watch_order(int(oid)) if oid else None
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
    store.update_stages(
        execution_id,
        status="acked" if timings.broker_ack_ns else "sent",
        order_id=oid,
        broker_ack_ns=timings.broker_ack_ns,
        filled_ns=timings.filled_ns,
        broker_status=watch.ack_status if watch else None,
        mode=mode,
    )
    return ExecutionReceipt(
        ok=True, execution_id=execution_id, operation=cmd.operation,
        source=cmd.source, idempotency_key=cmd.idempotency_key,
        mode=mode, symbol=cmd.normalized_symbol(), order_id=oid,
        broker_status=watch.ack_status if watch else None, timings=timings,
    )
