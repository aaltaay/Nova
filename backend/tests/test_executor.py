"""
Unit tests for the paper-execution engine (Phase D). No live IB Gateway —
IBKR and risk calls are mocked, mirroring test_ibkr_safety.py's style. The
journal DB is isolated to a tmp_path SQLite file, mirroring test_journal.py.
"""
import asyncio
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import journal.db as db
import nova_os.events_db as events_db
import strategy.executor as executor
import strategy.risk as risk_mod
from constants import NOVA_OS_MODE_AUTO_PAPER, NOVA_OS_MODE_CONFIRM
from ibkr import orders as orders_mod
from nova_os import control_mode, staged_tickets


@pytest.fixture(autouse=True)
def isolated_journal_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "cache_dir", lambda: tmp_path)
    monkeypatch.setattr(events_db, "cache_dir", lambda: tmp_path)
    db.init_db()
    events_db.init_db()
    yield


@pytest.fixture(autouse=True)
def reset_executor_state():
    control_mode.reset_for_tests()
    staged_tickets.reset_for_tests()
    executor._kill_switch_tripped = False
    executor._open_positions.clear()
    yield
    control_mode.reset_for_tests()
    staged_tickets.reset_for_tests()
    executor._kill_switch_tripped = False
    executor._open_positions.clear()


_SIGNAL = {"entry_price": 5.00, "stop_price": 4.90, "target_price": 5.20}


def _approve_risk(monkeypatch, qty=100):
    monkeypatch.setattr(risk_mod, "can_trade", lambda: (True, "OK"))
    monkeypatch.setattr(risk_mod, "validate_trade_plan", lambda e, s, t: (True, []))
    monkeypatch.setattr(risk_mod, "position_size_shares", lambda: qty)


def _enable_auto_paper():
    """P4 rejects set_mode(auto_paper); tests poke the in-memory mode for the P5 path."""
    control_mode._mode = NOVA_OS_MODE_AUTO_PAPER
    executor._kill_switch_tripped = False


class TestArmDisarmKillSwitch:
    def test_disarmed_by_default(self):
        assert executor.is_armed() is False

    def test_arm_sets_armed_true(self):
        result = executor.arm()
        assert result["armed"] is True
        assert result["control_mode"] == NOVA_OS_MODE_CONFIRM
        assert executor.is_armed() is True

    def test_disarm_sets_armed_false(self):
        executor.arm()
        result = executor.disarm()
        assert result["armed"] is False
        assert result["control_mode"] == "signal"
        assert executor.is_armed() is False

    def test_kill_switch_cancels_only_when_parent_unfilled(self, monkeypatch):
        executor.arm()
        cancelled_ids = []
        monkeypatch.setattr(executor._ibkr_client, "is_connected", lambda: True)
        monkeypatch.setattr(orders_mod, "open_orders", lambda: [{"order_id": 1}])
        monkeypatch.setattr(orders_mod, "cancel_order", lambda oid: cancelled_ids.append(oid) or {"ok": True})
        executor._open_positions["AAPL"] = executor.OpenPosition(
            symbol="AAPL", setup="gap_and_go", qty=100,
            entry_price=5.0, stop_price=4.9, target_price=5.2,
            parent_order_id=1, target_order_id=2, stop_order_id=3, opened_ts=time.time(),
        )
        result = executor.kill_switch()
        assert result["armed"] is False
        assert result["kill_switch_tripped"] is True
        assert executor.is_armed() is False
        assert sorted(cancelled_ids) == [1, 2, 3]

    def test_kill_switch_preserves_stops_when_parent_filled(self, monkeypatch):
        executor.arm()
        cancelled_ids = []
        monkeypatch.setattr(executor._ibkr_client, "is_connected", lambda: True)
        monkeypatch.setattr(orders_mod, "open_orders", lambda: [{"order_id": 2}, {"order_id": 3}])
        monkeypatch.setattr(orders_mod, "cancel_order", lambda oid: cancelled_ids.append(oid) or {"ok": True})
        executor._open_positions["AAPL"] = executor.OpenPosition(
            symbol="AAPL", setup="gap_and_go", qty=100,
            entry_price=5.0, stop_price=4.9, target_price=5.2,
            parent_order_id=1, target_order_id=2, stop_order_id=3, opened_ts=time.time(),
        )
        executor.kill_switch()
        assert cancelled_ids == []

    def test_reset_kill_switch_clears_flag_without_arming(self):
        executor.arm()
        executor.kill_switch()
        result = executor.reset_kill_switch()
        assert result["kill_switch_tripped"] is False
        assert result["armed"] is False
        assert executor.is_armed() is False


