"""Unit tests for strategy/setups_stream.py's Nova OS decide() wiring.

Regression coverage for the "mode-receipt split-brain": _scan_once() used to
hardcode mode=NOVA_OS_DEFAULT_MODE ("signal") when calling nova_os.decide(),
so every journaled receipt claimed the system was in signal mode and
would_execute=False even while control_mode was actually auto_paper/confirm
and executor.on_signal() below went on to place/stage a real order. These
tests assert the scan loop now passes the REAL current control mode.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from constants import NOVA_OS_DECISION_NO_BUY, NOVA_OS_MODE_AUTO_PAPER, NOVA_OS_MODE_SIGNAL
from nova_os import control_mode
import nova_os.events_db as events_db
import strategy.setups_stream as setups_stream


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(events_db, "cache_dir", lambda: tmp_path)
    events_db.init_db()
    control_mode.reset_for_tests()
    setups_stream._last_alert_ts.clear()
    setups_stream._signal_history.clear()
    yield
    control_mode.reset_for_tests()


def _fake_decision(mode: str) -> SimpleNamespace:
    """Mimic the subset of NovaOsDecision._scan_once reads."""
    return SimpleNamespace(
        decision=NOVA_OS_DECISION_NO_BUY,
        reason_codes=["PILLAR_FLOAT_FAIL"],
        mode=mode,
        would_execute=False,
        ticket=None,
        receipt={"id": 1},
    )


def _run_scan_once_with_one_candidate(monkeypatch):
    entry = SimpleNamespace(symbol="MOCK")
    monkeypatch.setattr(setups_stream, "_watchlist_universe", lambda: [{"symbol": "MOCK"}])
    monkeypatch.setattr(setups_stream, "build_watchlist", lambda universe, limit: [entry])
    monkeypatch.setattr(
        setups_stream,
        "evaluate_setups",
        lambda row, bars: {"eligible_setups": ["gap_and_go"], "gap_and_go": {"eligible": True}},
    )
    monkeypatch.setattr(setups_stream._l2_recorder, "on_signal", AsyncMock())
    monkeypatch.setattr(setups_stream._executor, "on_signal", AsyncMock())
    monkeypatch.setattr(setups_stream, "_record_signal", lambda *a, **k: {"timestamp": 0.0})

    captured: dict = {}

    def _fake_nova_os_decide(row, bars, *, watchlist_rank, mode, preferred_setup):
        captured["mode"] = mode
        return _fake_decision(mode)

    monkeypatch.setattr(setups_stream, "nova_os_decide", _fake_nova_os_decide)

    with (
        patch("alpaca._get_discovery_provider", return_value="alpaca"),
        patch("chart_bars.fetch_chart_bars", return_value={"bars": [{"t": "x"}]}),
        patch("ibkr.historical_gate.interactive_busy", return_value=False),
    ):
        asyncio.run(setups_stream._scan_once())

    return captured


class TestScanOncePassesRealControlMode:
    def test_signal_mode_passed_through(self, monkeypatch):
        control_mode.set_mode(NOVA_OS_MODE_SIGNAL)
        captured = _run_scan_once_with_one_candidate(monkeypatch)
        assert captured["mode"] == NOVA_OS_MODE_SIGNAL

    def test_auto_paper_mode_passed_through_not_hardcoded_signal(self, monkeypatch):
        """The regression case: control_mode is auto_paper, so decide() must
        see mode=auto_paper — never the hardcoded NOVA_OS_DEFAULT_MODE."""
        monkeypatch.setattr(control_mode, "_mode", NOVA_OS_MODE_AUTO_PAPER)
        captured = _run_scan_once_with_one_candidate(monkeypatch)
        assert captured["mode"] == NOVA_OS_MODE_AUTO_PAPER


class TestScanOnceBroadcastContract:
    """The /ws/strategy payload the frontend consumes (see routes/hod_momo.py
    ws_strategy + setups_stream._broadcast). mode/would_execute here must be
    the same values just journaled to the receipt, not a stale/default mode."""

    def test_broadcast_payload_carries_real_mode_and_would_execute(self, monkeypatch):
        monkeypatch.setattr(control_mode, "_mode", NOVA_OS_MODE_AUTO_PAPER)
        entry = SimpleNamespace(symbol="MOCK")
        monkeypatch.setattr(setups_stream, "_watchlist_universe", lambda: [{"symbol": "MOCK"}])
        monkeypatch.setattr(setups_stream, "build_watchlist", lambda universe, limit: [entry])
        monkeypatch.setattr(
            setups_stream,
            "evaluate_setups",
            lambda row, bars: {"eligible_setups": ["gap_and_go"], "gap_and_go": {"eligible": True}},
        )
        monkeypatch.setattr(setups_stream._l2_recorder, "on_signal", AsyncMock())
        monkeypatch.setattr(setups_stream._executor, "on_signal", AsyncMock())
        monkeypatch.setattr(setups_stream, "_record_signal", lambda *a, **k: {"timestamp": 0.0})
        monkeypatch.setattr(
            setups_stream,
            "nova_os_decide",
            lambda row, bars, *, watchlist_rank, mode, preferred_setup: _fake_decision(mode),
        )
        broadcasts: list[dict] = []
        monkeypatch.setattr(setups_stream, "_broadcast", AsyncMock(side_effect=broadcasts.append))

        with (
            patch("alpaca._get_discovery_provider", return_value="alpaca"),
            patch("chart_bars.fetch_chart_bars", return_value={"bars": [{"t": "x"}]}),
            patch("ibkr.historical_gate.interactive_busy", return_value=False),
        ):
            asyncio.run(setups_stream._scan_once())

        assert len(broadcasts) == 1
        payload = broadcasts[0]
        assert payload["type"] == "decision"
        assert payload["mode"] == NOVA_OS_MODE_AUTO_PAPER
        assert payload["decision"] == NOVA_OS_DECISION_NO_BUY
        assert payload["would_execute"] is False
        assert "receipt_id" in payload
        assert "reason_codes" in payload
