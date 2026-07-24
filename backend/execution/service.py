"""Sole public broker-mutation entry point (ADR 007)."""
from __future__ import annotations

import asyncio
import logging
import time

from constants import NOVA_OS_MAX_CONCURRENT_POSITIONS
from execution import store
from execution import telemetry
from execution import validate as _validate
from execution import evidence_store
from execution import timing as _timing
from execution.broker_send import send_broker, wait_broker_ack
from execution.latency import latency_summary
from execution.models import ExecutionCommand, ExecutionReceipt, StageTimings
from ibkr import client as _client

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


def _reject(
    execution_id: str,
    cmd: ExecutionCommand,
    timings: StageTimings,
    detail: str,
    reason_code: str,
) -> ExecutionReceipt:
    store.update_stages(
        execution_id,
        status="rejected",
        reason_code=reason_code,
        error=detail,
        mode=_client.account_mode(),
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
        mode=_client.account_mode(),
        symbol=cmd.normalized_symbol(),
        timings=timings,
    )


async def execute(
    cmd: ExecutionCommand,
    *,
    received_ns: int | None = None,
    wait_ack: bool = True,
) -> ExecutionReceipt:
    """Receive → validate → persist → send → track ack.

    Strategies / UI / agents must call this — never ibkr.orders directly.
    """
    store.init_db()
    received = received_ns if received_ns is not None else time.perf_counter_ns()
    timings = StageTimings(received_ns=received)
    symbol = cmd.normalized_symbol()
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
            payload={
                "setup": cmd.setup,
                "order_type": cmd.order_type,
                "side": (cmd.side or "").upper() or None,
                "qty": cmd.qty if cmd.qty is not None else cmd.shares,
                "requested_price": requested_price,
                "reference_price": (
                    cmd.reference_price
                    if cmd.reference_price is not None
                    else requested_price
                ),
                "measurement": measurement,
            },
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

        if not cmd.skip_risk and cmd.operation in ("place", "bracket"):
            from strategy import risk as _risk
            from nova_os import control_mode as _control_mode
            from strategy import executor as _executor

            if _executor.is_kill_switch_tripped() and cmd.source not in (
                "kill", "flatten", "cancel_working",
            ):
                timings.validation_completed_ns = time.perf_counter_ns()
                return _reject(execution_id, cmd, timings, "kill switch tripped", "KILL_SWITCH")

            if cmd.operation == "bracket" and not cmd.skip_concurrency:
                concurrent = len(_executor.open_positions()) + len(
                    __import__("nova_os.staged_tickets", fromlist=["list_staged"]).list_staged()
                )
                if symbol and symbol in _executor.open_positions():
                    timings.validation_completed_ns = time.perf_counter_ns()
                    return _reject(
                        execution_id, cmd, timings,
                        f"{symbol} already has a tracked open position", "ALREADY_OPEN",
                    )
                if concurrent >= NOVA_OS_MAX_CONCURRENT_POSITIONS:
                    timings.validation_completed_ns = time.perf_counter_ns()
                    return _reject(
                        execution_id, cmd, timings,
                        f"at max concurrent ({NOVA_OS_MAX_CONCURRENT_POSITIONS})",
                        "MAX_CONCURRENT",
                    )

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

            if cmd.source == "auto_paper":
                gate_ok, gate_reason = _control_mode.auto_paper_gate_status()
                if not gate_ok:
                    timings.validation_completed_ns = time.perf_counter_ns()
                    return _reject(
                        execution_id, cmd, timings, gate_reason, "AUTO_PAPER_GATE",
                    )

        ok, detail, reason = _validate.check_account_and_position(cmd)
        if not ok:
            timings.validation_completed_ns = time.perf_counter_ns()
            return _reject(execution_id, cmd, timings, detail, reason or "ACCOUNT")

        timings.validation_completed_ns = time.perf_counter_ns()
        store.update_stages(
            execution_id,
            status="validated",
            validation_completed_ns=timings.validation_completed_ns,
            mode=_client.account_mode(),
        )

        ib = _client.get_ib()
        telemetry.ensure_handlers(ib)
        receipt = await send_broker(
            cmd, execution_id, timings, wait_ack=False, reject=_reject,
        )

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
