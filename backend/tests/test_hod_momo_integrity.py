"""Tests for fail-loud HOD / scanner integrity evaluators."""
from __future__ import annotations

from hod_momo_integrity import (
    evaluate_hod_integrity,
    evaluate_scanner_integrity,
    merge_integrity,
)


def _base_hod(**overrides):
    snap = {
        "universe_size": 50,
        "active_set_size": 40,
        "active_set_capacity": 40,
        "uncovered_count": 10,
        "active_coverage_pct": 100.0,
        "active_quote_age_p95": 1.0,
        "active_quote_age_max": 2.0,
        "active_eval_age_p95": 1.0,
        "active_eval_age_max": 2.0,
        "total_trades_seen": 100,
        "last_trade_age_sec": 1.0,
        "process_uptime_sec": 300.0,
        "buffer_symbol_count": 20,
        "surge_ready_count": 15,
        "surge_seeded_count": 15,
        "pending_surge_seeds": 0,
        "surge_none_after_seed_count": 0,
        "watch_seed_size": 10,
        "discovery_provider": "ibkr",
        "snaps_with_rvol": 15,
        "snaps_tracked": 20,
        "ibkr_connected": True,
    }
    snap.update(overrides)
    return snap


def test_hod_ticks_fail_when_universe_but_no_trades():
    report = evaluate_hod_integrity(_base_hod(
        total_trades_seen=0,
        last_trade_age_sec=None,
        buffer_symbol_count=0,
        surge_ready_count=0,
        surge_seeded_count=0,
        snaps_with_rvol=0,
        snaps_tracked=0,
        active_coverage_pct=0.0,
        active_quote_age_p95=None,
        active_quote_age_max=None,
        active_eval_age_p95=None,
        active_eval_age_max=None,
    ))
    assert report["status"] == "fail"
    tick = next(c for c in report["checks"] if c["id"] == "hod_ticks_flowing")
    assert tick["status"] == "fail"


def test_hod_surge_buffer_warns_while_seed_queue_drains():
    report = evaluate_hod_integrity(_base_hod(
        surge_ready_count=2,
        surge_seeded_count=0,
        pending_surge_seeds=5,
        buffer_symbol_count=20,
    ))
    surge = next(c for c in report["checks"] if c["id"] == "hod_surge_buffer")
    assert surge["status"] == "warn"


def test_hod_surge_buffer_fails_when_cold_and_not_seeding():
    report = evaluate_hod_integrity(_base_hod(
        surge_ready_count=2,
        surge_seeded_count=0,
        pending_surge_seeds=0,
        buffer_symbol_count=20,
    ))
    surge = next(c for c in report["checks"] if c["id"] == "hod_surge_buffer")
    assert surge["status"] == "fail"


def test_hod_tick_stale_fails_when_not_second_by_second():
    report = evaluate_hod_integrity(_base_hod(last_trade_age_sec=20.0))
    tick = next(c for c in report["checks"] if c["id"] == "hod_ticks_flowing")
    assert tick["status"] == "fail"


def test_active_quote_age_fails_over_slo():
    report = evaluate_hod_integrity(_base_hod(
        active_quote_age_p95=2.5,
        active_quote_age_max=4.0,
    ))
    age = next(c for c in report["checks"] if c["id"] == "hod_active_quote_age")
    assert age["status"] == "fail"


def test_surge_none_after_seed_is_hard_fail_when_tape_dead():
    report = evaluate_hod_integrity(_base_hod(
        surge_none_after_seed_count=2,
        total_trades_seen=0,
        last_trade_age_sec=None,
    ))
    chk = next(c for c in report["checks"] if c["id"] == "hod_surge_after_seed")
    assert chk["status"] == "fail"


def test_surge_none_after_seed_warns_when_tape_alive():
    report = evaluate_hod_integrity(_base_hod(surge_none_after_seed_count=2))
    chk = next(c for c in report["checks"] if c["id"] == "hod_surge_after_seed")
    assert chk["status"] == "warn"


