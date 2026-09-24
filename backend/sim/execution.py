"""ADR 007 send path for the practice venues -- never calls ibkr.orders.

``send_practice_broker`` is the one send path Paper and Sim share (ADR 020):
the caller hands it the venue's ``PracticeBroker`` (``practice.broker.for_venue``)
and the receipt's ``mode`` is that broker's venue label (``paper`` or ``sim``).
Admission comes from the broker's own market reference -- the loaded replay on
Sim, the live feed on Paper -- so the desk never guesses a price.
``send_sim_broker`` keeps the Sim-only entry point every existing caller uses.
"""
from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from constants_practice import PRACTICE_VENUE_SIM
from constants_sim import SIM_ORDER_TYPE_CODE
from execution import inflight
from execution import store
from execution import telemetry
from execution.models import ExecutionCommand, ExecutionReceipt, StageTimings
from execution.nova_placed import persist_nova_placed_at
from execution.store_facts import persist_successful_cancel
from ibkr.safety import PROTECTIVE_SOURCES
from practice.watch import note_answer
from sim.fill_model import SUPPORTED_ORDER_TYPES

if TYPE_CHECKING:
    from execution.broker_send import RejectFn
    from practice.broker import PracticeBroker
else:
    RejectFn = object  # runtime: send_broker passes the real callable
    PracticeBroker = Any


async def send_sim_broker(
    cmd: ExecutionCommand,
    execution_id: str,
    timings: StageTimings,
    *,
    wait_ack: bool = True,
    reject,
) -> ExecutionReceipt:
    """The Sim venue's send: ``send_practice_broker`` on the Sim broker."""
    from practice.broker import for_venue

    return await send_practice_broker(
        cmd, execution_id, timings, broker=for_venue(PRACTICE_VENUE_SIM),
        wait_ack=wait_ack, reject=reject,
    )


async def send_practice_broker(
    cmd: ExecutionCommand,
    execution_id: str,
    timings: StageTimings,
    *,
    broker: PracticeBroker,
    wait_ack: bool = True,
    reject,
) -> ExecutionReceipt:
    del wait_ack
    symbol = cmd.normalized_symbol()
    mode = str(broker.venue)

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
        raw = broker.cancel(cmd.order_id, source=cmd.source)
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
        raw = broker.replace(
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
        ok, reason, code = broker.reference.admission(symbol or "")
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
    raw = broker.place(
        symbol=symbol or "",
        side=(cmd.side or "BUY").upper(),
        qty=float(cmd.qty or 0),
        order_type=typ,
        limit_price=cmd.limit_price,
        stop_price=cmd.stop_price,
        outside_rth=True,
        protective=protective,
        source=cmd.source,
        tif=cmd.tif,
        short_entry=bool(cmd.short_entry),
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
            reference_source=f"{mode}_fill",
        )
        if oid
        else None
    )
    if watch is not None and raw.get("ok"):
        # The venue answered inside the send: that answer is the ack, so the
        # door's ack wait returns at once instead of timing out (2026-09-24).
        note_answer(watch, raw)
        timings.broker_ack_ns = watch.ack_ns
        timings.filled_ns = watch.filled_ns or timings.filled_ns
        if str(raw.get("broker_status") or "") in telemetry.TERMINAL_REJECT_STATUSES:
            # Cancelled at the fill (practice.order_rules.fill_refusal): a
            # refusal in the venue's own words, never an order reported placed.
            raw = {
                **raw, "ok": False,
                "error": raw.get("status_reason") or f"The {mode} venue cancelled the order",
                "reason_code": raw.get("status_code"),
            }
    receipt = await finish_place(
        execution_id, cmd, timings, raw, watch, mode, wait_ack=False,
    )
    if not receipt.ok and raw.get("reason_code"):
        # The venue refused in its own words (PRACTICE_NO_SHORTS,
        # PRACTICE_BUYING_POWER, TIF_INVALID, SIM_*): keep that code on the
        # receipt and the store instead of the generic BROKER_REJECT.
        receipt.reason_code = str(raw["reason_code"])
        store.update_stages(execution_id, reason_code=receipt.reason_code)
    if not receipt.ok and oid:
        # The venue took the order, then cancelled it at the fill: name it.
        receipt.order_id = int(oid)
        receipt.broker_status = raw.get("broker_status")
        store.update_stages(execution_id, order_id=int(oid), broker_status=receipt.broker_status)
    if receipt.ok and not receipt.broker_status:
        receipt.broker_status = raw.get("broker_status")
        if receipt.broker_status == "Filled" and timings.filled_ns is None:
            timings.filled_ns = time.perf_counter_ns()
    if receipt.ok and str(raw.get("broker_status") or "") == "Filled":
        # Filled inside the send: the broker's own notice ran before this row
        # carried its order id, so nothing marked it -- KILL / flatten / bot
        # closes sat "sent" or "acked" for good (QA R41).
        if timings.filled_ns is None:
            timings.filled_ns = time.perf_counter_ns()
        store.update_stages(
            execution_id, status="filled", broker_status="Filled", filled_ns=timings.filled_ns,
        )
    return receipt
