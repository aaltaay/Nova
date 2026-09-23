"""MASTER TEST QTY GATE — IBKR_FORCE_ONE_SHARE (intentional; not a bug).

Since 2026-09-22 (#444) the gate is a cap, not a fixed size: at or under
IBKR_FORCE_ONE_SHARE_QTY goes through as asked, above it is cut to the cap --
on the Live venue only (default one share). Paper and Sim are not capped.
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
import sim.mode as sim_mode
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
    _venue(monkeypatch, "live")
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


def _venue(monkeypatch, label: str) -> None:
    """Pin the desk venue in memory (no venue file, no Sim feed, no disarm)."""
    monkeypatch.setattr(sim_mode, "_override", label)
    monkeypatch.setattr(sim_mode, "_venue_loaded", True)


def _place(qty, *, source="manual", key="cap") -> ExecutionCommand:
    return ExecutionCommand(
        operation="place",
        idempotency_key=key,
        source=source,
        symbol="AAPL",
        side="BUY",
        qty=qty,
        order_type="MKT",
    )


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


# ── #444 option 1: Live is capped, Paper and Sim are not ──────────────────────


def test_the_live_default_is_one_share():
    """Operator decision on #444: one share on Live so a fat finger never reaches real money."""
    import constants

    assert constants.IBKR_FORCE_ONE_SHARE is True
    assert constants.IBKR_FORCE_ONE_SHARE_QTY == 1.0


@pytest.mark.parametrize("label", ["paper", "sim"])
def test_practice_venues_are_not_capped(monkeypatch, label):
    monkeypatch.setattr(qty_gate, "IBKR_FORCE_ONE_SHARE", True)
    monkeypatch.setattr(qty_gate, "IBKR_FORCE_ONE_SHARE_QTY", 1.0)
    _venue(monkeypatch, label)
    cmd = _place(500)
    assert qty_gate.apply_force_one_share(cmd) is cmd
    assert qty_gate.qty_cap() is None  # the ticket states no cap there


def test_live_is_capped_at_the_default(monkeypatch):
    monkeypatch.setattr(qty_gate, "IBKR_FORCE_ONE_SHARE", True)
    monkeypatch.setattr(qty_gate, "IBKR_FORCE_ONE_SHARE_QTY", 1.0)
    monkeypatch.delenv("IBKR_QTY_CAP", raising=False)
    _venue(monkeypatch, "live")
    assert qty_gate.apply_force_one_share(_place(10)).qty == 1.0
    assert qty_gate.qty_cap() == 1.0


def test_an_unreadable_venue_counts_as_live(monkeypatch):
    """Fail closed: if the venue cannot be read, the Live cap applies."""
    monkeypatch.setattr(qty_gate, "IBKR_FORCE_ONE_SHARE", True)
    monkeypatch.setattr(qty_gate, "IBKR_FORCE_ONE_SHARE_QTY", 1.0)

    def broken():
        raise RuntimeError("venue file unreadable")

    monkeypatch.setattr(sim_mode, "is_practice_venue", broken)
    assert qty_gate.apply_force_one_share(_place(10)).qty == 1.0
    assert qty_gate.qty_cap() == 1.0


def test_live_cap_refusal_is_the_ibkr_doors_last_word(monkeypatch):
    """No venue check: whatever reaches the IBKR send is real money."""
    monkeypatch.setattr(qty_gate, "IBKR_FORCE_ONE_SHARE", True)
    monkeypatch.setattr(qty_gate, "IBKR_FORCE_ONE_SHARE_QTY", 1.0)
    monkeypatch.delenv("IBKR_QTY_CAP", raising=False)
    _venue(monkeypatch, "paper")  # e.g. the clamp ran on Paper, then the venue became Live
    refusal = qty_gate.live_cap_refusal(_place(5), 5)
    assert refusal is not None and "at most 1 share per order" in refusal
    assert qty_gate.live_cap_refusal(_place(1), 1) is None
    assert qty_gate.live_cap_refusal(_place(5, source="flatten"), 5) is None
    cancel = ExecutionCommand(operation="cancel", idempotency_key="c", source="manual", order_id=9)
    assert qty_gate.live_cap_refusal(cancel, 5) is None
    monkeypatch.setattr(qty_gate, "IBKR_FORCE_ONE_SHARE", False)
    assert qty_gate.live_cap_refusal(_place(5), 5) is None


