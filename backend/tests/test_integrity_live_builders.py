"""Builders wire mode + active ages into integrity reports (mocked)."""
from __future__ import annotations

import integrity_live as live
import ibkr.client as ibkr_client
import ibkr.reprice as ibkr_reprice
import ibkr.scanner_l1 as ibkr_scanner_l1


def test_build_scanner_report_includes_current_mode(monkeypatch):
    class _State:
        current_mode = "afterhours"
        gapper_cache = [{"symbol": "AAA"}]
        gainer_cache = [{"symbol": "BBB"}]
        loser_cache = [{"symbol": "CCC"}]
        afterhours_cache: list = []
        gapper_cache_ts = 1.0
        gainer_cache_ts = 1_700_000_000.0
        loser_cache_ts = 1_700_000_000.0
        afterhours_cache_ts = 1_700_000_000.0

    monkeypatch.setattr(live, "get_runtime_state", lambda: _State())
    monkeypatch.setattr(
        "alpaca._get_discovery_provider",
        lambda: "ibkr",
    )
    monkeypatch.setattr(ibkr_client, "is_connected", lambda: True)
    monkeypatch.setattr(ibkr_scanner_l1, "get_last_ok_ts", lambda: 1_700_000_000.0)
    monkeypatch.setattr(
        ibkr_scanner_l1,
        "get_subscription_state",
        lambda: {
            "active_total": 40,
            "active_tab": 0,
            "active_hod": 40,
            "error": None,
        },
    )
    monkeypatch.setattr(ibkr_reprice, "_table_busy_skips", 0, raising=False)
    monkeypatch.setattr(ibkr_reprice, "_table_timeouts", 0, raising=False)

    report = live.build_scanner_integrity_report()
    assert report["metrics"]["current_mode"] == "afterhours"
    gap = next(c for c in report["checks"] if c["id"] == "scanner_gappers")
    assert gap["status"] == "pass"
