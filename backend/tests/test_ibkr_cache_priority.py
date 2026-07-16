"""Regression test for _find_ibkr_cache_row's gainer/loser-over-gapper priority.

_find_ibkr_cache_row was extracted to ticker.py (Phase 1 modularisation).
It reads the explicit scanner runtime-state owner.

See PROBLEM_LOG 2026-07-13 ("ticker detail stuck on premarket gapper
snapshot"): gappers stop refreshing once the market opens, so a symbol
tracked in both the gapper and gainer/loser cache must resolve to the live
gainer/loser row, not the frozen gapper one.
"""
import sys
import os

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from runtime_state import ScannerRuntimeState, set_runtime_state_for_testing  # noqa: E402
import ticker  # noqa: E402


@pytest.fixture
def state():
    current = ScannerRuntimeState()
    previous = set_runtime_state_for_testing(current)
    yield current
    set_runtime_state_for_testing(previous)


def test_prefers_gainer_row_over_stale_gapper_row(state):
    state.gapper_cache = [{"symbol": "VEEE", "price": 12.01, "prev_close": 4.34, "volume": 304}]
    state.gainer_cache = [{"symbol": "VEEE", "price": 25.05, "prev_close": 4.82, "volume": 69737457}]
    state.loser_cache = []

    row = ticker._find_ibkr_cache_row("VEEE")

    assert row is not None
    assert row["price"] == 25.05
    assert row["prev_close"] == 4.82


def test_prefers_loser_row_over_stale_gapper_row(state):
    state.gapper_cache = [{"symbol": "XYZ", "price": 1.0, "prev_close": 2.0, "volume": 10}]
    state.gainer_cache = []
    state.loser_cache = [{"symbol": "XYZ", "price": 0.5, "prev_close": 2.0, "volume": 999}]

    row = ticker._find_ibkr_cache_row("XYZ")

    assert row is not None
    assert row["price"] == 0.5


def test_falls_back_to_gapper_row_when_symbol_not_a_mover(state):
    state.gapper_cache = [{"symbol": "ABC", "price": 3.0, "prev_close": 1.0, "volume": 500}]
    state.gainer_cache = []
    state.loser_cache = []

    row = ticker._find_ibkr_cache_row("ABC")

    assert row is not None
    assert row["price"] == 3.0


def test_returns_none_when_symbol_in_no_cache(state):
    state.gapper_cache = []
    state.gainer_cache = []
    state.loser_cache = []

    assert ticker._find_ibkr_cache_row("NOPE") is None
