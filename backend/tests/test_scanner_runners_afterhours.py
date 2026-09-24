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


def test_afterhours_rvol_names_its_alpaca_average(monkeypatch):
    """QA C39: the AH RVOL divides by Alpaca IEX daily bars -- never label it yfinance."""
    state = _fake_state()
    state.avg_volume_cache = {"TOPS": 20_000.0}
    seen: dict = {}

    def fake_snapshot(sym, **kw):
        seen[sym] = kw.get("rvol_source")

    monkeypatch.setattr(scan_runners, "get_runtime_state", lambda: state)
    monkeypatch.setattr(scan_runners, "_get_discovery_provider", lambda: "ibkr")
    monkeypatch.setattr(scan_runners, "_alpaca_headers", lambda: None)
    monkeypatch.setattr(scan_runners._ibkr_discovery, "get_afterhours_gainers", lambda: None)
    monkeypatch.setattr(
        scan_runners,
        "run_ibkr",
        lambda coro, on_error="none", label="ibkr": [
            {"symbol": "TOPS", "price": 2.5, "prev_close": 1.5, "change_pct": 0.66, "volume": 1_000_000},
            {"symbol": "NOAVG", "price": 3.0, "prev_close": 2.0, "change_pct": 0.5, "volume": 50_000},
        ],
    )
    monkeypatch.setattr(scan_runners, "mark_resub", lambda: None)
    monkeypatch.setattr(
        afterhours, "_hod_momo",
        type("M", (), {"update_ticker_snapshot": staticmethod(lambda sym, **kw: fake_snapshot(sym, **kw))})(),
    )
    monkeypatch.setattr(scan_runners, "save_afterhours_snapshot", lambda *a, **k: None)
    import universe as _universe

    monkeypatch.setattr(_universe, "refresh_hod_momo_universe", lambda: None)

    afterhours.run_afterhours_discovery_scan()

    rows = {r["symbol"]: r for r in state.afterhours_cache}
    assert rows["TOPS"]["rel_volume"] is not None
    assert rows["TOPS"]["rvol_source"] == "alpaca"
    assert rows["NOAVG"]["rel_volume"] is None
    assert rows["NOAVG"]["rvol_source"] is None
    # The HOD snapshot no longer calls an Alpaca-average RVOL "ibkr_pace".
    assert seen["TOPS"] in ("alpaca_pace", "alpaca")
    assert "_hod_rvol_source" not in rows["TOPS"]


def test_afterhours_hands_hod_momo_the_float_check_with_the_float(monkeypatch):
    """#532: HOD Momo's max_float reads a contradicted float on shares outstanding, so the check rides
    with the float the after-hours runner seeds."""
    import fundamentals

    state = _fake_state()
    seen: dict = {}
    monkeypatch.setitem(fundamentals._fundamentals_cache, "SECZ", {
        "float_shares": 8_450_000, "shares_outstanding": 163_270_000, "float_contradicted": True})
    monkeypatch.setattr(scan_runners, "get_runtime_state", lambda: state)
    monkeypatch.setattr(scan_runners, "_get_discovery_provider", lambda: "ibkr")
    monkeypatch.setattr(scan_runners, "_alpaca_headers", lambda: None)
    monkeypatch.setattr(scan_runners._ibkr_discovery, "get_afterhours_gainers", lambda: None)
    monkeypatch.setattr(
        scan_runners,
        "run_ibkr",
        lambda coro, on_error="none", label="ibkr": [
            {"symbol": "SECZ", "price": 11.2, "prev_close": 5.0, "change_pct": 1.24, "volume": 900_000},
            {"symbol": "NOFUND", "price": 3.0, "prev_close": 2.0, "change_pct": 0.5, "volume": 50_000},
        ],
    )
    monkeypatch.setattr(scan_runners, "mark_resub", lambda: None)
    monkeypatch.setattr(
        afterhours, "_hod_momo",
        type("M", (), {"update_ticker_snapshot": staticmethod(lambda sym, **kw: seen.__setitem__(sym, kw))})(),
    )
    monkeypatch.setattr(scan_runners, "save_afterhours_snapshot", lambda *a, **k: None)
    import universe as _universe

    monkeypatch.setattr(_universe, "refresh_hod_momo_universe", lambda: None)

    afterhours.run_afterhours_discovery_scan()

    secz = seen["SECZ"]
    assert (secz["float_shares"], secz["float_contradicted"], secz["shares_outstanding"]) == (
        8_450_000, True, 163_270_000)
    nofund = seen["NOFUND"]
    assert (nofund["float_shares"], nofund["float_contradicted"], nofund["shares_outstanding"]) == (None, None, None)


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
