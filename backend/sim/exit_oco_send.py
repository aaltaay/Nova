"""The exit-only pair's send on the practice venues (#681): ``PracticeBroker.place_exit_oco`` through the door.

The execution door validated it and committed its shares once (``execution.venue_door``); this hands the
venue's broker the pair -- a stop for every share and a target per half -- and records what it answered:
one watch per leg (none counts toward the execution's own fills: the pair closes a position, it buys
nothing), the stop's id as the execution's ``order_id`` (its close frees the commitment, as any order's
does), the targets' ids beside it (a second target's in the row's payload, which has no column for it).
The broker answers inside the send, so its answer about the stop is the acknowledgment.
"""
from __future__ import annotations

import time
from typing import Any

from execution import inflight, store, telemetry
from execution.evidence_store import merge_execution_payload
from execution.models import ExecutionCommand, ExecutionReceipt, StageTimings
from execution.nova_placed import persist_nova_placed_at
from practice.watch import note_answer


async def send_exit_oco(
    cmd: ExecutionCommand,
    execution_id: str,
    timings: StageTimings,
    *,
    broker: Any,
    reject: Any,
) -> ExecutionReceipt:
    symbol = cmd.normalized_symbol() or ""
    mode = str(broker.venue)
    ok, reason, code = broker.reference.admission(symbol)
    if not ok:
        return reject(execution_id, cmd, timings, reason, code)
    side = (cmd.side or "").upper()
    timings.broker_sent_ns = time.perf_counter_ns()
    store.update_stages(execution_id, status="sent", broker_sent_ns=timings.broker_sent_ns, mode=mode, symbol=symbol)
    raw = broker.place_exit_oco(
        symbol, side, float(cmd.qty or 0), float(cmd.stop_price or 0), float(cmd.target_price or 0),
        target2_price=cmd.target2_price, target1_qty=cmd.target1_qty, tif=cmd.tif, source=cmd.source,
        origin=cmd.origin,
    )
    stop_id = raw.get("stop_order_id")
    if not raw.get("ok") or stop_id is None:
        refused = str(raw.get("reason_code") or "BROKER_REJECT")   # the venue's own words
        store.update_stages(execution_id, status="failed", error=str(raw.get("error")), reason_code=refused)
        return ExecutionReceipt(
            ok=False, execution_id=execution_id, operation=cmd.operation, source=cmd.source,
            idempotency_key=cmd.idempotency_key, error=raw.get("error"), reason_code=refused, mode=mode,
            symbol=symbol, timings=timings,
        )
    watch = None
    for role, child, reference in (
        ("stop", stop_id, cmd.stop_price),
        ("target", raw.get("target_order_id"), cmd.target_price),
        ("target2", raw.get("target2_order_id"), cmd.target2_price),
    ):
        if child is None:
            continue
        leg = telemetry.watch_order(
            int(child), execution_id, venue=mode, fresh=True, leg_role=role, side=side,
            reference_price=reference, reference_source=f"exit_oco_{role}", aggregate_eligible=False,
        )
        watch = watch or leg
    note_answer(watch, raw)
    timings.broker_ack_ns = watch.ack_ns
    persist_nova_placed_at(execution_id, raw.get("nova_placed_at"))
    target2_id = raw.get("target2_order_id")
    if target2_id is not None:
        merge_execution_payload(execution_id, {"target2_order_id": int(target2_id)})
    status = str(raw.get("broker_status") or "")
    if status in ("Filled", *telemetry.TERMINAL_REJECT_STATUSES):
        # The stop closed inside the send (it filled, or the targets spent it): its notice ran before this
        # execution held its order id, so the commitment is freed here.
        inflight.release_execution(execution_id)
    ids = {"order_id": int(stop_id), "stop_order_id": int(stop_id), "target_order_id": raw.get("target_order_id")}
    store.update_stages(execution_id, status="acked", broker_ack_ns=timings.broker_ack_ns, broker_status=status,
                        **ids)
    return ExecutionReceipt(
        ok=True, execution_id=execution_id, operation=cmd.operation, source=cmd.source,
        idempotency_key=cmd.idempotency_key, mode=mode, symbol=symbol, broker_status=status, timings=timings,
        target2_order_id=int(target2_id) if target2_id is not None else None, **ids,
    )
