"""Sole public broker-mutation entry point (ADR 007)."""
from __future__ import annotations

import asyncio
import logging
import time

from constants import (
    IBKR_FORCE_ONE_SHARE,
    IBKR_LOOP_WEDGED_ORDER_MSG,
)
from execution import inflight
from execution import store
from execution import telemetry
from execution import validate as _validate
from execution import evidence_store
from execution.desk_mode import desk_mode
from execution import timing as _timing
from execution.broker_send import send_broker, wait_broker_ack
from execution.latency import latency_summary
from execution.models import ExecutionCommand, ExecutionReceipt, StageTimings
from execution.qty_gate import apply_force_one_share
from execution.record_payload import build_reserve_payload
from execution.store_facts import lookup_symbol_for_order_id
from execution import verification_gate
from ibkr import client as _client
import loop_lag as _loop_lag

logger = logging.getLogger(__name__)

_lock = asyncio.Lock()

__all__ = [
    "execute", "finalize_http_response", "get_execution",
    "latency_summary", "reset_for_tests",
]


def _receipt_from_row(row: dict, *, duplicate: bool = False) -> ExecutionReceipt:
    same_boot = row.get("boot_id") == store.current_boot_id()
    timings = (
        StageTimings(
            received_ns=int(row["received_ns"]),
            validation_completed_ns=row.get("validation_completed_ns"),
            persisted_ns=row.get("persisted_ns"),
            broker_sent_ns=row.get("broker_sent_ns"),
            broker_ack_ns=row.get("broker_ack_ns"),
            filled_ns=row.get("filled_ns"),
        )
        if same_boot else None
    )
    payload = dict(row.get("payload") or {})
    if not same_boot:
        payload["timing_excluded_reason"] = "cross_boot"
    ok = row.get("status") in ("acked", "filled", "sent", "duplicate_replay")
    if row.get("status") in ("rejected", "failed"):
        ok = False
    if duplicate and row.get("order_id") is not None:
        ok = True
    return ExecutionReceipt(
        ok=ok and not row.get("error"),
        execution_id=row["id"],
        operation=row["operation"],  # type: ignore[arg-type]
        source=row["source"],  # type: ignore[arg-type]
        idempotency_key=row["idempotency_key"],
        error=row.get("error"),
        reason_code=row.get("reason_code"),
        mode=row.get("mode"),
        symbol=row.get("symbol"),
        order_id=row.get("order_id"),
        parent_order_id=row.get("parent_order_id"),
        target_order_id=row.get("target_order_id"),
        stop_order_id=row.get("stop_order_id"),
        broker_status=row.get("broker_status"),
        duplicate=duplicate,
        timings=timings,
        payload=payload,
    )


def _open_order_symbol(order_id: int) -> str | None:
    """Best-effort symbol from IB open orders when cancel omitted it."""
    if _client.get_ib() is None:
        return None
    try:
        from ibkr import orders as _orders

        for row in _orders.open_orders():
            if int(row.get("order_id") or 0) == order_id:
                symbol = str(row.get("symbol") or "").strip().upper()
                return symbol or None
    except Exception:
        logger.debug(
            "execution: open-order symbol lookup failed for %s",
            order_id,
            exc_info=True,
        )
    return None


def _reject(
    execution_id: str,
    cmd: ExecutionCommand,
    timings: StageTimings,
    detail: str,
    reason_code: str,
) -> ExecutionReceipt:
    mode = desk_mode()  # the venue on Paper / Sim (QA R38)
    store.update_stages(
        execution_id,
        status="rejected",
        reason_code=reason_code,
        error=detail,
        mode=mode,
        validation_completed_ns=timings.validation_completed_ns,
        persisted_ns=timings.persisted_ns,
    )
    return ExecutionReceipt(
        ok=False,
        execution_id=execution_id,
        operation=cmd.operation,
        source=cmd.source,
        idempotency_key=cmd.idempotency_key,
        error=detail,
        reason_code=reason_code,
        mode=mode,
        symbol=cmd.normalized_symbol(),
        timings=timings,
    )


def _commit_position(
    cmd: ExecutionCommand, execution_id: str, symbol: str | None,
) -> None:
    """Hold the position this send will consume until the order resolves.

    Short-opening SELLs are skipped — they add exposure instead of spending a
    long, and holding one would refuse a legitimate exit in the same symbol.
    """
    if cmd.operation != "place" or not symbol:
        return
    if (cmd.side or "").upper() == "SELL" and getattr(cmd, "short_entry", False):
        return
    inflight.commit(execution_id, symbol=symbol, side=cmd.side, qty=cmd.qty)