class TestOnSignal:
    def test_does_nothing_when_disarmed(self, monkeypatch):
        called = []
        monkeypatch.setattr(orders_mod, "place_bracket_order", lambda *a, **k: called.append(1))
        result = asyncio.run(executor.on_signal("AAPL", "gap_and_go", _SIGNAL))
        assert result is None
        assert called == []

    def test_confirm_stages_instead_of_placing(self, monkeypatch):
        executor.arm()
        called = []
        monkeypatch.setattr(orders_mod, "place_bracket_order", lambda *a, **k: called.append(1))
        result = asyncio.run(executor.on_signal("AAPL", "gap_and_go", {**_SIGNAL, "shares": 50}))
        assert result is not None
        assert result["status"] == "staged"
        assert called == []
        assert len(staged_tickets.list_staged()) == 1

    def test_skips_when_position_already_open_for_symbol(self, monkeypatch):
        _enable_auto_paper()
        _approve_risk(monkeypatch)
        executor._open_positions["AAPL"] = executor.OpenPosition(
            symbol="AAPL", setup="gap_and_go", qty=100,
            entry_price=5.0, stop_price=4.9, target_price=5.2,
            parent_order_id=1, target_order_id=2, stop_order_id=3, opened_ts=time.time(),
        )
        called = []
        monkeypatch.setattr(orders_mod, "place_bracket_order", lambda *a, **k: called.append(1))
        result = asyncio.run(executor.on_signal("AAPL", "gap_and_go", _SIGNAL))
        assert result is None
        assert called == []

    def test_skips_when_risk_halted(self, monkeypatch):
        _enable_auto_paper()
        monkeypatch.setattr(risk_mod, "can_trade", lambda: (False, "Daily max loss reached."))
        called = []
        monkeypatch.setattr(orders_mod, "place_bracket_order", lambda *a, **k: called.append(1))
        result = asyncio.run(executor.on_signal("AAPL", "gap_and_go", _SIGNAL))
        assert result is None
        assert called == []

    def test_skips_when_plan_fails_validation(self, monkeypatch):
        _enable_auto_paper()
        monkeypatch.setattr(risk_mod, "can_trade", lambda: (True, "OK"))
        monkeypatch.setattr(risk_mod, "validate_trade_plan", lambda e, s, t: (False, ["Stop too wide."]))
        called = []
        monkeypatch.setattr(orders_mod, "place_bracket_order", lambda *a, **k: called.append(1))
        result = asyncio.run(executor.on_signal("AAPL", "gap_and_go", _SIGNAL))
        assert result is None
        assert called == []

    def test_skips_when_bracket_order_rejected(self, monkeypatch):
        _enable_auto_paper()
        _approve_risk(monkeypatch)
        monkeypatch.setattr(
            orders_mod, "place_bracket_order",
            lambda *a, **k: {"ok": False, "parent_order_id": None, "target_order_id": None,
                              "stop_order_id": None, "error": "Not connected", "mode": "disconnected"},
        )
        result = asyncio.run(executor.on_signal("AAPL", "gap_and_go", _SIGNAL))
        assert result is None
        assert "AAPL" not in executor._open_positions

    def test_places_bracket_when_auto_paper_and_checks_pass(self, monkeypatch):
        _enable_auto_paper()
        _approve_risk(monkeypatch, qty=100)
        placed_args = []
        monkeypatch.setattr(
            orders_mod, "place_bracket_order",
            lambda *a, **k: (placed_args.append(a) or
                              {"ok": True, "parent_order_id": 10, "target_order_id": 11,
                               "stop_order_id": 12, "error": None, "mode": "paper"}),
        )
        result = asyncio.run(executor.on_signal("AAPL", "gap_and_go", _SIGNAL))
        assert result is not None
        assert result["symbol"] == "AAPL"
        assert result["qty"] == 100
        assert "AAPL" in executor._open_positions
        pos = executor._open_positions["AAPL"]
        assert pos.parent_order_id == 10
        assert pos.target_order_id == 11
        assert pos.stop_order_id == 12
        assert placed_args[0][0] == "AAPL"
        assert placed_args[0][2] == 100


