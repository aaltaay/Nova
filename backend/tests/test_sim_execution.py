"""Sim places go through ADR 007, not ibkr.orders."""
from __future__ import annotations

import pytest

from execution.models import ExecutionCommand, StageTimings
from execution.validate import validate_command
from sim.execution import send_sim_broker
from sim.mode import reset_for_tests, set_sim_mode
from sim import broker


def setup_function() -> None:
    reset_for_tests()
    set_sim_mode(True)
    from execution import store

    store.init_db()


def teardown_function() -> None:
    reset_for_tests()


def _reject(execution_id, cmd, timings, detail, reason):
    from execution.models import ExecutionReceipt

    return ExecutionReceipt(
        ok=False,
        execution_id=execution_id,
        operation=cmd.operation,
        source=cmd.source,
        idempotency_key=cmd.idempotency_key,
        error=detail,
        reason_code=reason,
        timings=timings,
    )


@pytest.mark.asyncio
async def test_validate_and_fill_market_buy() -> None:
    cmd = ExecutionCommand(
        operation="place",
        idempotency_key="sim-mkt-1",
        source="manual",
        symbol="SIM1",
        side="BUY",
        qty=1,
        order_type="MKT",
    )
    ok, detail, reason = validate_command(cmd)
    assert ok is True, detail
    assert reason is None
    receipt = await send_sim_broker(
        cmd, "exec-sim-1", StageTimings(received_ns=0), wait_ack=False, reject=_reject,
    )
    assert receipt.ok is True
    assert receipt.mode == "sim"
    assert receipt.broker_status == "Filled"
    assert broker.positions()[0]["qty"] == 1


@pytest.mark.asyncio
async def test_bracket_rejected() -> None:
    cmd = ExecutionCommand(
        operation="bracket",
        idempotency_key="sim-br-1",
        source="manual",
        symbol="SIM1",
        side="BUY",
        qty=1,
        entry_price=25.0,
        stop_price=24.0,
        target_price=26.0,
    )
    receipt = await send_sim_broker(
        cmd, "exec-sim-br", StageTimings(received_ns=0), wait_ack=False, reject=_reject,
    )
    assert receipt.ok is False
    assert receipt.reason_code == "SIM_NO_BRACKET"


@pytest.mark.asyncio
async def test_real_ticker_place_refused() -> None:
    cmd = ExecutionCommand(
        operation="place",
        idempotency_key="sim-spy-1",
        source="manual",
        symbol="SPY",
        side="BUY",
        qty=1,
        order_type="MKT",
    )
    ok, _detail, reason = validate_command(cmd)
    assert ok is False
    assert reason == "SIM_SYMBOL"
    receipt = await send_sim_broker(
        cmd, "exec-sim-spy", StageTimings(received_ns=0), wait_ack=False, reject=_reject,
    )
    assert receipt.ok is False
    assert receipt.reason_code == "SIM_SYMBOL"
