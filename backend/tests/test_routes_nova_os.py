"""Tests for the Nova OS decide display endpoints (backend/routes/nova_os.py).

Regression coverage for two "truthful decisions" fixes:
  1. These endpoints are polled every few seconds by the frontend
     (useNovaOsDecide.ts) and must call decide(record=False) so polling never
     writes append-only receipts for symbols nobody acted on.
  2. They must pass the REAL current control mode, not a hardcoded default,
     so the displayed would_execute/mode matches what the scan loop journals.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import nova_os.events_db as events_db
from constants import NOVA_OS_MODE_AUTO_PAPER, NOVA_OS_MODE_SIGNAL
from main import app
from nova_os import control_mode
from runtime_state import ScannerRuntimeState, set_runtime_state_for_testing

client = TestClient(app)


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    state = ScannerRuntimeState()
    previous_state = set_runtime_state_for_testing(state)
    monkeypatch.setattr(events_db, "cache_dir", lambda: tmp_path)
    events_db.init_db()
    monkeypatch.setattr(control_mode, "_mode", NOVA_OS_MODE_SIGNAL)
    state.gapper_cache = [{"symbol": "MOCK", "price": 5.5}]
    state.gainer_cache = []
    yield
    set_runtime_state_for_testing(previous_state)
    monkeypatch.setattr(control_mode, "_mode", NOVA_OS_MODE_SIGNAL)


def _no_receipts_written() -> bool:
    from nova_os.events import get_events
    return get_events() == []


class TestDecideOneSymbolIsDisplayOnly:
    def test_uses_real_control_mode_not_hardcoded_default(self):
        monkeypatch_mode = NOVA_OS_MODE_AUTO_PAPER
        with patch.object(control_mode, "_mode", monkeypatch_mode):
            with patch("routes.nova_os._fetch_chart_bars", return_value={"bars": [{"t": "x"}]}):
                res = client.get("/api/nova-os/decide/MOCK")
        assert res.status_code == 200
        body = res.json()
        assert body["mode"] == monkeypatch_mode

    def test_does_not_write_a_receipt(self):
        with patch("routes.nova_os._fetch_chart_bars", return_value={"bars": [{"t": "x"}]}):
            res = client.get("/api/nova-os/decide/MOCK")
        assert res.status_code == 200
        assert res.json()["receipt"]["id"] is None
        assert _no_receipts_written()


class TestDecideWatchlistIsDisplayOnly:
    def test_uses_real_control_mode_not_hardcoded_default(self):
        with patch.object(control_mode, "_mode", NOVA_OS_MODE_AUTO_PAPER):
            with patch("routes.nova_os._fetch_chart_bars", return_value={"bars": [{"t": "x"}]}):
                res = client.get("/api/nova-os/decide")
        assert res.status_code == 200
        body = res.json()
        assert body["count"] >= 1
        assert all(d["mode"] == NOVA_OS_MODE_AUTO_PAPER for d in body["decisions"])

    def test_does_not_write_receipts(self):
        with patch("routes.nova_os._fetch_chart_bars", return_value={"bars": [{"t": "x"}]}):
            res = client.get("/api/nova-os/decide")
        assert res.status_code == 200
        assert all(d["receipt"]["id"] is None for d in res.json()["decisions"])
        assert _no_receipts_written()

    def test_bars_fetch_failure_is_reported_loudly_not_as_a_fake_no_buy(self):
        """A bars-fetch exception must show up in `errors`, never get folded
        into `decisions` as an indistinguishable NO_BUY verdict."""
        with patch("routes.nova_os._fetch_chart_bars", side_effect=RuntimeError("boom")):
            res = client.get("/api/nova-os/decide")
        assert res.status_code == 200
        body = res.json()
        assert body["decisions"] == []
        assert body["errors"]
        assert body["errors"][0]["symbol"] == "MOCK"
        assert "boom" in body["errors"][0]["error"]
        assert _no_receipts_written()
