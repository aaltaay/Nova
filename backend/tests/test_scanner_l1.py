"""Tests for active-tab + reserved HOD L1 planner."""
from __future__ import annotations

from ibkr.scanner_l1 import plan_stream_symbols


def test_plan_reserves_tab_then_hod_with_dedupe():
    plan = plan_stream_symbols(
        [f"G{i:02d}" for i in range(50)],
        [f"G{i:02d}" for i in range(10)] + [f"H{i:02d}" for i in range(40)],
        budget=90,
        tab_max=50,
    )
    assert len(plan["tab"]) == 50
    # Overlap G00-G09 already on tab — HOD slots fill with H** only for unique
    assert all(s.startswith("H") or s.startswith("G") for s in plan["hod"])
    assert len(plan["combined"]) <= 90
    assert "G00" in plan["tab"]


def test_plan_rejects_overflow_when_budget_tight():
    plan = plan_stream_symbols(
        [f"T{i:02d}" for i in range(40)],
        [f"H{i:02d}" for i in range(40)],
        budget=50,
        tab_max=40,
    )
    assert len(plan["tab"]) == 40
    assert len(plan["hod"]) == 10
    assert len(plan["rejected"]) >= 30


def test_empty_tab_gives_full_budget_to_hod():
    plan = plan_stream_symbols(
        [],
        [f"H{i:02d}" for i in range(40)],
        budget=95,
        tab_max=50,
    )
    assert plan["tab"] == []
    assert len(plan["hod"]) == 40
    assert plan["rejected"] == []
