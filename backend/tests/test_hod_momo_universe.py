"""Tests for the ADR 008 HOD Momo watch universe (Gappers ∪ Gainers ∪
Afterhours ∪ Former Momo — no seeds, no Losers, no open-ticker priority)."""
from __future__ import annotations

import pytest

from hod_momo_universe import build_focus_universe, chunk_symbols


def test_build_focus_universe_unions_scanner_rows_and_extras():
    blocked = {"ZZZZ"}
    result = build_focus_universe(
        gapper_rows=[{"symbol": "AAA"}, {"symbol": "zzzz"}],
        gainer_rows=[{"symbol": "bbb"}, {"symbol": "CCC"}],
        afterhours_rows=[{"symbol": "EEE"}],
        extra_symbols=["FFF", "zzzz"],  # blocked extra is filtered too
        is_blocked=lambda s: s.upper() in blocked,
    )
    assert result == {"AAA", "BBB", "CCC", "EEE", "FFF"}


def test_build_focus_universe_has_no_loser_or_detail_or_seed_inputs():
    import inspect

    params = set(inspect.signature(build_focus_universe).parameters)
    for retired in ("loser_rows", "detail_symbols"):
        assert retired not in params


def test_build_focus_universe_empty_inputs():
    assert build_focus_universe() == set()


def test_chunk_symbols_batches_and_dedupes():
    chunks = chunk_symbols(["b", "a", "a", "c", ""], chunk_size=2)
    assert chunks == [["A", "B"], ["C"]]


def test_chunk_symbols_rejects_nonpositive_size():
    with pytest.raises(ValueError):
        chunk_symbols(["A"], chunk_size=0)
