"""Sole public broker-mutation entry point (ADR 007)."""
from __future__ import annotations

import asyncio
import logging
import time

from constants import NOVA_OS_MAX_CONCURRENT_POSITIONS
from execution import store
from execution import telemetry
from execution import validate as _validate
from execution.broker_send import send_broker, wait_broker_ack
from execution.latency import latency_summary
from execution.models import ExecutionCommand, ExecutionReceipt, StageTimings
from ibkr import client as _client

logger = logging.getLogger(__name__)

_lock = asyncio.Lock()

__all__ = ["execute", "get_execution", "latency_summary", "reset_for_tests"]


def _receipt_from_row(row: dict, *, duplicate: bool = False) -> ExecutionReceipt:
    timings = StageTimings(
        received_ns=int(row["received_ns"]),
        validation_completed_ns=row.get("validation_completed_ns"),
        persisted_ns=row.get("persisted_ns"),
        broker_sent_ns=row.get("broker_sent_ns"),
        broker_ack_ns=row.get("broker_ack_ns"),
        filled_ns=row.get("filled_ns"),
    )
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
        payload=row.get("payload") or {},
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

    async with _lock:
        execution_id, is_new = store.reserve(
            idempotency_key=cmd.idempotency_key,
            operation=cmd.operation,
            source=cmd.source,
            symbol=symbol,
            received_ns=received,
            payload={"setup": cmd.setup, "order_type": cmd.order_type},
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
        timings.validation_completed_ns = time.perf_counter_ns()
        if not ok:
            return _reject(execution_id, cmd, timings, detail, reason or "VALIDATION")

        if not cmd.skip_risk and cmd.operation in ("place", "bracket"):
            from strategy import risk as _risk
            from nova_os import control_mode as _control_mode
            from strategy import executor as _executor

            if _executor.is_kill_switch_tripped() and cmd.source not in (
                "kill", "flatten", "cancel_working",
            ):
                return _reject(execution_id, cmd, timings, "kill switch tripped", "KILL_SWITCH")

            if cmd.operation == "bracket" and not cmd.skip_concurrency:
                concurrent = len(_executor.open_positions()) + len(
                    __import__("nova_os.staged_tickets", fromlist=["list_staged"]).list_staged()
                )
                if symbol and symbol in _executor.open_positions():
                    return _reject(
                        execution_id, cmd, timings,
                        f"{symbol} already has a tracked open position", "ALREADY_OPEN",
                    )
                if concurrent >= NOVA_OS_MAX_CONCURRENT_POSITIONS:
                    return _reject(
                        execution_id, cmd, timings,
                        f"at max concurrent ({NOVA_OS_MAX_CONCURRENT_POSITIONS})",
                        "MAX_CONCURRENT",
                    )

            can_trade, halt = _risk.can_trade()
            if not can_trade and cmd.source not in ("flatten", "kill"):
                return _reject(execution_id, cmd, timings, halt, "RISK_HALT")

            if cmd.operation == "bracket" and cmd.entry_price and cmd.stop_price and cmd.target_price:
                plan_ok, issues = _risk.validate_trade_plan(
                    cmd.entry_price, cmd.stop_price, cmd.target_price,
                )
                if not plan_ok:
                    return _reject(execution_id, cmd, timings, "; ".join(issues), "PLAN_INVALID")

            if cmd.source == "auto_paper":
                gate_ok, gate_reason = _control_mode.auto_paper_gate_status()
                if not gate_ok:
                    return _reject(
                        execution_id, cmd, timings, gate_reason, "AUTO_PAPER_GATE",
                    )

        ok, detail, reason = _validate.check_account_and_position(cmd)
        if not ok:
            return _reject(execution_id, cmd, timings, detail, reason or "ACCOUNT")

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
    return store.get_by_id(execution_id)


def reset_for_tests() -> None:
    telemetry.reset_for_tests()
