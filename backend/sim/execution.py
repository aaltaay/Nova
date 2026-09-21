"""ADR 007 send path for Sim Fill -- never calls ibkr.orders."""
from __future__ import annotations

import time
from typing import TYPE_CHECKING

from constants_sim import SIM_MODE_LABEL, SIM_ORDER_TYPE_CODE
from execution import inflight
from execution import store
from execution import telemetry
from execution.models import ExecutionCommand, ExecutionReceipt, StageTimings
from execution.nova_placed import persist_nova_placed_at
from execution.store_facts import persist_successful_cancel
from ibkr.safety import PROTECTIVE_SOURCES
from sim import broker as _broker
from sim import practice
from sim.fill_model import SUPPORTED_ORDER_TYPES

if TYPE_CHECKING:
    from execution.broker_send import RejectFn
else:
    RejectFn = object  # runtime: send_broker passes the real callable


async def send_sim_broker(
    cmd: ExecutionCommand,
    execution_id: str,
    timings: StageTimings,
    *,
    wait_ack: bool = True,
    reject,
) -> ExecutionReceipt:
    del wait_ack
    symbol = cmd.normalized_symbol()
    mode = SIM_MODE_LABEL

    if cmd.operation == "bracket":
        return reject(
            execution_id, cmd, timings,
            "Practice orders do not support brackets",
            "SIM_NO_BRACKET",
        )

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
        raw = _broker.cancel(cmd.order_id)
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
        timings.broker_ack_ns = time.perf_counter_ns()
        inflight.release_order(cmd.order_id)
        persist_successful_cancel(
            execution_id, order_id=cmd.order_id, perm_id=cmd.order_id,
            broker_ack_ns=timings.broker_ack_ns, broker_status="Cancelled",
            verified_gone=True,
        )
        watch.note_status(
            "Cancelled", filled=0, remaining=0, perm_id=int(cmd.order_id),
            callback_perf_ns=time.perf_counter_ns(),
        )
        return ExecutionReceipt(
            ok=True, execution_id=execution_id, operation=cmd.operation,
            source=cmd.source, idempotency_key=cmd.idempotency_key,
            mode=mode, order_id=cmd.order_id,
            broker_status="Cancelled", timings=timings,
        )

    if cmd.operation == "replace":
        raw = _broker.replace(
            int(cmd.order_id or 0),
            limit_price=cmd.limit_price,
            stop_price=cmd.stop_price,
        )
        if not raw.get("ok"):
            return reject(
                execution_id, cmd, timings,
                str(raw.get("error") or "replace failed"),
                "REPLACE_NOT_OPEN",
            )
        timings.broker_sent_ns = time.perf_counter_ns()
        persist_nova_placed_at(execution_id, raw.get("nova_placed_at"))
        return await _receipt_from_raw(cmd, execution_id, timings, raw, mode)

    protective = cmd.source in PROTECTIVE_SOURCES
    if not protective:
        ok, reason, code = practice.admission(symbol or "")
        if not ok:
            return reject(execution_id, cmd, timings, reason, code)

    typ = (cmd.order_type or "MKT").upper()
    if typ not in SUPPORTED_ORDER_TYPES:
        return reject(
            execution_id, cmd, timings,
            "Practice orders support MKT, LMT and STP",
            SIM_ORDER_TYPE_CODE,
        )

    timings.broker_sent_ns = time.perf_counter_ns()
    store.update_stages(
        execution_id, status="sent", broker_sent_ns=timings.broker_sent_ns,
        mode=mode, symbol=symbol,
    )
    raw = _broker.place(
        symbol=symbol or "",
        side=(cmd.side or "BUY").upper(),
        qty=float(cmd.qty or 0),
        order_type=typ,
        limit_price=cmd.limit_price,
        stop_price=cmd.stop_price,
        outside_rth=True,
        protective=protective,
    )
    return await _receipt_from_raw(cmd, execution_id, timings, raw, mode)


async def _receipt_from_raw(
    cmd: ExecutionCommand,
    execution_id: str,
    timings: StageTimings,
    raw: dict,
    mode: str,
) -> ExecutionReceipt:
    from execution.broker_send import finish_place

    oid = raw.get("order_id")
    watch = (
        telemetry.watch_order(
            int(oid), execution_id, fresh=False,
            side=(cmd.side or "BUY").upper(),
            reference_price=(
                cmd.reference_price
                if cmd.reference_price is not None
                else cmd.limit_price if cmd.limit_price is not None
                else cmd.stop_price
            ),
            reference_source="sim_fill",
        )
        if oid
        else None
    )
    receipt = await finish_place(
        execution_id, cmd, timings, raw, watch, mode, wait_ack=False,
    )
    if receipt.ok and not receipt.broker_status:
        receipt.broker_status = raw.get("broker_status")
        if receipt.broker_status == "Filled" and timings.filled_ns is None:
            timings.filled_ns = time.perf_counter_ns()
    return receipt
