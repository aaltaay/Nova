"""The Live venue's place, replace and bracket, sent to IBKR without holding the socket loop (#725).

``execution.broker_send`` (on the socket loop) hands Live sends here. Each one awaits
``ibkr.send_hop.send``, which runs the whole ``ibkr.orders`` call on the IB loop -- once, or provably
never -- while every socket keeps flowing. The order's watch is registered in that same IB-loop
callback, right after IBKR's ``placeOrder``, and the order id joins its in-flight commitment there:
a status for an order nobody watches is dropped (``telemetry_handlers``), and a fill heard before the
commitment knew its order id would leave the shares "already sent". On the socket loop either could
come after IBKR's first status.

A desk order carries its deadline (``market_view.gate.send_deadline``): past it, the IB loop refuses
to send the order (``ORDER_LATE``), however long it was busy (ADR 045).
"""
from __future__ import annotations

import logging
import time
from typing import Any, Callable

from constants import (
    EXECUTION_ACK_WAIT_SEC,
    EXECUTOR_ENTRY_SIDE_IBKR,
    EXECUTOR_ENTRY_SIDE_IBKR_SHORT,
    IBKR_ORDER_TIF_DEFAULT,
    IBKR_SEND_HOP_TIMEOUT_SEC,
    IBKR_SEND_NOT_STARTED_MSG,
    IBKR_SEND_RUNNING_GRACE_SEC,
    IBKR_SEND_UNKNOWN_MSG,
)
from execution import inflight, store, telemetry
from execution.models import ExecutionCommand, ExecutionReceipt, StageTimings
from execution.nova_placed import persist_nova_placed_at
from execution.qty_gate import live_cap_refusal
from ibkr import orders as _orders
from ibkr import send_hop
from ibkr.order_build import normalize_tif, tif_error
from market_view import gate as _view_gate

logger = logging.getLogger(__name__)

RejectFn = Callable[[str, ExecutionCommand, StageTimings, str, str], ExecutionReceipt]


def _working_tif(row: dict) -> str:
    """TIF to resend on a price-only replace: the working order's own (#91).

    A TIF Nova does not place (blank, IOC, a TWS-set GTD) falls back to the
    default -- what every replace sent before per-order TIF existed.
    """
    tif = normalize_tif(row.get("tif"))
    return tif if tif_error(tif) is None else IBKR_ORDER_TIF_DEFAULT


def _reference_price(cmd: ExecutionCommand) -> float | None:
    if cmd.reference_price is not None:
        return cmd.reference_price
    return cmd.limit_price if cmd.limit_price is not None else cmd.stop_price


def _watch(order_id: Any, execution_id: str, **kwargs: Any) -> telemetry.OrderWatch | None:
    """Register a watch from inside the send; a failure never loses the order it watches."""
    if not order_id:
        return None
    try:
        return telemetry.watch_order(int(order_id), execution_id, fresh=True, **kwargs)
    except Exception:
        logger.exception("live send: the watch of IBKR order %s could not be registered", order_id)
        return None


async def _hop(
    cmd: ExecutionCommand,
    execution_id: str,
    timings: StageTimings,
    call: Callable[[], Any],
    *,
    mode: str,
    reject: RejectFn,
    label: str,
) -> tuple[Any, ExecutionReceipt | None]:
    """``call`` on the IB loop: ``(result, None)`` when it ran, else ``(None, the refusal)``."""
    try:
        return await send_hop.send(call, not_after=_view_gate.send_deadline(cmd), label=label), None
    except send_hop.SendTooLate:
        late = _view_gate.late_refusal(cmd)
        return None, reject(execution_id, cmd, timings, late.text or "", late.code or "ORDER_LATE")
    except send_hop.SendNotSent:
        detail = IBKR_SEND_NOT_STARTED_MSG.format(sec=IBKR_SEND_HOP_TIMEOUT_SEC)
        return None, reject(execution_id, cmd, timings, detail, "IB_LOOP_WEDGED")
    except send_hop.SendOutcomeUnknown:
        detail = IBKR_SEND_UNKNOWN_MSG.format(sec=IBKR_SEND_RUNNING_GRACE_SEC)
        # Not "rejected": the order may be working at IBKR, and Working orders will show it.
        store.update_stages(execution_id, status="failed", error=detail, reason_code="SEND_UNKNOWN", mode=mode)
        return None, ExecutionReceipt(
            ok=False, execution_id=execution_id, operation=cmd.operation, source=cmd.source,
            idempotency_key=cmd.idempotency_key, error=detail, reason_code="SEND_UNKNOWN",
            mode=mode, symbol=cmd.normalized_symbol(), timings=timings,
        )


