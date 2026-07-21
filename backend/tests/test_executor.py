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

import execution.service as exec_svc
import execution.store as exec_store
import execution.telemetry as exec_telemetry
import ibkr.account as account_mod
import ibkr.client as client_mod
import ibkr.safety as safety_mod
import journal.db as db
import nova_os.events_db as events_db
import strategy.executor as executor
import strategy.executor_flatten as executor_flatten
import strategy.risk as risk_mod
from constants import NOVA_OS_MODE_AUTO_PAPER, NOVA_OS_MODE_CONFIRM
from ibkr import orders as orders_mod
from nova_os import control_mode, staged_tickets


@pytest.fixture(autouse=True)
def isolated_journal_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "cache_dir", lambda: tmp_path)
    monkeypatch.setattr(events_db, "cache_dir", lambda: tmp_path)
    monkeypatch.setattr("execution.store.cache_dir", lambda: tmp_path)
    import execution.broker_send as broker_send

    monkeypatch.setattr(broker_send, "EXECUTION_ACK_WAIT_SEC", 0.05)
    db.init_db()
    events_db.init_db()
    exec_store.init_db()
    exec_telemetry.reset_for_tests()
    yield
    exec_telemetry.reset_for_tests()


@pytest.fixture(autouse=True)
def reset_executor_state():
    control_mode.reset_for_tests()
    staged_tickets.reset_for_tests()
    risk_mod.reset_day()
    executor._kill_switch_tripped = False
    executor._open_positions.clear()
    yield
    control_mode.reset_for_tests()
    staged_tickets.reset_for_tests()
    risk_mod.reset_day()
    executor._kill_switch_tripped = False
    executor._open_positions.clear()


_SIGNAL = {"entry_price": 5.00, "stop_price": 4.90, "target_price": 5.20}


def _approve_risk(monkeypatch, qty=100):
    monkeypatch.setattr(risk_mod, "can_trade", lambda: (True, "OK"))
    monkeypatch.setattr(risk_mod, "validate_trade_plan", lambda e, s, t: (True, []))
    monkeypatch.setattr(risk_mod, "position_size_shares", lambda: qty)


def _arm_ibkr_execution(monkeypatch):
    """Open IBKR safety + account gates so execution.service can reach risk/broker."""
    monkeypatch.setattr(client_mod, "is_enabled", lambda: True)
    monkeypatch.setattr(client_mod, "is_connected", lambda: True)
    monkeypatch.setattr(client_mod, "account_mode", lambda: "paper")
    monkeypatch.setattr(client_mod, "broker_account_kind", lambda: "paper")
    monkeypatch.setattr(client_mod, "get_ib", lambda: None)
    monkeypatch.setattr(executor._ibkr_client, "is_enabled", lambda: True)
    monkeypatch.setattr(executor._ibkr_client, "is_connected", lambda: True)
    monkeypatch.setattr(executor._ibkr_client, "account_mode", lambda: "paper")
    monkeypatch.setattr(executor._ibkr_client, "broker_account_kind", lambda: "paper")
    monkeypatch.setattr(executor._ibkr_client, "get_ib", lambda: None)
    monkeypatch.setattr(safety_mod, "orders_enabled", lambda: True)
    # ibkr.safety.assert_orders_allowed reads the *real* IBKR_GATEWAY_MODE env
    # var independently of the account_mode/broker_account_kind mocks above —
    # pin it to paper so these tests don't depend on the developer's real .env.
    monkeypatch.setenv("IBKR_GATEWAY_MODE", "paper")
    monkeypatch.setattr(
        account_mod,
        "get_account_summary",
        lambda: {"connected": True, "BuyingPower": 1_000_000.0, "pending": False},
    )
    monkeypatch.setattr(account_mod, "get_positions", lambda: [])