async def execute(
    cmd: ExecutionCommand,
    *,
    received_ns: int | None = None,
    wait_ack: bool = True,
) -> ExecutionReceipt:
    """Receive → validate → persist → send → track ack.

    Strategies / UI / agents must call this — never ibkr.orders directly.
    """
    requested_qty = (
        float(cmd.qty) if cmd.qty is not None
        else float(cmd.shares) if cmd.shares is not None
        else None
    )
    # MASTER TEST GATE — see IBKR_FORCE_ONE_SHARE in constants_ibkr.py.
    # One line to remove: delete the next assignment (or set the constant False).
    cmd = apply_force_one_share(cmd)
    sent_qty = (
        float(cmd.qty) if cmd.qty is not None
        else float(cmd.shares) if cmd.shares is not None
        else requested_qty
    )

    store.init_db()
    received = received_ns if received_ns is not None else time.perf_counter_ns()
    timings = StageTimings(received_ns=received)
    symbol = cmd.normalized_symbol()
    if cmd.operation == "cancel" and not symbol and cmd.order_id:
        symbol = lookup_symbol_for_order_id(int(cmd.order_id)) or _open_order_symbol(
            int(cmd.order_id)
        )
    requested_price = (
        cmd.limit_price if cmd.limit_price is not None
        else cmd.stop_price if cmd.stop_price is not None
        else cmd.entry_price
    )
    measurement = _timing.initial_measurement(
        browser_timing=cmd.client_timing,
        backend_ingress_perf_ns=received,
        backend_ingress_wall_ns=cmd.backend_ingress_wall_ns or time.time_ns(),
    )
    async with _lock:
        execution_id, is_new = store.reserve(
            idempotency_key=cmd.idempotency_key,
            operation=cmd.operation,
            source=cmd.source,
            symbol=symbol,
            received_ns=received,
            payload=build_reserve_payload(
                cmd,
                requested_qty=requested_qty,
                sent_qty=sent_qty,
                requested_price=requested_price,
                measurement=measurement,
                # Truthful stamp: only when the gate actually changed the size
                # (a protective order or an order already at 1 share is not clamped).
                forced_one_share=bool(IBKR_FORCE_ONE_SHARE)
                and requested_qty is not None
                and sent_qty is not None
                and sent_qty != requested_qty,
            ),
        )
        timings.persisted_ns = time.perf_counter_ns()
        store.update_stages(execution_id, persisted_ns=timings.persisted_ns)

        if not is_new:
            row = store.get_by_id(execution_id)
            assert row is not None
            # Replay prior outcome — never send a second broker order.
            store.update_stages(execution_id, status="duplicate_replay")
            logger.warning(
                "execution: duplicate idempotency_key=%s → id=%s",
                cmd.idempotency_key,
                execution_id,
            )
            return _receipt_from_row(row, duplicate=True)

        ok, detail, reason = _validate.validate_command(cmd)
        if not ok:
            timings.validation_completed_ns = time.perf_counter_ns()
            return _reject(execution_id, cmd, timings, detail, reason or "VALIDATION")

        # Kill switch is checked BEFORE skip_risk (D-037): a tripped kill means
        # no Nova-originated spend of any source, so manual ticket places and
        # Nova Action hotkeys (which pass skip_risk=True) are refused too.
        # Only protective sources may still reach the broker.
        if cmd.operation in ("place", "bracket") and cmd.source not in (
            "kill", "flatten", "cancel_working",
        ):
            import kill_switch as _kill_switch

            if _kill_switch.is_tripped():
                timings.validation_completed_ns = time.perf_counter_ns()
                return _reject(
                    execution_id, cmd, timings,
                    "Kill switch tripped — reset it before placing any order",
                    "KILL_SWITCH",
                )
            from bot.buy_lock import buy_blocked

            locked, lock_reason = buy_blocked(cmd.side, cmd.source)
            if locked:
                timings.validation_completed_ns = time.perf_counter_ns()
                return _reject(
                    execution_id, cmd, timings,
                    "Bot -$200 day lock -- buys unlock next calendar midnight America/New_York",
                    lock_reason or "BOT_DAY_LOCK",
                )

        # Walk-away rules (strategy/risk.py). The manual ticket and the bot pass
        # skip_risk=True, so since the Phase D executor was retired (ADR 025) no
        # current source reaches this block; who these rules gate is an open
        # operator decision, not changed here.
        if not cmd.skip_risk and cmd.operation in ("place", "bracket"):
            from strategy import risk as _risk

            can_trade, halt = _risk.can_trade()
            if not can_trade and cmd.source not in ("flatten", "kill"):
                timings.validation_completed_ns = time.perf_counter_ns()
                return _reject(execution_id, cmd, timings, halt, "RISK_HALT")

            if cmd.operation == "bracket" and cmd.entry_price and cmd.stop_price and cmd.target_price:
                plan_ok, issues = _risk.validate_trade_plan(
                    cmd.entry_price, cmd.stop_price, cmd.target_price,
                )
                if not plan_ok:
                    timings.validation_completed_ns = time.perf_counter_ns()
                    return _reject(execution_id, cmd, timings, "; ".join(issues), "PLAN_INVALID")

        ok, detail, reason = _validate.check_account_and_position(cmd)
        if not ok:
            timings.validation_completed_ns = time.perf_counter_ns()
            return _reject(execution_id, cmd, timings, detail, reason or "ACCOUNT")

        verification_block = verification_gate.entry_block(cmd)
        if verification_block is not None:
            timings.validation_completed_ns = time.perf_counter_ns()
            return _reject(
                execution_id,
                cmd,
                timings,
                verification_block.message,
                verification_block.reason_code,
            )

        timings.validation_completed_ns = time.perf_counter_ns()
        store.update_stages(
            execution_id,
            status="validated",
            validation_completed_ns=timings.validation_completed_ns,
            mode=desk_mode(),
        )

        if _loop_lag.is_wedged() and cmd.operation in (
            "place", "bracket", "cancel", "replace",
        ):
            return _reject(
                execution_id, cmd, timings,
                IBKR_LOOP_WEDGED_ORDER_MSG, "IB_LOOP_WEDGED",
            )

        ib = _client.get_ib()
        telemetry.ensure_handlers(ib)

        # ADR 007 decision 5: the lock covers reservation, validation, and the
        # synchronous broker send. Commit the shares first so a command that
        # validates behind this one cannot spend them again (D-011).
        _commit_position(cmd, execution_id, symbol)
        receipt = await send_broker(
            cmd, execution_id, timings, wait_ack=False, reject=_reject,
        )
        if receipt.ok:
            inflight.attach_order(execution_id, receipt.order_id)
            # A practice order can fill inside the send (ADR 020), so its
            # terminal notice ran before the order id was attached and found
            # nothing to free. The ack wait frees it for wait_ack=True; KILL,
            # flatten, bot and strategy sends skip that wait and kept their
            # shares "already sent" until a restart (QA R31, 2026-09-22).
            if receipt.timings.filled_ns or str(receipt.broker_status or "") == "Filled":
                inflight.release_execution(execution_id)
        else:
            inflight.release_execution(execution_id)

    # Only the acknowledgment wait happens after release, so a slow order
    # cannot block an urgent cancel/flatten send.
    if wait_ack:
        return await wait_broker_ack(cmd, receipt)
    return receipt


