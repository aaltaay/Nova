"""Unit tests for Nova OS P4 staged tickets + kill integration."""
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import nova_os.events_db as events_db
import strategy.executor as executor
from constants import NOVA_OS_CONFIRM_TIMEOUT_SEC, NOVA_OS_MODE_CONFIRM, NOVA_OS_MODE_SIGNAL
from nova_os import control_mode, staged_tickets


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(events_db, "cache_dir", lambda: tmp_path)
    events_db.init_db()
    control_mode.reset_for_tests()
    staged_tickets.reset_for_tests()
    executor._kill_switch_tripped = False
    executor._open_positions.clear()
    yield
    control_mode.reset_for_tests()
    staged_tickets.reset_for_tests()
    executor._kill_switch_tripped = False
    executor._open_positions.clear()


_SIGNAL = {"entry_price": 5.0, "stop_price": 4.9, "target_price": 5.2, "shares": 100}


class TestStageExpireApprove:
    def test_stage_and_expire(self, monkeypatch):
        monkeypatch.setattr(
            "constants.NOVA_OS_CONFIRM_TIMEOUT_SEC", 0.01, raising=False
        )
        # Patch the module-level import used by staged_tickets
        import nova_os.staged_tickets as st

        monkeypatch.setattr(st, "NOVA_OS_CONFIRM_TIMEOUT_SEC", 0.01)
        ticket = staged_tickets.stage_from_signal("AAPL", "gap_and_go", _SIGNAL)
        assert ticket is not None
        assert ticket.symbol == "AAPL"
        assert len(staged_tickets.list_staged()) == 1
        time.sleep(0.02)
        expired = staged_tickets.expire_due()
        assert len(expired) == 1
        assert staged_tickets.list_staged() == []

    def test_approve_calls_place_from_ticket(self, monkeypatch):
        called = []

        def fake_place(symbol, setup, entry, stop, target, shares=None, **_kw):
            called.append(
                {"symbol": symbol, "setup": setup, "entry": entry, "shares": shares}
            )
            return {"symbol": symbol, "qty": shares}

        monkeypatch.setattr(executor, "place_from_ticket", fake_place)
        control_mode.set_mode(NOVA_OS_MODE_CONFIRM)
        ticket = staged_tickets.stage_from_signal("AAPL", "gap_and_go", _SIGNAL)
        assert ticket is not None
        result = staged_tickets.approve(ticket.id)
        assert result["ok"] is True
        assert called == [
            {
                "symbol": "AAPL",
                "setup": "gap_and_go",
                "entry": 5.0,
                "shares": 100,
            }
        ]
        assert staged_tickets.list_staged() == []

    def test_kill_rejects_staged_and_forces_signal(self, monkeypatch):
        control_mode.set_mode(NOVA_OS_MODE_CONFIRM)
        staged_tickets.stage_from_signal("AAPL", "gap_and_go", _SIGNAL)
        monkeypatch.setattr(executor._ibkr_client, "is_connected", lambda: False)
        monkeypatch.setattr(executor._orders, "open_orders", lambda: [])
        executor.kill_switch()
        assert control_mode.get_mode() == NOVA_OS_MODE_SIGNAL
        assert staged_tickets.list_staged() == []
        assert executor._kill_switch_tripped is True

    def test_set_mode_signal_rejects_staged(self):
        """Dropping to signal directly via set_mode (not just kill/disarm)
        must also void any staged confirm tickets — the "nothing executes
        without Approve" promise ends the instant automation is signal-only."""
        control_mode.set_mode(NOVA_OS_MODE_CONFIRM)
        staged_tickets.stage_from_signal("AAPL", "gap_and_go", _SIGNAL)
        assert len(staged_tickets.list_staged()) == 1
        control_mode.set_mode(NOVA_OS_MODE_SIGNAL)
        assert staged_tickets.list_staged() == []

    def test_approve_blocked_when_kill_tripped(self, monkeypatch):
        control_mode.set_mode(NOVA_OS_MODE_CONFIRM)
        ticket = staged_tickets.stage_from_signal("AAPL", "gap_and_go", _SIGNAL)
        assert ticket is not None
        # Trip kill without going through executor.kill_switch() (which would
        # already reject staged) to isolate approve()'s own re-check.
        executor._kill_switch_tripped = True
        called = []
        monkeypatch.setattr(
            executor, "place_from_ticket", lambda *a, **k: called.append(1) or None
        )
        with pytest.raises(ValueError, match="kill switch"):
            staged_tickets.approve(ticket.id)
        assert called == []
        # Ticket was claimed (popped) even though declined — never restaged.
        assert staged_tickets.list_staged() == []

    def test_approve_blocked_when_mode_dropped_to_signal_after_staging(self, monkeypatch):
        control_mode.set_mode(NOVA_OS_MODE_CONFIRM)
        ticket = staged_tickets.stage_from_signal("AAPL", "gap_and_go", _SIGNAL)
        assert ticket is not None
        # Re-add it directly to simulate a mode drop that happened AFTER
        # staging but where the ticket itself survived (e.g. a future code
        # path that stages without going through kill/disarm). approve()'s
        # own mode re-check must still catch this.
        control_mode._mode = NOVA_OS_MODE_SIGNAL
        staged_tickets._staged[ticket.id] = ticket
        called = []
        monkeypatch.setattr(
            executor, "place_from_ticket", lambda *a, **k: called.append(1) or None
        )
        with pytest.raises(ValueError, match="signal"):
            staged_tickets.approve(ticket.id)
        assert called == []

    def test_approve_is_atomic_second_call_fails(self, monkeypatch):
        control_mode.set_mode(NOVA_OS_MODE_CONFIRM)
        ticket = staged_tickets.stage_from_signal("AAPL", "gap_and_go", _SIGNAL)
        assert ticket is not None
        monkeypatch.setattr(
            executor, "place_from_ticket",
            lambda *a, **k: {"symbol": "AAPL", "qty": 100},
        )
        first = staged_tickets.approve(ticket.id)
        assert first["ok"] is True
        with pytest.raises(ValueError, match="not found"):
            staged_tickets.approve(ticket.id)


class TestOnSignalConfirm:
    def test_confirm_stages_does_not_place(self, monkeypatch):
        placed = []
        monkeypatch.setattr(
            executor, "place_from_ticket", lambda *a, **k: placed.append(1) or None
        )
        control_mode.set_mode(NOVA_OS_MODE_CONFIRM)
        import asyncio

        result = asyncio.run(executor.on_signal("TSLA", "gap_and_go", _SIGNAL))
        assert result is not None
        assert result["symbol"] == "TSLA"
        assert result["status"] == "staged"
        assert placed == []
        assert len(staged_tickets.list_staged()) == 1
