"""Nova OS P5 — auto_paper gates, on_signal placement, restart recovery, auto_live blocked."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import nova_os.events_db as events_db
import strategy.executor as executor
import strategy.risk as risk_mod
from constants import (
    NOVA_OS_ACTION_EXECUTED_PAPER,
    NOVA_OS_DEFAULT_MODE,
    NOVA_OS_MODE_AUTO_LIVE,
    NOVA_OS_MODE_AUTO_PAPER,
    NOVA_OS_MODE_CONFIRM,
    NOVA_OS_MODE_SIGNAL,
)
from ibkr import client as ibkr_client
from ibkr import safety as ibkr_safety
from nova_os import control_mode, staged_tickets
from nova_os.events import KIND_ACTION, get_events, record_receipt
from nova_os.recovery import run_startup_recovery


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(events_db, "cache_dir", lambda: tmp_path)
    monkeypatch.setattr("execution.store.cache_dir", lambda: tmp_path)
    events_db.init_db()
    control_mode.reset_for_tests()
    executor._kill_switch_tripped = False
    executor._open_positions.clear()
    staged_tickets.reset_for_tests()
    risk_mod.get_state().consecutive_losses = 0
    risk_mod.get_state().losses_today = 0
    yield
    control_mode.reset_for_tests()
    executor._kill_switch_tripped = False
    executor._open_positions.clear()
    staged_tickets.reset_for_tests()
    risk_mod.get_state().consecutive_losses = 0
    risk_mod.get_state().losses_today = 0


def _gate_auto_paper_ok(monkeypatch):
    import ibkr.account as account_mod

    monkeypatch.setattr(ibkr_client, "is_connected", lambda: True)
    monkeypatch.setattr(ibkr_client, "account_mode", lambda: "paper")
    monkeypatch.setattr(ibkr_client, "broker_account_kind", lambda: "paper")
    monkeypatch.setattr(ibkr_client, "is_enabled", lambda: True)
    monkeypatch.setattr(ibkr_client, "get_ib", lambda: None)
    monkeypatch.setattr(ibkr_safety, "orders_enabled", lambda: True)
    monkeypatch.setattr(
        ibkr_safety,
        "assert_orders_allowed",
        lambda **kw: (True, ""),
    )
    monkeypatch.setattr(risk_mod, "can_trade", lambda: (True, "OK"))
    monkeypatch.setattr("nova_os.control_mode.is_nyse_holiday", lambda when=None: False)
    monkeypatch.setattr(
        account_mod,
        "get_account_summary",
        lambda: {"connected": True, "BuyingPower": 1_000_000.0, "pending": False},
    )
    monkeypatch.setattr(account_mod, "get_positions", lambda: [])


_SIGNAL = {"entry_price": 5.00, "stop_price": 4.90, "target_price": 5.20}


class TestSetModeAutoPaperGates:
    def test_auto_live_rejected(self):
        with pytest.raises(ValueError, match="auto_live is not enabled"):
            control_mode.set_mode(NOVA_OS_MODE_AUTO_LIVE)
        assert control_mode.get_mode() == NOVA_OS_MODE_SIGNAL

    def test_auto_paper_requires_connected(self, monkeypatch):
        monkeypatch.setattr(ibkr_client, "is_connected", lambda: False)
        with pytest.raises(ValueError, match="IBKR connected"):
            control_mode.set_mode(NOVA_OS_MODE_AUTO_PAPER)

    def test_auto_paper_rejects_live_account(self, monkeypatch):
        monkeypatch.setattr(ibkr_client, "is_connected", lambda: True)
        monkeypatch.setattr(ibkr_client, "account_mode", lambda: "live")
        with pytest.raises(ValueError, match="paper Gateway"):
            control_mode.set_mode(NOVA_OS_MODE_AUTO_PAPER)

    def test_auto_paper_requires_orders_enabled(self, monkeypatch):
        monkeypatch.setattr(ibkr_client, "is_connected", lambda: True)
        monkeypatch.setattr(ibkr_client, "account_mode", lambda: "paper")
        monkeypatch.setattr(ibkr_client, "broker_account_kind", lambda: "paper")
        monkeypatch.setattr(ibkr_safety, "orders_enabled", lambda: False)
        with pytest.raises(ValueError, match="IBKR_ORDERS_ENABLED"):
            control_mode.set_mode(NOVA_OS_MODE_AUTO_PAPER)

    def test_auto_paper_rejects_live_broker_accounts(self, monkeypatch):
        monkeypatch.setattr(ibkr_client, "is_connected", lambda: True)
        monkeypatch.setattr(ibkr_client, "account_mode", lambda: "paper")
        monkeypatch.setattr(ibkr_client, "broker_account_kind", lambda: "live")
        with pytest.raises(ValueError, match="paper broker accounts"):
            control_mode.set_mode(NOVA_OS_MODE_AUTO_PAPER)

    def test_auto_paper_requires_risk(self, monkeypatch):
        _gate_auto_paper_ok(monkeypatch)
        monkeypatch.setattr(risk_mod, "can_trade", lambda: (False, "Daily max loss reached."))
        with pytest.raises(ValueError, match="Daily max loss"):
            control_mode.set_mode(NOVA_OS_MODE_AUTO_PAPER)

    def test_auto_paper_blocked_on_holiday(self, monkeypatch):
        _gate_auto_paper_ok(monkeypatch)
        monkeypatch.setattr("nova_os.control_mode.is_nyse_holiday", lambda when=None: True)
        with pytest.raises(ValueError, match="holiday"):
            control_mode.set_mode(NOVA_OS_MODE_AUTO_PAPER)

    def test_auto_paper_ok_when_gates_pass(self, monkeypatch):
        _gate_auto_paper_ok(monkeypatch)
        assert control_mode.set_mode(NOVA_OS_MODE_AUTO_PAPER) == NOVA_OS_MODE_AUTO_PAPER
        assert control_mode.get_mode() == NOVA_OS_MODE_AUTO_PAPER


class TestOnSignalAutoPaper:
    def test_places_when_auto_paper(self, monkeypatch):
        _gate_auto_paper_ok(monkeypatch)
        control_mode.set_mode(NOVA_OS_MODE_AUTO_PAPER)
        monkeypatch.setattr(risk_mod, "can_trade", lambda: (True, "OK"))
        monkeypatch.setattr(risk_mod, "validate_trade_plan", lambda e, s, t: (True, []))
        monkeypatch.setattr(risk_mod, "position_size_shares", lambda: 100)
        monkeypatch.setattr(
            executor._orders,
            "place_bracket_order",
            lambda *a, **k: {
                "ok": True,
                "parent_order_id": 10,
                "target_order_id": 11,
                "stop_order_id": 12,
                "error": None,
                "mode": "paper",
            },
        )
        result = asyncio.run(executor.on_signal("AAPL", "gap_and_go", _SIGNAL))
        assert result is not None
        assert result["symbol"] == "AAPL"
        assert "AAPL" in executor._open_positions
        events = get_events(kind=KIND_ACTION, limit=5)
        assert any(e.get("action") == NOVA_OS_ACTION_EXECUTED_PAPER for e in events)

    def test_confirm_still_stages(self, monkeypatch):
        control_mode.set_mode(NOVA_OS_MODE_CONFIRM)
        called = []
        monkeypatch.setattr(
            executor._orders, "place_bracket_order", lambda *a, **k: called.append(1)
        )
        result = asyncio.run(executor.on_signal("AAPL", "gap_and_go", {**_SIGNAL, "shares": 50}))
        assert result is not None
        assert result["status"] == "staged"
        assert called == []

    def test_signal_noop(self, monkeypatch):
        assert control_mode.get_mode() == NOVA_OS_MODE_SIGNAL
        called = []
        monkeypatch.setattr(
            executor._orders, "place_bracket_order", lambda *a, **k: called.append(1)
        )
        assert asyncio.run(executor.on_signal("AAPL", "gap_and_go", _SIGNAL)) is None
        assert called == []


class TestRestartRecovery:
    def test_forces_signal_and_does_not_restore_auto_paper(self, monkeypatch):
        _gate_auto_paper_ok(monkeypatch)
        control_mode.set_mode(NOVA_OS_MODE_AUTO_PAPER)
        assert control_mode.get_mode() == NOVA_OS_MODE_AUTO_PAPER
        # Simulate process restart: mode module would reset, then recovery runs.
        control_mode.reset_for_tests()
        monkeypatch.setattr(ibkr_client, "is_connected", lambda: False)
        summary = run_startup_recovery()
        assert control_mode.get_mode() == NOVA_OS_DEFAULT_MODE
        assert control_mode.get_mode() == NOVA_OS_MODE_SIGNAL
        assert summary["mode"] == NOVA_OS_MODE_SIGNAL

    def test_reconstructs_from_executed_paper_when_orders_open(self, monkeypatch):
        record_receipt(
            kind=KIND_ACTION,
            symbol="TSLA",
            action=NOVA_OS_ACTION_EXECUTED_PAPER,
            mode=NOVA_OS_MODE_AUTO_PAPER,
            would_execute=True,
            executed=True,
            payload={
                "event": "executed_paper",
                "setup": "gap_and_go",
                "qty": 50,
                "entry_price": 10.0,
                "stop_price": 9.8,
                "target_price": 10.5,
                "parent_order_id": 100,
                "target_order_id": 101,
                "stop_order_id": 102,
                "opened_ts": 1_700_000_000.0,
            },
        )
        monkeypatch.setattr(ibkr_client, "is_connected", lambda: True)
        monkeypatch.setattr(
            executor._orders,
            "open_orders",
            lambda: [{"order_id": 100}, {"order_id": 101}, {"order_id": 102}],
        )
        # Patch recovery's orders import path
        monkeypatch.setattr(
            "nova_os.recovery._orders.open_orders",
            lambda: [{"order_id": 100}, {"order_id": 101}, {"order_id": 102}],
        )
        summary = run_startup_recovery()
        assert "TSLA" in summary["restored_symbols"]
        assert "TSLA" in executor._open_positions
        assert executor._open_positions["TSLA"].parent_order_id == 100
        assert control_mode.get_mode() == NOVA_OS_MODE_SIGNAL

    def test_ambiguous_missing_ids_forces_signal(self, monkeypatch):
        control_mode.set_mode(NOVA_OS_MODE_CONFIRM)
        record_receipt(
            kind=KIND_ACTION,
            symbol="BAD",
            action=NOVA_OS_ACTION_EXECUTED_PAPER,
            mode=NOVA_OS_MODE_CONFIRM,
            would_execute=True,
            executed=True,
            payload={"event": "executed_paper", "qty": 1},  # missing order ids
        )
        monkeypatch.setattr(ibkr_client, "is_connected", lambda: False)
        summary = run_startup_recovery()
        assert summary["ambiguous"]

    def test_does_not_restore_ghost_position_when_ibkr_unverifiable(self, monkeypatch):
        """A fully-formed executed_paper payload with IBKR unreachable must
        NOT be restored into _open_positions — cancel/flatten could act on a
        position nobody has proven exists."""
        record_receipt(
            kind=KIND_ACTION,
            symbol="GHOST",
            action=NOVA_OS_ACTION_EXECUTED_PAPER,
            mode=NOVA_OS_MODE_AUTO_PAPER,
            would_execute=True,
            executed=True,
            payload={
                "event": "executed_paper",
                "setup": "gap_and_go",
                "qty": 50,
                "entry_price": 10.0,
                "stop_price": 9.8,
                "target_price": 10.5,
                "parent_order_id": 200,
                "target_order_id": 201,
                "stop_order_id": 202,
                "opened_ts": 1_700_000_000.0,
            },
        )
        monkeypatch.setattr(ibkr_client, "is_connected", lambda: False)
        summary = run_startup_recovery()
        assert "GHOST" not in summary["restored_symbols"]
        assert "GHOST" not in executor._open_positions
        assert summary["ambiguous"]
        assert control_mode.get_mode() == NOVA_OS_MODE_SIGNAL

    def test_orphan_flagged_even_when_another_symbol_restores_cleanly(self, monkeypatch):
        """A clean restore for one symbol must never mask an orphan IBKR
        order in another the journal can't explain."""
        record_receipt(
            kind=KIND_ACTION,
            symbol="TSLA",
            action=NOVA_OS_ACTION_EXECUTED_PAPER,
            mode=NOVA_OS_MODE_AUTO_PAPER,
            would_execute=True,
            executed=True,
            payload={
                "event": "executed_paper",
                "setup": "gap_and_go",
                "qty": 50,
                "entry_price": 10.0,
                "stop_price": 9.8,
                "target_price": 10.5,
                "parent_order_id": 100,
                "target_order_id": 101,
                "stop_order_id": 102,
                "opened_ts": 1_700_000_000.0,
            },
        )
        monkeypatch.setattr(ibkr_client, "is_connected", lambda: True)
        # IBKR reports an extra open order (999) the journal has no record of.
        monkeypatch.setattr(
            "nova_os.recovery._orders.open_orders",
            lambda: [{"order_id": 100}, {"order_id": 101}, {"order_id": 102}, {"order_id": 999}],
        )
        summary = run_startup_recovery()
        assert "TSLA" in summary["restored_symbols"]
        assert summary["ambiguous"]
        assert control_mode.get_mode() == NOVA_OS_MODE_SIGNAL
        assert control_mode.get_mode() == NOVA_OS_MODE_SIGNAL
        assert "BAD" not in executor._open_positions
