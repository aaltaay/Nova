"""Route/API contract tests for backend/routes/executor.py.

No live IB Gateway — IBKR/risk internals are mocked, mirroring
test_executor.py's style. These exercise the HTTP contract (status codes,
response shapes) for the mode ladder, kill switch, staged-ticket approval,
and the "signal impossibility" guarantee: once mode drops to signal, a
previously staged ticket can never be approved into an order via the API.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import journal.db as db
import nova_os.events_db as events_db
import strategy.executor as executor
import strategy.risk as risk_mod
from constants import NOVA_OS_MODE_AUTO_PAPER, NOVA_OS_MODE_CONFIRM, NOVA_OS_MODE_SIGNAL
from main import app
from nova_os import control_mode, staged_tickets

client = TestClient(app)


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "cache_dir", lambda: tmp_path)
    monkeypatch.setattr(events_db, "cache_dir", lambda: tmp_path)
    db.init_db()
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


_SIGNAL = {"entry_price": 5.00, "stop_price": 4.90, "target_price": 5.20}


def _stage_one_ticket() -> str:
    ticket = staged_tickets.stage_from_signal(
        "AAPL", "gap_and_go", _SIGNAL, decision_meta={"shares": 10},
    )
    assert ticket is not None
    return ticket.id


class TestModeTransitionsContract:
    def test_signal_to_confirm_succeeds(self):
        res = client.post("/api/strategy/executor/mode", json={"mode": NOVA_OS_MODE_CONFIRM})
        assert res.status_code == 200
        assert res.json()["control_mode"] == NOVA_OS_MODE_CONFIRM

    def test_unknown_mode_rejected_with_409(self):
        res = client.post("/api/strategy/executor/mode", json={"mode": "yolo"})
        assert res.status_code == 409
        assert "unknown control mode" in res.json()["detail"]

    def test_auto_live_always_rejected_with_409(self):
        """Hard invariant: no route call can ever raise the API into auto_live."""
        res = client.post("/api/strategy/executor/mode", json={"mode": "auto_live"})
        assert res.status_code == 409
        assert "auto_live is not enabled" in res.json()["detail"]

    def test_raising_mode_blocked_while_kill_switch_tripped(self):
        client.post("/api/strategy/executor/kill-switch")
        res = client.post("/api/strategy/executor/mode", json={"mode": NOVA_OS_MODE_CONFIRM})
        assert res.status_code == 409
        assert "kill switch is tripped" in res.json()["detail"]

    def test_reset_kill_switch_unblocks_raising_mode(self):
        client.post("/api/strategy/executor/kill-switch")
        client.post("/api/strategy/executor/reset-kill-switch")
        res = client.post("/api/strategy/executor/mode", json={"mode": NOVA_OS_MODE_CONFIRM})
        assert res.status_code == 200

    def test_auto_paper_blocked_with_409_when_gate_fails(self):
        with patch.object(
            control_mode, "auto_paper_gate_status",
            return_value=(False, "auto_paper requires IBKR connected on paper Gateway"),
        ):
            res = client.post(
                "/api/strategy/executor/mode", json={"mode": NOVA_OS_MODE_AUTO_PAPER},
            )
        assert res.status_code == 409
        assert "IBKR connected" in res.json()["detail"]

    def test_auto_paper_allowed_with_200_when_gate_passes(self):
        with patch.object(control_mode, "auto_paper_gate_status", return_value=(True, "OK")):
            res = client.post(
                "/api/strategy/executor/mode", json={"mode": NOVA_OS_MODE_AUTO_PAPER},
            )
        assert res.status_code == 200
        assert res.json()["control_mode"] == NOVA_OS_MODE_AUTO_PAPER


class TestArmDisarmRoutes:
    def test_arm_route_sets_confirm(self):
        res = client.post("/api/strategy/executor/arm")
        assert res.status_code == 200
        assert res.json()["control_mode"] == NOVA_OS_MODE_CONFIRM

    def test_arm_route_blocked_by_kill_switch_with_409(self):
        client.post("/api/strategy/executor/kill-switch")
        res = client.post("/api/strategy/executor/arm")
        assert res.status_code == 409
        assert "kill switch is tripped" in res.json()["detail"]

    def test_disarm_route_drops_to_signal(self):
        client.post("/api/strategy/executor/arm")
        res = client.post("/api/strategy/executor/disarm")
        assert res.status_code == 200
        assert res.json()["control_mode"] == NOVA_OS_MODE_SIGNAL


class TestStagedApprovalContract:
    def test_approve_unknown_ticket_returns_409(self):
        res = client.post("/api/strategy/executor/staged/does-not-exist/approve")
        assert res.status_code == 409
        assert "not found" in res.json()["detail"]

    def test_reject_unknown_ticket_returns_404(self):
        res = client.post("/api/strategy/executor/staged/does-not-exist/reject")
        assert res.status_code == 404

    def test_approve_happy_path_delegates_to_executor(self, monkeypatch):
        control_mode._mode = NOVA_OS_MODE_CONFIRM
        monkeypatch.setattr(risk_mod, "can_trade", lambda: (True, "OK"))
        ticket_id = _stage_one_ticket()
        fake_placement = {"ok": True, "order_id": 1}
        with patch.object(executor, "place_from_ticket", return_value=fake_placement):
            res = client.post(f"/api/strategy/executor/staged/{ticket_id}/approve")
        assert res.status_code == 200
        body = res.json()
        assert body["ok"] is True
        assert body["placed"] == fake_placement

    def test_reject_with_reason_body_is_recorded(self):
        control_mode._mode = NOVA_OS_MODE_CONFIRM
        ticket_id = _stage_one_ticket()
        res = client.post(
            f"/api/strategy/executor/staged/{ticket_id}/reject",
            json={"reason": "operator declined — spread too wide"},
        )
        assert res.status_code == 200
        assert res.json()["receipt"]["payload"]["reason"] == "operator declined — spread too wide"

    def test_signal_impossibility_staged_ticket_cannot_survive_mode_drop_to_signal(self):
        """The core "signal impossibility" guarantee at the API level: once an
        operator drops mode to signal, a ticket staged under confirm can never
        be approved afterward — set_mode(signal) must have already voided it."""
        control_mode._mode = NOVA_OS_MODE_CONFIRM
        ticket_id = _stage_one_ticket()
        assert staged_tickets.get_staged(ticket_id) is not None

        res_mode = client.post(
            "/api/strategy/executor/mode", json={"mode": NOVA_OS_MODE_SIGNAL},
        )
        assert res_mode.status_code == 200
        assert staged_tickets.get_staged(ticket_id) is None

        res_approve = client.post(f"/api/strategy/executor/staged/{ticket_id}/approve")
        assert res_approve.status_code == 409
        assert "not found" in res_approve.json()["detail"]