def test_ibkr_send_refuses_a_size_above_the_live_cap(monkeypatch):
    """A size that got past the clamp is refused at the IBKR send, never sent."""
    import execution.broker_send as broker_send
    from execution.models import ExecutionReceipt, StageTimings

    monkeypatch.setattr(qty_gate, "IBKR_FORCE_ONE_SHARE", True)
    monkeypatch.setattr(qty_gate, "IBKR_FORCE_ONE_SHARE_QTY", 1.0)
    monkeypatch.delenv("IBKR_QTY_CAP", raising=False)
    sent = []
    monkeypatch.setattr(orders_mod, "place_order", lambda **kw: sent.append(kw) or {"ok": True})
    monkeypatch.setattr(orders_mod, "place_bracket_order", lambda **kw: sent.append(kw) or {"ok": True})
    monkeypatch.setattr(risk_mod, "position_size_shares", lambda: 40)

    def reject(execution_id, cmd, timings, detail, reason):
        return ExecutionReceipt(
            ok=False, execution_id=execution_id, operation=cmd.operation, source=cmd.source,
            idempotency_key=cmd.idempotency_key, error=detail, reason_code=reason, timings=timings,
        )

    def send(cmd):
        return asyncio.run(broker_send.send_broker(
            cmd, "exec-cap", StageTimings(received_ns=0), wait_ack=False, reject=reject,
        ))

    placed = send(_place(5))
    assert placed.ok is False and placed.reason_code == "QTY_CAP_LIVE"
    # A bracket with no size is sized at the send from strategy risk (40 here).
    bracket = send(ExecutionCommand(
        operation="bracket", idempotency_key="b", source="approve", symbol="AAPL",
        side="BUY", entry_price=10.0, stop_price=9.5, target_price=11.0,
    ))
    assert bracket.ok is False and bracket.reason_code == "QTY_CAP_LIVE"
    assert sent == []


class _PaperBroker:
    """A practice broker that records the size it was handed."""

    venue = "paper"
    account_id = "NOVA-PAPER"

    def __init__(self):
        self.calls = []

        class _Reference:
            @staticmethod
            def admission(symbol):
                return True, "OK", None

        self.reference = _Reference()

    def place(self, **kw):
        self.calls.append(kw)
        return {"ok": True, "order_id": 7, "error": None, "mode": "paper",
                "nova_placed_at": None, "broker_status": "Submitted"}

    def positions(self):
        return []

    def working_orders(self):
        return []

    def account_summary(self):
        return {"connected": True, "mode": "paper", "practice": True, "pending": False,
                "account_id": "NOVA-PAPER", "BuyingPower": 100_000.0}


def test_execute_on_paper_sends_the_size_asked(monkeypatch):
    """Through the whole door: Paper hands the practice broker all 100 shares."""
    from practice import broker as practice_broker

    monkeypatch.setattr(qty_gate, "IBKR_FORCE_ONE_SHARE", True)
    monkeypatch.setattr(qty_gate, "IBKR_FORCE_ONE_SHARE_QTY", 1.0)
    monkeypatch.setattr(exec_svc, "IBKR_FORCE_ONE_SHARE", True)
    _venue(monkeypatch, "paper")
    broker = _PaperBroker()
    monkeypatch.setattr(practice_broker, "for_venue", lambda label: broker)
    safety_mod.set_armed(True, reason="test")
    try:
        r = asyncio.run(exec_svc.execute(
            ExecutionCommand(
                operation="place", idempotency_key="paper-100", source="manual",
                symbol="AAPL", side="BUY", qty=100, order_type="LMT", limit_price=10.0,
                skip_risk=True, skip_concurrency=True,
            ),
            wait_ack=False,
        ))
    finally:
        safety_mod.set_armed(False, reason="test")
    assert r.ok is True, r.error
    assert len(broker.calls) == 1 and float(broker.calls[0]["qty"]) == 100.0
    row = store.get_by_id(r.execution_id)
    assert row["payload"]["sent_qty"] == 100.0
    assert row["payload"]["forced_one_share"] is False