class _FakeExecution:
    def __init__(self, order_id, avg_price):
        self.orderId = order_id
        self.avgPrice = avg_price


class _FakeFill:
    def __init__(self, symbol, order_id, avg_price):
        self.contract = SimpleNamespace(symbol=symbol)
        self.execution = _FakeExecution(order_id, avg_price)


class _FakeIB:
    def __init__(self, fills):
        self._fills = fills

    def fills(self):
        return self._fills


class TestCheckFillsOnce:
    def _seed_open_position(self, symbol="AAPL", target_id=11, stop_id=12):
        executor._open_positions[symbol] = executor.OpenPosition(
            symbol=symbol, setup="gap_and_go", qty=100,
            entry_price=5.0, stop_price=4.9, target_price=5.2,
            parent_order_id=10, target_order_id=target_id, stop_order_id=stop_id,
            opened_ts=time.time(),
        )

    def test_still_open_position_is_left_alone(self, monkeypatch):
        self._seed_open_position()
        monkeypatch.setattr(executor._ibkr_client, "get_ib", lambda: _FakeIB([]))
        monkeypatch.setattr(orders_mod, "open_orders", lambda: [{"order_id": 10}])
        asyncio.run(executor._check_fills_once())
        assert "AAPL" in executor._open_positions

    def test_target_fill_records_winning_trade_and_updates_risk(self, monkeypatch):
        self._seed_open_position()
        fake_ib = _FakeIB([_FakeFill("AAPL", 11, 5.20)])
        monkeypatch.setattr(executor._ibkr_client, "get_ib", lambda: fake_ib)
        monkeypatch.setattr(orders_mod, "open_orders", lambda: [])
        pnl_results = []
        monkeypatch.setattr(risk_mod, "record_trade_result", lambda pnl: pnl_results.append(pnl))

        asyncio.run(executor._check_fills_once())

        assert "AAPL" not in executor._open_positions
        assert pnl_results == [pytest.approx(20.0)]  # (5.20 - 5.00) * 100

        from journal.store import get_closed_trades
        trades = get_closed_trades()
        assert len(trades) == 1
        assert trades[0]["symbol"] == "AAPL"
        assert trades[0]["pnl"] == pytest.approx(20.0)
        assert trades[0]["adherent"] == 1

    def test_stop_fill_records_losing_trade(self, monkeypatch):
        self._seed_open_position()
        fake_ib = _FakeIB([_FakeFill("AAPL", 12, 4.90)])
        monkeypatch.setattr(executor._ibkr_client, "get_ib", lambda: fake_ib)
        monkeypatch.setattr(orders_mod, "open_orders", lambda: [])
        pnl_results = []
        monkeypatch.setattr(risk_mod, "record_trade_result", lambda pnl: pnl_results.append(pnl))

        asyncio.run(executor._check_fills_once())

        assert pnl_results == [pytest.approx(-10.0)]  # (4.90 - 5.00) * 100
        from journal.store import get_closed_trades
        trades = get_closed_trades()
        assert trades[0]["pnl"] == pytest.approx(-10.0)

    def test_no_fill_found_drops_position_without_journal_entry(self, monkeypatch):
        """All legs cancelled before the entry ever filled -- nothing to journal."""
        self._seed_open_position()
        monkeypatch.setattr(executor._ibkr_client, "get_ib", lambda: _FakeIB([]))
        monkeypatch.setattr(orders_mod, "open_orders", lambda: [])

        asyncio.run(executor._check_fills_once())

        assert "AAPL" not in executor._open_positions
        from journal.store import get_trades
        assert get_trades(include_mock=True) == []

    def test_no_open_positions_is_a_noop(self, monkeypatch):
        called = []
        monkeypatch.setattr(orders_mod, "open_orders", lambda: called.append(1))
        asyncio.run(executor._check_fills_once())
        assert called == []

    def test_disconnected_ib_is_a_noop(self, monkeypatch):
        self._seed_open_position()
        monkeypatch.setattr(executor._ibkr_client, "get_ib", lambda: None)
        asyncio.run(executor._check_fills_once())
        assert "AAPL" in executor._open_positions
