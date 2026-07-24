"""Tests for scanner_runners.afterhours sticky-bridge-error clearing.

Regression for PROBLEM_LOG 2026-07-23 "AH sticky bridge error never clears":
``run_afterhours_discovery_scan``/``run_afterhours_focus_scan`` never cleared
``state.ibkr_bridge_last_error`` on success, unlike ``movers.py``/
``discovery.py`` — one transient AH timeout painted Integrity fail for the
rest of the session even while AH rows kept landing every cycle.
"""
from __future__ import annotations

import scan_runners
from runtime_state import ScannerRuntimeState
from runtime_state.state import TABLE_STATE_LIVE
import scanner_runners.afterhours as afterhours


def _fake_state() -> ScannerRuntimeState:
    state = ScannerRuntimeState()
    state.afterhours_table.state = TABLE_STATE_LIVE
    return state


def test_run_afterhours_discovery_scan_clears_sticky_bridge_error(monkeypatch):
    state = _fake_state()
    state.ibkr_bridge_last_error = (
        "afterhours: TimeoutError: TimeoutError()"
    )
    state.ibkr_bridge_last_error_ts = 1_700_000_000.0

    monkeypatch.setattr(scan_runners, "get_runtime_state", lambda: state)
    monkeypatch.setattr(scan_runners, "_get_discovery_provider", lambda: "ibkr")
    monkeypatch.setattr(scan_runners, "_alpaca_headers", lambda: None)
    monkeypatch.setattr(scan_runners._ibkr_discovery, "get_afterhours_gainers", lambda: None)
    monkeypatch.setattr(
        scan_runners,
        "run_ibkr",
        lambda coro, on_error="none", label="ibkr": [
            {"symbol": "WLDS", "price": 3.21, "prev_close": 1.20, "change_pct": 1.675, "volume": 500_000}
        ],
    )
    monkeypatch.setattr(scan_runners, "mark_resub", lambda: None)
    monkeypatch.setattr(afterhours, "_hod_momo", type("M", (), {"update_ticker_snapshot": staticmethod(lambda *a, **k: None)})())
    monkeypatch.setattr(scan_runners, "save_afterhours_snapshot", lambda *a, **k: None)
    import universe as _universe

    monkeypatch.setattr(_universe, "refresh_hod_momo_universe", lambda: None)

    afterhours.run_afterhours_discovery_scan()

    assert state.afterhours_cache
    assert state.afterhours_cache[0]["symbol"] == "WLDS"
    assert state.ibkr_bridge_last_error == ""


def test_run_afterhours_focus_scan_clears_sticky_bridge_error(monkeypatch):
    state = _fake_state()
    state.afterhours_cache = [
        {"symbol": "WLDS", "current_price": 3.0, "previous_close": 1.2, "gap_percent": 1.5, "volume": 400_000}
    ]
    state.ibkr_bridge_last_error = "afterhours: TimeoutError: TimeoutError()"
    state.ibkr_bridge_last_error_ts = 1_700_000_000.0

    monkeypatch.setattr(scan_runners, "get_runtime_state", lambda: state)
    monkeypatch.setattr(scan_runners, "_get_discovery_provider", lambda: "ibkr")
    monkeypatch.setattr(scan_runners._ibkr_discovery, "snapshot_quotes", lambda *a, **k: None)
    monkeypatch.setattr(
        scan_runners,
        "run_ibkr",
        lambda coro, on_error="none", label="ibkr": {"WLDS": {"price": 3.4, "volume": 450_000}},
    )
    monkeypatch.setattr(
        afterhours._ah_discovery,
        "reprice_afterhours_rows_ibkr",
        lambda rows, quotes, avg_vol: [{**rows[0], "current_price": 3.4}],
    )
    monkeypatch.setattr(scan_runners, "save_afterhours_snapshot", lambda *a, **k: None)

    afterhours.run_afterhours_focus_scan()

    assert state.afterhours_cache[0]["current_price"] == 3.4
    assert state.ibkr_bridge_last_error == ""
