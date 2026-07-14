"""Tests for Ross-style HOD Momo focus universe + subscribe chunking."""
from __future__ import annotations

import pytest

from hod_momo_universe import (
    build_focus_universe,
    chunk_symbols,
    get_seed_symbols,
    set_seed_symbols,
)


def test_build_focus_universe_unions_scanner_rows_and_detail():
    blocked = {"ZZZZ"}
    set_seed_symbols([])
    result = build_focus_universe(
        gapper_rows=[{"symbol": "AAA"}, {"symbol": "zzzz"}],
        gainer_rows=[{"symbol": "bbb"}, {"symbol": "CCC"}],
        loser_rows=[{"symbol": "DDD"}],
        afterhours_rows=[{"symbol": "EEE"}],
        detail_symbols=["FFF", "zzzz"],  # blocked detail still kept
        is_blocked=lambda s: s.upper() in blocked,
    )
    assert result == {"AAA", "BBB", "CCC", "DDD", "EEE", "FFF", "ZZZZ"}


def test_build_focus_universe_merges_volume_seeds():
    set_seed_symbols(["TSSI", "yg", "FRE"])
    result = build_focus_universe(
        gainer_rows=[{"symbol": "NXTC"}],
        is_blocked=lambda _s: False,
    )
    assert result == {"NXTC", "TSSI", "YG", "FRE"}
    assert get_seed_symbols() == {"TSSI", "YG", "FRE"}
    set_seed_symbols([])


def test_build_focus_universe_empty_inputs():
    set_seed_symbols([])
    assert build_focus_universe() == set()


def test_chunk_symbols_batches_and_dedupes():
    chunks = chunk_symbols(["b", "a", "a", "c", ""], chunk_size=2)
    assert chunks == [["A", "B"], ["C"]]


def test_chunk_symbols_rejects_nonpositive_size():
    with pytest.raises(ValueError):
        chunk_symbols(["A"], chunk_size=0)
