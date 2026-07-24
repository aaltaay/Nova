"""Mode-aware scanner integrity — gappers offline after open is not a fail."""
from __future__ import annotations

from hod_momo_integrity_scanner import evaluate_scanner_integrity


def _base(**overrides):
    snap = {
        "discovery_provider": "ibkr",
        "ibkr_connected": True,
        "current_mode": "premarket",
        "gapper_count": 25,
        "gainer_count": 50,
        "loser_count": 50,
        "gapper_age_sec": 10.0,
        "gainer_age_sec": 10.0,
        "loser_age_sec": 10.0,
        "scanner_l1_age_sec": 1.0,
    }
    snap.update(overrides)
    return snap


def test_stale_gappers_warn_in_premarket():
    report = evaluate_scanner_integrity(_base(
        current_mode="premarket",
        gapper_age_sec=30_000.0,
    ))
    gap = next(c for c in report["checks"] if c["id"] == "scanner_gappers")
    assert gap["status"] == "warn"


def test_stale_gappers_pass_in_rth():
    report = evaluate_scanner_integrity(_base(
        current_mode="market",
        gapper_age_sec=30_000.0,
    ))
    gap = next(c for c in report["checks"] if c["id"] == "scanner_gappers")
    assert gap["status"] == "pass"
    assert "offline by design" in gap["detail"]


def test_stale_gappers_pass_in_afterhours():
    report = evaluate_scanner_integrity(_base(
        current_mode="afterhours",
        gapper_age_sec=30_000.0,
    ))
    gap = next(c for c in report["checks"] if c["id"] == "scanner_gappers")
    assert gap["status"] == "pass"


def test_stale_gainers_still_warn_in_afterhours():
    report = evaluate_scanner_integrity(_base(
        current_mode="afterhours",
        gainer_age_sec=30_000.0,
    ))
    g = next(c for c in report["checks"] if c["id"] == "scanner_gainers")
    assert g["status"] == "warn"


def test_empty_stale_gainers_warn_when_afterhours_live():
    report = evaluate_scanner_integrity(_base(
        current_mode="afterhours",
        gainer_count=0,
        gainer_age_sec=300.0,
        afterhours_count=40,
    ))
    g = next(c for c in report["checks"] if c["id"] == "scanner_gainers")
    assert g["status"] == "warn"
    assert report["status"] != "fail" or all(
        c["status"] != "fail" for c in report["checks"] if c["id"] == "scanner_gainers"
    )


def test_empty_stale_gainers_fail_in_rth():
    report = evaluate_scanner_integrity(_base(
        current_mode="market",
        gainer_count=0,
        gainer_age_sec=300.0,
        afterhours_count=0,
    ))
    g = next(c for c in report["checks"] if c["id"] == "scanner_gainers")
    assert g["status"] == "fail"


def test_empty_premarket_gappers_fail_when_ibkr_connected():
    report = evaluate_scanner_integrity(_base(
        current_mode="premarket",
        gapper_count=0,
        gapper_age_sec=40.0,
        ibkr_bridge_last_error="gappers: TimeoutError: TimeoutError()",
    ))
    gap = next(c for c in report["checks"] if c["id"] == "scanner_gappers")
    assert gap["status"] == "fail"
    assert "bridge" in gap["detail"].lower() or "0 rows" in gap["detail"]
    bridge = next(c for c in report["checks"] if c["id"] == "scanner_ibkr_bridge")
    # Gainers still fresh in base snap → bridge demotes to warn (sticky leftover).
    assert bridge["status"] == "warn"


def test_bridge_error_fails_when_gainer_cache_stale():
    report = evaluate_scanner_integrity(_base(
        current_mode="market",
        gainer_count=0,
        gainer_age_sec=300.0,
        ibkr_bridge_last_error=(
            "gainers: IbkrDiscoveryError: scanner TOP_PERC_GAIN timed out after 20s"
        ),
        ibkr_bridge_last_error_age_sec=173.0,
    ))
    bridge = next(c for c in report["checks"] if c["id"] == "scanner_ibkr_bridge")
    assert bridge["status"] == "fail"


def test_bridge_error_warns_when_gainer_cache_fresh():
    report = evaluate_scanner_integrity(_base(
        current_mode="market",
        gainer_count=40,
        gainer_age_sec=25.0,
        ibkr_bridge_last_error=(
            "gainers: IbkrDiscoveryError: scanner TOP_PERC_GAIN timed out after 20s"
        ),
        ibkr_bridge_last_error_age_sec=173.0,
    ))
    bridge = next(c for c in report["checks"] if c["id"] == "scanner_ibkr_bridge")
    assert bridge["status"] == "warn"
    assert "recovered" in bridge["detail"]
    assert report["status"] != "fail"


def test_empty_stale_losers_pass_when_gainers_live():
    report = evaluate_scanner_integrity(_base(
        current_mode="market",
        loser_count=0,
        loser_age_sec=167.0,
        gainer_count=40,
        gainer_age_sec=20.0,
    ))
    losers = next(c for c in report["checks"] if c["id"] == "scanner_losers")
    assert losers["status"] == "pass"
    assert "secondary" in losers["detail"]
    assert report["status"] != "fail"


def test_empty_stale_losers_fail_when_gainers_also_dead():
    report = evaluate_scanner_integrity(_base(
        current_mode="market",
        loser_count=0,
        loser_age_sec=300.0,
        gainer_count=0,
        gainer_age_sec=300.0,
    ))
    losers = next(c for c in report["checks"] if c["id"] == "scanner_losers")
    assert losers["status"] == "fail"
