"""MASTER TEST QTY GATE — IBKR_FORCE_ONE_SHARE (intentional; not a bug)."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import execution.qty_gate as qty_gate
import execution.service as exec_svc
import execution.store as store
import execution.telemetry as telemetry
import ibkr.account as account_mod
import ibkr.client as client_mod
import ibkr.orders as orders_mod
import ibkr.safety as safety_mod
import strategy.executor as executor
import strategy.risk as risk_mod
from execution.models import ExecutionCommand
from nova_os import control_mode, staged_tickets


@pytest.fixture(autouse=True)
def isolated_execution(tmp_path, monkeypatch):
    monkeypatch.setattr("paths.cache_dir", lambda: tmp_path)
    monkeypatch.setattr("execution.store.cache_dir", lambda: tmp_path)
    import execution.broker_send as broker_send

    monkeypatch.setattr(broker_send, "EXECUTION_ACK_WAIT_SEC", 0.05)
    store.init_db()
    telemetry.reset_for_tests()
    control_mode.reset_for_tests()
    staged_tickets.reset_for_tests()
    risk_mod.reset_day()
    executor._kill_switch_tripped = False
    executor._open_positions.clear()
    yield
    telemetry.reset_for_tests()
    control_mode.reset_for_tests()
    staged_tickets.reset_for_tests()
    risk_mod.reset_day()
    executor._kill_switch_tripped = False
    executor._open_positions.clear()


def _arm_paper(monkeypatch):
    monkeypatch.setattr(client_mod, "is_enabled", lambda: True)
    monkeypatch.setattr(client_mod, "is_connected", lambda: True)
    monkeypatch.setattr(client_mod, "account_mode", lambda: "paper")
    monkeypatch.setattr(client_mod, "broker_account_kind", lambda: "paper")
    monkeypatch.setattr(client_mod, "get_ib", lambda: None)
    monkeypatch.setattr(safety_mod, "orders_enabled", lambda: True)
    monkeypatch.setenv("IBKR_GATEWAY_MODE", "paper")
    monkeypatch.setattr(
        account_mod,
        "get_account_summary",
        lambda: {"connected": True, "BuyingPower": 100_000.0, "pending": False},
    )
    monkeypatch.setattr(account_mod, "get_positions", lambda: [])


def test_apply_force_clamps_place_qty(monkeypatch):
    monkeypatch.setattr(qty_gate, "IBKR_FORCE_ONE_SHARE", True)
    monkeypatch.setattr(qty_gate, "IBKR_FORCE_ONE_SHARE_QTY", 1.0)
    cmd = ExecutionCommand(
        operation="place",
        idempotency_key="g1",
        source="manual",
        symbol="AAPL",
        side="BUY",
        qty=500,
        order_type="MKT",
    )
    out = qty_gate.apply_force_one_share(cmd)
    assert out.qty == 1.0
    assert cmd.qty == 500


def test_apply_force_off_passthrough(monkeypatch):
    monkeypatch.setattr(qty_gate, "IBKR_FORCE_ONE_SHARE", False)
    cmd = ExecutionCommand(
        operation="place",
        idempotency_key="g2",
        source="manual",
        symbol="AAPL",
        side="BUY",
        qty=500,
        order_type="MKT",
    )
    assert qty_gate.apply_force_one_share(cmd).qty == 500


def test_execute_sends_one_share_when_gate_on(monkeypatch):
    _arm_paper(monkeypatch)
    monkeypatch.setattr(qty_gate, "IBKR_FORCE_ONE_SHARE", True)
    monkeypatch.setattr(qty_gate, "IBKR_FORCE_ONE_SHARE_QTY", 1.0)
    monkeypatch.setattr(exec_svc, "IBKR_FORCE_ONE_SHARE", True)
    calls = []

    def place(**kw):
        calls.append(kw)
        return {"ok": True, "order_id": 42, "error": None, "mode": "paper"}

    monkeypatch.setattr(orders_mod, "place_order", place)
    r = asyncio.run(
        exec_svc.execute(
            ExecutionCommand(
                operation="place",
                idempotency_key="force-1",
                source="manual",
                symbol="AAPL",
                side="BUY",
                qty=1000,
                order_type="MKT",
                skip_risk=True,
                skip_concurrency=True,
            ),
            wait_ack=False,
        )
    )
    assert r.ok is True
    assert len(calls) == 1
    assert float(calls[0]["qty"]) == 1.0
    row = store.get_by_id(r.execution_id)
    assert row["payload"]["requested_qty"] == 1000.0
    assert row["payload"]["sent_qty"] == 1.0
    assert row["payload"]["forced_one_share"] is True
    assert row["payload"]["short_entry"] is False
    assert "orders_enabled" in row["payload"]
    assert "gateway_mode" in row["payload"]