def test_active_coverage_98_warns_not_fails():
    """One unquoted explore admit must not hard-fail the feed (39/40→98%)."""
    report = evaluate_hod_integrity(_base_hod(active_coverage_pct=97.5))
    chk = next(c for c in report["checks"] if c["id"] == "hod_active_set")
    assert chk["status"] == "warn"
    assert report["status"] in ("pass", "warn")


def test_active_coverage_below_floor_still_fails():
    report = evaluate_hod_integrity(_base_hod(active_coverage_pct=85.0))
    chk = next(c for c in report["checks"] if c["id"] == "hod_active_set")
    assert chk["status"] == "fail"


def test_active_coverage_98_warns_not_fails():
    """Single unquoted explore admit must not hard-fail the feed."""
    report = evaluate_hod_integrity(_base_hod(active_coverage_pct=97.5))
    chk = next(c for c in report["checks"] if c["id"] == "hod_active_set")
    assert chk["status"] == "warn"
    assert report["status"] in ("pass", "warn")


def test_active_coverage_below_floor_still_fails():
    report = evaluate_hod_integrity(_base_hod(active_coverage_pct=85.0))
    chk = next(c for c in report["checks"] if c["id"] == "hod_active_set")
    assert chk["status"] == "fail"
    assert report["status"] == "fail"


def test_scanner_fails_when_ibkr_disconnected():
    report = evaluate_scanner_integrity({
        "discovery_provider": "ibkr",
        "ibkr_connected": False,
        "gapper_count": 0,
        "gainer_count": 0,
        "loser_count": 0,
        "gapper_age_sec": 10.0,
        "gainer_age_sec": 10.0,
        "loser_age_sec": 10.0,
        "scanner_l1_age_sec": 1.0,
    })
    assert report["status"] == "fail"


def test_frozen_gainer_table_passes_despite_old_age():
    """ADR 008: a session-frozen table is immutable by design — its age only
    grows because it must never be rewritten again, not because the feed is
    broken. Without the frozen bypass this would fail/warn on cache age."""
    report = evaluate_scanner_integrity({
        "discovery_provider": "ibkr",
        "ibkr_connected": True,
        "current_mode": "closed",
        "gapper_count": 0,
        "gainer_count": 12,
        "loser_count": 0,
        "gapper_age_sec": None,
        "gainer_age_sec": 30_000.0,  # far past SCANNER_INTEGRITY_CACHE_STALE_SEC
        "loser_age_sec": None,
        "gainer_frozen": True,
        "scanner_l1_age_sec": None,
    })
    chk = next(c for c in report["checks"] if c["id"] == "scanner_gainers")
    assert chk["status"] == "pass"
    assert "frozen" in chk["detail"]


def test_unfrozen_stale_gainer_table_still_warns():
    report = evaluate_scanner_integrity({
        "discovery_provider": "ibkr",
        "ibkr_connected": True,
        "current_mode": "market",
        "gapper_count": 0,
        "gainer_count": 12,
        "loser_count": 0,
        "gapper_age_sec": None,
        "gainer_age_sec": 30_000.0,
        "loser_age_sec": None,
        "gainer_frozen": False,
        "scanner_l1_age_sec": None,
    })
    chk = next(c for c in report["checks"] if c["id"] == "scanner_gainers")
    assert chk["status"] == "warn"


def test_merge_takes_worst_status():
    hod = {"scope": "hod_momo", "status": "warn", "checks": [
        {"id": "a", "status": "warn", "detail": "x"},
    ]}
    scan = {"scope": "scanner", "status": "fail", "checks": [
        {"id": "b", "status": "fail", "detail": "y"},
    ]}
    merged = merge_integrity(hod, scan)
    assert merged["status"] == "fail"
    assert merged["ok"] is False