def _enable_auto_paper(monkeypatch):
    """Bypass set_mode gates when a test only needs the on_signal auto path.

    place_from_ticket() re-checks the real auto_paper runtime gate (IBKR
    connected/paper/orders-enabled/risk/holiday) at every placement, not just
    at the moment set_mode() was called — so tests that only care about the
    non-IBKR checks (risk, plan validation, bracket rejection, concurrency)
    stub that gate open here rather than re-mocking IBKR client state in
    every test.
    """
    control_mode._mode = NOVA_OS_MODE_AUTO_PAPER
    executor._kill_switch_tripped = False
    monkeypatch.setattr(control_mode, "auto_paper_gate_status", lambda: (True, "OK"))
    _arm_ibkr_execution(monkeypatch)


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
        _arm_ibkr_execution(monkeypatch)
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
        _arm_ibkr_execution(monkeypatch)
        monkeypatch.setattr(orders_mod, "open_orders", lambda: [{"order_id": 2}, {"order_id": 3}])
        monkeypatch.setattr(orders_mod, "cancel_order", lambda oid: cancelled_ids.append(oid) or {"ok": True})
        executor._open_positions["AAPL"] = executor.OpenPosition(
            symbol="AAPL", setup="gap_and_go", qty=100,
            entry_price=5.0, stop_price=4.9, target_price=5.2,
            parent_order_id=1, target_order_id=2, stop_order_id=3, opened_ts=time.time(),
        )
        executor.kill_switch()
        assert cancelled_ids == []

    def test_kill_switch_preserves_stops_when_open_orders_read_fails(self, monkeypatch):
        """A transient open_orders() failure must not be treated as 'parent
        unfilled' — that would cancel a filled position's live protective
        stop/target based on a guess."""
        executor.arm()
        cancelled_ids = []
        _arm_ibkr_execution(monkeypatch)

        def boom():
            raise orders_mod.IbkrAccountError("open_orders failed: boom")

        monkeypatch.setattr(orders_mod, "open_orders", boom)
        monkeypatch.setattr(orders_mod, "cancel_order", lambda oid: cancelled_ids.append(oid) or {"ok": True})
        executor._open_positions["AAPL"] = executor.OpenPosition(
            symbol="AAPL", setup="gap_and_go", qty=100,
            entry_price=5.0, stop_price=4.9, target_price=5.2,
            parent_order_id=1, target_order_id=2, stop_order_id=3, opened_ts=time.time(),
        )
        result = executor.kill_switch()
        assert cancelled_ids == []
        assert result["kill_switch_tripped"] is True

    def test_reset_kill_switch_clears_flag_without_arming(self):
        executor.arm()
        executor.kill_switch()
        result = executor.reset_kill_switch()
        assert result["kill_switch_tripped"] is False
        assert result["armed"] is False
        assert executor.is_armed() is False

    def test_arm_raises_while_kill_tripped(self):
        """Kill is a deliberate stop — raising mode again must require an
        explicit reset_kill_switch(), not be silently cleared by arm()."""
        executor.arm()
        executor.kill_switch()
        assert executor.is_kill_switch_tripped() is True
        with pytest.raises(ValueError, match="kill switch"):
            executor.arm()
        assert executor.is_kill_switch_tripped() is True
        executor.reset_kill_switch()
        result = executor.arm()
        assert result["armed"] is True


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
        _enable_auto_paper(monkeypatch)
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
        _enable_auto_paper(monkeypatch)
        _approve_risk(monkeypatch)
        monkeypatch.setattr(risk_mod, "can_trade", lambda: (False, "Daily max loss reached."))
        called = []
        monkeypatch.setattr(orders_mod, "place_bracket_order", lambda *a, **k: called.append(1))
        result = asyncio.run(executor.on_signal("AAPL", "gap_and_go", _SIGNAL))
        assert result is None
        assert called == []

    def test_skips_when_plan_fails_validation(self, monkeypatch):
        _enable_auto_paper(monkeypatch)
        monkeypatch.setattr(risk_mod, "can_trade", lambda: (True, "OK"))
        monkeypatch.setattr(risk_mod, "position_size_shares", lambda: 100)
        monkeypatch.setattr(risk_mod, "validate_trade_plan", lambda e, s, t: (False, ["Stop too wide."]))
        called = []
        monkeypatch.setattr(orders_mod, "place_bracket_order", lambda *a, **k: called.append(1))
        result = asyncio.run(executor.on_signal("AAPL", "gap_and_go", _SIGNAL))
        assert result is None
        assert called == []

    def test_skips_when_bracket_order_rejected(self, monkeypatch):
        _enable_auto_paper(monkeypatch)
        _approve_risk(monkeypatch)
        monkeypatch.setattr(
            orders_mod, "place_bracket_order",
            lambda *a, **k: {"ok": False, "parent_order_id": None, "target_order_id": None,
                              "stop_order_id": None, "error": "Not connected", "mode": "disconnected"},
        )
        result = asyncio.run(executor.on_signal("AAPL", "gap_and_go", _SIGNAL))
        assert result is None
        assert "AAPL" not in executor._open_positions

    def test_place_from_ticket_blocked_when_kill_tripped(self, monkeypatch):
        _enable_auto_paper(monkeypatch)
        _approve_risk(monkeypatch)
        executor._kill_switch_tripped = True
        called = []
        monkeypatch.setattr(orders_mod, "place_bracket_order", lambda *a, **k: called.append(1))
        result = executor.place_from_ticket("AAPL", "gap_and_go", 5.0, 4.9, 5.2)
        assert result is None
        assert called == []

    def test_place_from_ticket_blocked_at_max_concurrent(self, monkeypatch):
        from constants import NOVA_OS_MAX_CONCURRENT_POSITIONS

        _enable_auto_paper(monkeypatch)
        _approve_risk(monkeypatch)
        for i in range(NOVA_OS_MAX_CONCURRENT_POSITIONS):
            executor._open_positions[f"SYM{i}"] = executor.OpenPosition(
                symbol=f"SYM{i}", setup="gap_and_go", qty=100,
                entry_price=5.0, stop_price=4.9, target_price=5.2,
                parent_order_id=i, target_order_id=i + 100, stop_order_id=i + 200,
                opened_ts=time.time(),
            )
        called = []
        monkeypatch.setattr(orders_mod, "place_bracket_order", lambda *a, **k: called.append(1))
        result = executor.place_from_ticket("NEWSYM", "gap_and_go", 5.0, 4.9, 5.2)
        assert result is None
        assert called == []

    def test_place_from_ticket_declines_leave_receipt(self, monkeypatch):
        """Every rejection is a decision — it must be auditable, not a bare
        None with only a log line."""
        _enable_auto_paper(monkeypatch)
        monkeypatch.setattr(risk_mod, "can_trade", lambda: (False, "Daily max loss reached."))
        monkeypatch.setattr(risk_mod, "position_size_shares", lambda: 100)
        monkeypatch.setattr(risk_mod, "validate_trade_plan", lambda e, s, t: (True, []))
        result = executor.place_from_ticket("AAPL", "gap_and_go", 5.0, 4.9, 5.2)
        assert result is None
        from nova_os.events import KIND_ACTION, get_events

        events = get_events(kind=KIND_ACTION, limit=5)
        assert any(
            (e.get("payload") or {}).get("event") == "placement_declined"
            and (e.get("payload") or {}).get("reason_code") == "RISK_HALT"
            for e in events
        )

    def test_places_bracket_when_auto_paper_and_checks_pass(self, monkeypatch):
        _enable_auto_paper(monkeypatch)
        _approve_risk(monkeypatch, qty=100)
        placed_kwargs = []
        monkeypatch.setattr(
            orders_mod, "place_bracket_order",
            lambda *a, **k: (placed_kwargs.append(k) or
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
        assert placed_kwargs[0]["symbol"] == "AAPL"
        assert placed_kwargs[0]["qty"] == 100


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

    def test_target_fill_emits_bracket_closed_receipt(self, monkeypatch):
        """Recovery's orphan/closed-symbol detection reads nova_os events, not
        the journal — a real close must leave a `bracket_closed` receipt."""
        self._seed_open_position()
        fake_ib = _FakeIB([_FakeFill("AAPL", 11, 5.20)])
        monkeypatch.setattr(executor._ibkr_client, "get_ib", lambda: fake_ib)
        monkeypatch.setattr(orders_mod, "open_orders", lambda: [])
        monkeypatch.setattr(risk_mod, "record_trade_result", lambda pnl: None)

        asyncio.run(executor._check_fills_once())

        from nova_os.events import KIND_ACTION, get_events

        events = get_events(kind=KIND_ACTION, limit=5)
        assert any(
            e.get("symbol") == "AAPL" and (e.get("payload") or {}).get("event") == "bracket_closed"
            for e in events
        )

    def test_no_fill_found_emits_bracket_closed_unverified_receipt(self, monkeypatch):
        self._seed_open_position()
        monkeypatch.setattr(executor._ibkr_client, "get_ib", lambda: _FakeIB([]))
        monkeypatch.setattr(orders_mod, "open_orders", lambda: [])

        asyncio.run(executor._check_fills_once())

        from nova_os.events import KIND_ACTION, get_events

        events = get_events(kind=KIND_ACTION, limit=5)
        assert any(
            e.get("symbol") == "AAPL"
            and (e.get("payload") or {}).get("event") == "bracket_closed_unverified"
            for e in events
        )


class TestFlattenReconciliation:
    def _seed_open_position(self, symbol="AAPL"):
        executor._open_positions[symbol] = executor.OpenPosition(
            symbol=symbol, setup="gap_and_go", qty=100,
            entry_price=5.0, stop_price=4.9, target_price=5.2,
            parent_order_id=10, target_order_id=11, stop_order_id=12,
            opened_ts=time.time(),
        )

    def test_skips_sell_when_no_real_ibkr_position(self, monkeypatch):
        """Parent never filled at IBKR — there is nothing to sell. Placing a
        market SELL here would open an accidental short."""
        self._seed_open_position()
        _arm_ibkr_execution(monkeypatch)
        monkeypatch.setattr(executor_flatten._account, "long_qty", lambda _s: 0.0)
        monkeypatch.setattr(orders_mod, "open_orders", lambda: [{"order_id": 10}])
        cancelled = []
        monkeypatch.setattr(
            orders_mod, "cancel_order", lambda oid: cancelled.append(oid) or {"ok": True}
        )
        sell_calls = []
        monkeypatch.setattr(
            orders_mod, "place_order",
            lambda *a, **k: sell_calls.append(a) or {"ok": True, "order_id": 99},
        )
        result = executor.flatten_positions("FLATTEN")
        assert sell_calls == []
        assert cancelled == [10]
        assert "AAPL" not in executor._open_positions
        assert result["results"][0]["outcome"] == "no_position_skipped_sell"

    def test_sells_real_position_and_cancels_protective_legs(self, monkeypatch):
        """Parent filled — a real IBKR position exists. Flatten must sell the
        REAL qty and cancel the (now stale) protective stop/target legs so
        they can't fire against a future position in the same symbol."""
        self._seed_open_position()
        _arm_ibkr_execution(monkeypatch)
        monkeypatch.setattr(executor_flatten._account, "long_qty", lambda _s: 100.0)
        monkeypatch.setattr(account_mod, "long_qty", lambda _s: 100.0)
        monkeypatch.setattr(
            account_mod, "get_positions",
            lambda: [{"symbol": "AAPL", "qty": 100.0, "avg_cost": 5.0}],
        )
        # Parent filled (not in open_orders); stop/target still working.
        monkeypatch.setattr(orders_mod, "open_orders", lambda: [{"order_id": 11}, {"order_id": 12}])
        cancelled = []
        monkeypatch.setattr(
            orders_mod, "cancel_order", lambda oid: cancelled.append(oid) or {"ok": True}
        )
        sell_calls = []
        monkeypatch.setattr(
            orders_mod, "place_order",
            lambda symbol, side, qty, **k: sell_calls.append((symbol, side, qty))
            or {"ok": True, "order_id": 50, "mode": "paper"},
        )
        result = executor.flatten_positions("FLATTEN")
        assert sell_calls == [("AAPL", "SELL", 100.0)]
        assert sorted(cancelled) == [11, 12]
        assert "AAPL" not in executor._open_positions
        assert result["results"][0]["outcome"] == "closed_real_position"
        assert result["ok"] is True

    def test_flatten_rejects_wrong_confirm_token(self):
        with pytest.raises(ValueError, match="FLATTEN"):
            executor.flatten_positions("nope")

    def test_flatten_aborts_when_position_read_fails(self, monkeypatch):
        """A transient long_qty() failure must abort flatten instead of
        being treated as 'no real position' — that would skip the sell AND
        cancel the protective stop/target, leaving a real position naked."""
        self._seed_open_position()
        _arm_ibkr_execution(monkeypatch)

        def boom(_sym):
            raise executor_flatten.IbkrAccountError("get_positions failed: boom")

        monkeypatch.setattr(executor_flatten._account, "long_qty", boom)
        cancelled = []
        monkeypatch.setattr(
            orders_mod, "cancel_order", lambda oid: cancelled.append(oid) or {"ok": True}
        )
        sell_calls = []
        monkeypatch.setattr(
            orders_mod, "place_order",
            lambda *a, **k: sell_calls.append(a) or {"ok": True, "order_id": 99},
        )
        result = executor.flatten_positions("FLATTEN")
        assert result["ok"] is False
        assert "boom" in result["error"]
        assert sell_calls == []
        assert cancelled == []
        assert "AAPL" in executor._open_positions

    def test_flatten_fails_loud_when_ibkr_disconnected(self, monkeypatch):
        self._seed_open_position()
        monkeypatch.setattr(executor._ibkr_client, "is_connected", lambda: False)
        result = executor.flatten_positions("FLATTEN")
        assert result["ok"] is False
        assert "not connected" in result["error"]
        # Nothing touched — position still tracked, no orders placed.
        assert "AAPL" in executor._open_positions
