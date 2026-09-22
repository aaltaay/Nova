"""MASTER TEST QTY GATE — IBKR_FORCE_ONE_SHARE (intentional; not a bug).

Since 2026-09-22 (#444) the gate is a cap, not a fixed size: at or under
IBKR_FORCE_ONE_SHARE_QTY goes through as asked, above it is cut to the cap.
"""
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
    monkeypatch.setattr(qty_gate, "IBKR_FORCE_ONE_SHARE_QTY", 10.0)
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
    assert out.qty == 10.0
    assert cmd.qty == 500


def test_apply_force_keeps_sizes_at_or_under_the_cap(monkeypatch):
    """#444: the gate is a cap. 5 shares stay 5; exactly the cap stays the cap."""
    monkeypatch.setattr(qty_gate, "IBKR_FORCE_ONE_SHARE", True)
    monkeypatch.setattr(qty_gate, "IBKR_FORCE_ONE_SHARE_QTY", 10.0)
    for qty in (1, 5, 10):
        cmd = ExecutionCommand(
            operation="place",
            idempotency_key=f"cap-{qty}",
            source="manual",
            symbol="AAPL",
            side="BUY",
            qty=qty,
            order_type="MKT",
        )
        assert qty_gate.apply_force_one_share(cmd) is cmd
    assert qty_gate.qty_cap() == 10.0
    monkeypatch.setattr(qty_gate, "IBKR_FORCE_ONE_SHARE", False)
    assert qty_gate.qty_cap() is None


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
    monkeypatch.setattr(qty_gate, "IBKR_FORCE_ONE_SHARE_QTY", 10.0)
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
    assert float(calls[0]["qty"]) == 10.0
    row = store.get_by_id(r.execution_id)
    assert row["payload"]["requested_qty"] == 1000.0
    assert row["payload"]["sent_qty"] == 10.0
    assert row["payload"]["forced_one_share"] is True
    assert row["payload"]["short_entry"] is False
    assert "orders_enabled" in row["payload"]
    assert "gateway_mode" in row["payload"]


@pytest.mark.parametrize("source", ["flatten", "kill", "cancel_working"])
def test_protective_sources_are_never_clamped(monkeypatch, source):
    """QA R6 (2026-09-22): a clamped flatten left N-1 shares after an Emergency KILL."""
    monkeypatch.setattr(qty_gate, "IBKR_FORCE_ONE_SHARE", True)
    monkeypatch.setattr(qty_gate, "IBKR_FORCE_ONE_SHARE_QTY", 1.0)  # a 1-share cap: 2 must still pass
    cmd = ExecutionCommand(
        operation="place",
        idempotency_key=f"protect-{source}",
        source=source,
        symbol="GRML",
        side="SELL",
        qty=2,
        order_type="MKT",
    )
    assert qty_gate.apply_force_one_share(cmd).qty == 2


def test_execute_sends_the_whole_flatten_and_stamps_no_clamp(monkeypatch):
    _arm_paper(monkeypatch)
    monkeypatch.setattr(qty_gate, "IBKR_FORCE_ONE_SHARE", True)
    monkeypatch.setattr(qty_gate, "IBKR_FORCE_ONE_SHARE_QTY", 1.0)
    monkeypatch.setattr(exec_svc, "IBKR_FORCE_ONE_SHARE", True)
    monkeypatch.setattr(account_mod, "get_positions", lambda: [{"symbol": "AAPL", "qty": 3}])
    calls = []

    def place(**kw):
        calls.append(kw)
        return {"ok": True, "order_id": 43, "error": None, "mode": "paper"}

    monkeypatch.setattr(orders_mod, "place_order", place)
    r = asyncio.run(
        exec_svc.execute(
            ExecutionCommand(
                operation="place",
                idempotency_key="flatten-whole",
                source="flatten",
                symbol="AAPL",
                side="SELL",
                qty=3,
                order_type="MKT",
                skip_risk=True,
                skip_concurrency=True,
            ),
            wait_ack=False,
        )
    )
    assert r.ok is True, r.error
    assert len(calls) == 1
    assert float(calls[0]["qty"]) == 3.0
    row = store.get_by_id(r.execution_id)
    assert row["payload"]["sent_qty"] == 3.0
    assert row["payload"]["forced_one_share"] is False


def test_env_override_sets_the_cap(monkeypatch):
    """#444 follow-up: one .env line changes the cap everywhere (clamp + status)."""
    monkeypatch.setattr(qty_gate, "IBKR_FORCE_ONE_SHARE", True)
    monkeypatch.setattr(qty_gate, "IBKR_FORCE_ONE_SHARE_QTY", 10.0)
    monkeypatch.setenv("IBKR_QTY_CAP", "25")
    cmd = ExecutionCommand(
        operation="place",
        idempotency_key="env-cap",
        source="manual",
        symbol="AAPL",
        side="BUY",
        qty=100,
        order_type="MKT",
    )
    assert qty_gate.apply_force_one_share(cmd).qty == 25.0
    assert qty_gate.qty_cap() == 25.0
    monkeypatch.setenv("IBKR_QTY_CAP", "banana")
    assert qty_gate.qty_cap() == 10.0  # a bad value falls back to the default, loudly
    monkeypatch.setenv("IBKR_QTY_CAP", "0")
    assert qty_gate.qty_cap() == 10.0