def get_execution(execution_id: str) -> dict | None:
    row = store.get_by_id(execution_id)
    if row is None:
        return None
    fills = evidence_store.list_for_execution(execution_id)
    row["fill_evidence"] = fills
    aggregate_fills = [
        item for item in fills if bool(item.get("aggregate_eligible", 1))
    ]
    row["first_fill"] = aggregate_fills[0] if aggregate_fills else None
    row["complete_fill"] = next(
        (
            item for item in aggregate_fills
            if item["fill_state"] == "complete"
        ),
        None,
    )
    return row


def finalize_http_response(execution_id: str, *, duplicate: bool = False) -> dict:
    """Persist and return the handler response-ready mark (not frontend render)."""
    row = store.get_by_id(execution_id) or {}
    if duplicate:
        original = dict((row.get("payload") or {}).get("measurement") or {})
        original["replay_note"] = (
            "idempotency replay; timings belong to the original execution"
        )
        return original
    if row.get("boot_id") != store.current_boot_id():
        return {
            "schema_version": 1,
            "backend": {
                "clock_domain": "backend.perf_counter_ns",
                "ingress_to_response_ready_ms": None,
                "response_mark": "handler_response_ready_not_socket_or_frontend_render",
            },
            "cross_clock_arithmetic": "forbidden",
            "timing_excluded_reason": "cross_boot_idempotency_replay",
            "frontend_render": {
                "status": "not_measured_by_backend",
                "owner": "widgets",
            },
        }
    payload = row.get("payload") or {}
    measurement = _timing.response_ready_measurement(payload.get("measurement") or {})
    evidence_store.merge_execution_payload(
        execution_id, {"measurement": measurement},
    )
    return measurement


def reset_for_tests() -> None:
    telemetry.reset_for_tests()
    verification_gate.reset_for_tests()
    inflight.reset_for_tests()
