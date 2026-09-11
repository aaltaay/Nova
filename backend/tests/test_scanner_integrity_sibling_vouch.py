"""D-028: empty tables cannot vouch for each other."""
from __future__ import annotations

from hod_momo_integrity_scanner import evaluate_scanner_integrity


def _snap(**overrides):
    base = {
        "discovery_provider": "ibkr",
        "ibkr_connected": True,
        "current_mode": "afterhours",
        "gapper_count": 0,
        "gainer_count": 0,
        "loser_count": 0,
        "afterhours_count": 0,
        "gapper_age_sec": None,
        "gainer_age_sec": None,
        "loser_age_sec": None,
        "afterhours_age_sec": None,
        "scanner_l1_event_age_sec": 1.0,
    }
    base.update(overrides)
    return base


def _check(report, check_id):
    return next(c for c in report["checks"] if c["id"] == check_id)


def test_two_empty_tables_do_not_mutual_vouch():
    report = evaluate_scanner_integrity(_snap())
    losers = _check(report, "scanner_losers")
    gainers = _check(report, "scanner_gainers")
    assert losers["status"] == "fail"
    assert "no live sibling" in losers["detail"]
    assert gainers["status"] == "fail"
    assert "OK if another scanner list is live" not in losers["detail"]
    assert "OK if another scanner list is live" not in gainers["detail"]


def test_empty_losers_pass_only_when_gainers_are_live():
    report = evaluate_scanner_integrity(_snap(
        current_mode="market",
        gainer_count=12,
        gainer_age_sec=5.0,
    ))
    losers = _check(report, "scanner_losers")
    assert losers["status"] == "pass"
    assert "gainers live" in losers["detail"]


def test_stale_gainers_do_not_vouch_for_empty_losers():
    report = evaluate_scanner_integrity(_snap(
        current_mode="market",
        gainer_count=12,
        gainer_age_sec=30_000.0,
        gainer_frozen=False,
    ))
    losers = _check(report, "scanner_losers")
    assert losers["status"] == "fail"
    assert "no live sibling" in losers["detail"]


def test_large_cap_rows_do_not_vouch_for_empty_day_trade_tables():
    report = evaluate_scanner_integrity(_snap(
        current_mode="premarket",
        large_cap_count=40,
        large_cap_age_sec=1.0,
    ))
    gappers = _check(report, "scanner_gappers")
    gainers = _check(report, "scanner_gainers")
    assert gappers["status"] == "warn"
    assert "no live sibling" in gappers["detail"]
    assert gainers["status"] == "fail"
    assert "no roster ever committed" in gainers["detail"]
