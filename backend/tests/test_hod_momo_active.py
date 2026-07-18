"""Tests for capacity-bounded active set + fair reprice scheduler."""
from __future__ import annotations

import hod_momo_active as active


def test_build_active_set_caps_and_marks_uncovered():
    discovery = [f"S{i:03d}" for i in range(80)]
    gainers = [{"symbol": f"S{i:03d}", "change_pct": 50 - i} for i in range(30)]
    snap = active.build_active_set(
        discovery=discovery,
        gainer_rows=gainers,
        detail_symbols=["OPEN"],
        capacity=40,
    )
    assert "OPEN" in snap.active
    assert len(snap.active) == 40
    assert len(snap.uncovered) >= 1
    assert all(s not in snap.active for s in snap.uncovered)
    assert snap.reasons.get("OPEN") == "open_ticker"


def test_select_fair_batch_keeps_hot_every_tick():
    active.clear_session_state()
    symbols = [f"S{i:02d}" for i in range(40)]
    active.build_active_set(discovery=symbols, capacity=40)
    for i, sym in enumerate(symbols):
        active.note_quote(sym, ts=1000.0 + i)

    batch1 = active.select_fair_batch(
        symbols, hot=["S00", "S01"], chunk_size=20, hot_n=10, now=2000.0,
    )
    assert "S00" in batch1
    assert "S01" in batch1
    assert len(batch1) == 20

    batch2 = active.select_fair_batch(
        symbols, hot=["S00", "S01"], chunk_size=20, hot_n=10, now=2001.0,
    )
    assert "S00" in batch2
    assert "S01" in batch2


def test_coverage_requires_recent_quote_and_eval():
    active.clear_session_state()
    symbols = ["AAA", "BBB"]
    active.build_active_set(discovery=symbols, capacity=2)
    now = 5000.0
    active.note_quote("AAA", now - 0.5)
    active.note_evaluation("AAA", now - 0.5)
    active.note_quote("BBB", now - 10.0)
    active.note_evaluation("BBB", now - 10.0)
    pct = active.coverage_pct(symbols, now=now)
    assert pct == 50.0


def test_merge_prefers_active_then_fills_scanner():
    merged = active.merge_with_scanner_chunk(
        ["A", "B", "C"],
        ["C", "D", "E", "F"],
        chunk_size=4,
    )
    assert merged == ["A", "B", "C", "D"]


def test_l1_subscribe_fail_skips_explore_but_keeps_open_ticker():
    active.clear_session_state()
    active.note_l1_subscribe_failed(["FRE"], cooldown_sec=600.0, now=1000.0)
    snap = active.build_active_set(
        discovery=["FRE", "AAA", "BBB"],
        detail_symbols=["FRE"],
        capacity=3,
    )
    assert "FRE" in snap.active
    assert snap.reasons.get("FRE") == "open_ticker"

    snap2 = active.build_active_set(
        discovery=["FRE", "AAA", "BBB"],
        capacity=2,
    )
    assert "FRE" not in snap2.active
    assert "AAA" in snap2.active


def test_demoted_active_symbol_clears_stale_quote_age():
    active.clear_session_state()
    active.build_active_set(discovery=["AAA", "BBB"], capacity=2)
    active.note_quote("AAA", ts=1000.0)
    active.note_evaluation("AAA", ts=1000.0)
    active.build_active_set(discovery=["BBB", "CCC"], capacity=2)
    assert active.quote_age_sec("AAA", now=5000.0) is None