async def replace(
    cmd: ExecutionCommand,
    execution_id: str,
    timings: StageTimings,
    *,
    mode: str,
    wait_ack: bool,
    reject: RejectFn,
) -> ExecutionReceipt:
    from execution.broker_send import finish_place

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
    store.update_stages(
        execution_id, status="sent", broker_sent_ns=timings.broker_sent_ns,
        order_id=cmd.order_id, mode=mode,
    )

    def call() -> tuple[dict, telemetry.OrderWatch | None]:
        watch = _watch(
            cmd.order_id, execution_id, leg_role="replace", side=str(existing["side"]).upper(),
            reference_price=_reference_price(cmd), reference_source="replace_request",
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
        inflight.attach_order(execution_id, cmd.order_id)
        return raw, watch

    sent, refusal = await _hop(cmd, execution_id, timings, call, mode=mode, reject=reject, label="replace")
    if refusal is not None:
        return refusal
    raw, watch = sent
    return await finish_place(execution_id, cmd, timings, raw, watch, mode, wait_ack=wait_ack)


async def bracket(
    cmd: ExecutionCommand,
    execution_id: str,
    timings: StageTimings,
    *,
    mode: str,
    symbol: str | None,
    wait_ack: bool,
    reject: RejectFn,
) -> ExecutionReceipt:
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
    exit_side = "SELL" if entry_side == "BUY" else "BUY"

    def call() -> tuple[dict, telemetry.OrderWatch | None]:
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
        inflight.attach_order(execution_id, raw.get("parent_order_id"))
        watch = _watch(
            raw.get("parent_order_id"), execution_id, leg_role="parent", side=entry_side,
            reference_price=cmd.entry_price, reference_source="bracket_entry", aggregate_eligible=True,
        )
        for role, child_id, reference in (
            ("target", raw.get("target_order_id"), cmd.target_price),
            ("stop", raw.get("stop_order_id"), cmd.stop_price),
        ):
            _watch(
                child_id, execution_id, leg_role=role, side=exit_side, reference_price=reference,
                reference_source=f"bracket_{role}", aggregate_eligible=False,
            )
        return raw, watch

    sent, refused = await _hop(cmd, execution_id, timings, call, mode=mode, reject=reject, label="bracket")
    if refused is not None:
        return refused
    raw, watch = sent
    parent = raw.get("parent_order_id")
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


async def place(
    cmd: ExecutionCommand,
    execution_id: str,
    timings: StageTimings,
    *,
    mode: str,
    symbol: str | None,
    wait_ack: bool,
    reject: RejectFn,
) -> ExecutionReceipt:
    from execution.broker_send import finish_place

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
    side = (cmd.side or "BUY").upper()

    def call() -> tuple[dict, telemetry.OrderWatch | None]:
        raw = _orders.place_order(
            symbol=symbol or "",
            side=side,  # type: ignore[arg-type]
            qty=float(cmd.qty or 0),
            order_type=cmd.order_type,  # type: ignore[arg-type]
            limit_price=cmd.limit_price,
            stop_price=cmd.stop_price,
            outside_rth=cmd.outside_rth,
            tif=cmd.tif,
            targeted=cmd.target_venue == "live",
        )
        inflight.attach_order(execution_id, raw.get("order_id"))
        watch = _watch(
            raw.get("order_id"), execution_id, side=side,
            reference_price=_reference_price(cmd), reference_source="execution_command",
        )
        return raw, watch

    sent, refused = await _hop(cmd, execution_id, timings, call, mode=mode, reject=reject, label="order")
    if refused is not None:
        return refused
    raw, watch = sent
    return await finish_place(execution_id, cmd, timings, raw, watch, mode, wait_ack=wait_ack)
