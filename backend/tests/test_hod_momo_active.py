"""Tests for the ADR 008 deterministic HOD active-set admission.

HOD eligibility is exactly: manual Former Momo first (guaranteed), then a
round-robin across ranked Gappers/Gainers/Afterhours. No seeds, no open-
ticker priority, no Losers, no rotating "explore" tail.
"""
from __future__ import annotations

import inspect

import hod_momo_active as active


def test_former_momo_always_admitted_first():
    active.clear_session_state()
    gainers = [{"symbol": f"G{i:02d}", "change_pct": 50 - i} for i in range(40)]
    snap = active.build_active_set(
        gainer_rows=gainers,
        priority_symbols=["LBGJ", "BIYA"],
        capacity=40,
    )
    assert "LBGJ" in snap.active
    assert "BIYA" in snap.active
    assert snap.reasons.get("LBGJ") == "former_momo"
    assert snap.active[0] == "LBGJ"
    assert snap.active[1] == "BIYA"


def test_round_robin_across_gapper_gainer_afterhours():
    active.clear_session_state()
    gappers = [{"symbol": "GAP1", "gap_percent": 0.5}, {"symbol": "GAP2", "gap_percent": 0.4}]
    gainers = [{"symbol": "GAIN1", "change_pct": 0.6}, {"symbol": "GAIN2", "change_pct": 0.3}]
    afterhours = [{"symbol": "AH1", "change_pct": 0.7}]
    snap = active.build_active_set(
        gapper_rows=gappers,
        gainer_rows=gainers,
        afterhours_rows=afterhours,
        capacity=5,
    )
    # Every category's top-ranked symbol wins a slot before any category's
    # second-ranked symbol — no single table can monopolize the set.
    assert set(snap.active) == {"GAP1", "GAIN1", "AH1", "GAP2", "GAIN2"}
    assert snap.active.index("GAP1") < snap.active.index("GAP2")
    assert snap.active.index("GAIN1") < snap.active.index("GAIN2")


def test_capacity_bounds_admission_and_marks_uncovered():
    active.clear_session_state()
    gainers = [{"symbol": f"S{i:03d}", "change_pct": 80 - i} for i in range(80)]
    snap = active.build_active_set(gainer_rows=gainers, capacity=40)
    assert len(snap.active) == 40
    assert len(snap.uncovered) >= 1
    assert all(s not in snap.active for s in snap.uncovered)
    # Hottest-ranked gainers win the bounded slots.
    assert "S000" in snap.active
    assert "S079" not in snap.active


def test_losers_seeds_and_explore_have_no_admission_path():
    """build_active_set has no loser/seed/detail/discovery parameter at all
    (ADR 008) — there is no way for those categories to reach HOD."""
    params = set(inspect.signature(active.build_active_set).parameters)
    for retired in (
        "loser_rows", "seed_symbols", "detail_symbols", "discovery",
    ):
        assert retired not in params


def test_no_symbol_admitted_twice_across_categories():
    active.clear_session_state()
    # AAA appears on both the gapper and gainer tables.
    gappers = [{"symbol": "AAA", "gap_percent": 0.5}]
    gainers = [{"symbol": "AAA", "change_pct": 0.5}, {"symbol": "BBB", "change_pct": 0.4}]
    snap = active.build_active_set(gapper_rows=gappers, gainer_rows=gainers, capacity=5)
    assert snap.active.count("AAA") == 1
    assert "BBB" in snap.active


def test_select_fair_batch_keeps_hot_every_tick():
    active.clear_session_state()
    symbols = [f"S{i:02d}" for i in range(40)]
    active.build_active_set(gainer_rows=[{"symbol": s, "change_pct": 1} for s in symbols], capacity=40)
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
    active.build_active_set(
        gainer_rows=[{"symbol": "AAA", "change_pct": 1}, {"symbol": "BBB", "change_pct": 1}],
        capacity=2,
    )
    now = 5000.0
    active.note_quote("AAA", now - 0.5)
    active.note_evaluation("AAA", now - 0.5)
    active.note_quote("BBB", now - 10.0)
    active.note_evaluation("BBB", now - 10.0)
    pct = active.coverage_pct(["AAA", "BBB"], now=now)
    assert pct == 50.0


def test_merge_prefers_active_then_fills_scanner():
    merged = active.merge_with_scanner_chunk(
        ["A", "B", "C"],
        ["C", "D", "E", "F"],
        chunk_size=4,
    )
    assert merged == ["A", "B", "C", "D"]


def test_l1_subscribe_fail_excludes_symbol_from_admission():
    active.clear_session_state()
    # cooldown measured from "now" — must stay in the future relative to the
    # real wall clock build_active_set's internal blocked-check uses.
    active.note_l1_subscribe_failed(["FRE"], cooldown_sec=600.0)
    snap = active.build_active_set(
        gainer_rows=[{"symbol": "FRE", "change_pct": 5}, {"symbol": "AAA", "change_pct": 1}],
        capacity=2,
    )
    assert "FRE" not in snap.active
    assert "AAA" in snap.active


def test_demoted_active_symbol_clears_stale_quote_age():
    active.clear_session_state()
    active.build_active_set(
        gainer_rows=[{"symbol": "AAA", "change_pct": 2}, {"symbol": "BBB", "change_pct": 1}],
        capacity=2,
    )
    active.note_quote("AAA", ts=1000.0)
    active.note_evaluation("AAA", ts=1000.0)
    active.build_active_set(
        gainer_rows=[{"symbol": "BBB", "change_pct": 2}, {"symbol": "CCC", "change_pct": 1}],
        capacity=2,
    )
    assert active.quote_age_sec("AAA", now=5000.0) is None
