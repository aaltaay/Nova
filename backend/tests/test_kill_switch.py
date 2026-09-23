"""Kill switch (D-037, ADR 025): a persisted latch that blocks every place.

Ported from the retired Phase D executor tests. No live IB Gateway: IBKR calls
are mocked; the latch file lives in the per-test cache dir (conftest).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import kill_switch
import nova_os.events_db as events_db
from ibkr import client as client_mod
from ibkr import orders as orders_mod
from kill_switch import state as kill_state
from kill_switch import sweep as kill_sweep


@pytest.fixture(autouse=True)
def _events_db():
    events_db.init_db()


def _connected(monkeypatch, rows):
    cancelled: list[int] = []
    monkeypatch.setattr(client_mod, "is_connected", lambda: True)
    monkeypatch.setattr(orders_mod, "open_orders", lambda: rows)
    monkeypatch.setattr(
        kill_sweep, "cancel_via_service", lambda oid: cancelled.append(oid) or {"ok": True},
    )
    return cancelled


class TestLatch:
    def test_clean_cache_dir_is_not_tripped(self):
        assert kill_switch.is_tripped() is False

    def test_trip_persists_across_process_restart(self, monkeypatch):
        _connected(monkeypatch, [])
        kill_switch.trip()
        kill_switch.reset_for_tests()  # a fresh process reads the latch from disk
        assert kill_switch.is_tripped() is True
        assert kill_switch.status()["tripped"] is True

    def test_reset_persists_across_process_restart(self, monkeypatch):
        _connected(monkeypatch, [])
        kill_switch.trip()
        kill_switch.reset()
        kill_switch.reset_for_tests()
        assert kill_switch.is_tripped() is False

    def test_unreadable_latch_fails_tripped(self):
        kill_state._path().write_text("{not json", encoding="utf-8")
        assert kill_switch.is_tripped() is True

    def test_unknown_schema_version_fails_tripped(self):
        kill_state._path().write_text(
            json.dumps({"schema_version": 99, "tripped": False}), encoding="utf-8",
        )
        assert kill_switch.is_tripped() is True

    def test_trip_writes_a_kill_switch_receipt(self, monkeypatch):
        from nova_os.events import get_events

        _connected(monkeypatch, [])
        kill_switch.trip()
        events = get_events(limit=5)
        assert events[0]["payload"]["event"] == "kill_switch"


class TestSweep:
    def test_every_working_order_is_cancelled(self, monkeypatch):
        cancelled = _connected(
            monkeypatch, [{"order_id": 55, "symbol": "TSLA"}, {"order_id": 56, "symbol": "AAPL"}],
        )
        result = kill_switch.trip()
        assert cancelled == [55, 56]
        assert result["tripped"] is True
        assert result["cancelled_order_ids"] == [55, 56]

    def test_latch_is_set_before_the_sweep(self, monkeypatch):
        seen: list[bool] = []
        monkeypatch.setattr(client_mod, "is_connected", lambda: True)
        monkeypatch.setattr(orders_mod, "open_orders", lambda: [{"order_id": 7}])
        monkeypatch.setattr(
            kill_sweep, "cancel_via_service",
            lambda oid: seen.append(kill_switch.is_tripped()) or {"ok": True},
        )
        kill_switch.trip()
        assert seen == [True]

    def test_sweep_skipped_when_disconnected(self, monkeypatch):
        monkeypatch.setattr(client_mod, "is_connected", lambda: False)
        result = kill_switch.trip()
        assert result["cancelled_order_ids"] == []
        assert result["tripped"] is True

    def test_failed_cancel_is_reported(self, monkeypatch):
        monkeypatch.setattr(client_mod, "is_connected", lambda: True)
        monkeypatch.setattr(orders_mod, "open_orders", lambda: [{"order_id": 9}])

        def _boom(oid):
            raise RuntimeError("broker said no")

        monkeypatch.setattr(kill_sweep, "cancel_via_service", _boom)
        result = kill_switch.trip()
        assert result["failed_cancel_order_ids"] == [9]
        assert kill_switch.is_tripped() is True


class TestRoutes:
    def test_status_trip_reset(self, monkeypatch):
        from main import app

        _connected(monkeypatch, [])
        client = TestClient(app)
        assert client.get("/api/kill-switch").json()["tripped"] is False
        assert client.post("/api/kill-switch").json()["tripped"] is True
        assert client.get("/api/kill-switch").json()["tripped"] is True
        assert client.post("/api/kill-switch/reset").json()["tripped"] is False

    def test_retired_executor_routes_are_gone(self):
        from main import app

        client = TestClient(app)
        assert client.get("/api/strategy/executor/status").status_code == 404
        assert client.get("/api/nova-os/decide").status_code == 404
