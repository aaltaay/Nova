"""Tests for Ross-style HOD Momo focus universe + subscribe chunking."""
from __future__ import annotations

import pytest

from hod_momo_universe import (
    build_focus_universe,
    chunk_symbols,
    discovery_for_active,
    get_seed_symbols,
    seed_symbols_for_active,
    set_seed_symbols,
    under20_gainer_symbols,
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
    assert get_seed_symbols() == ["TSSI", "YG", "FRE"]
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


def test_under20_gainer_symbols_ranks_hottest_below_cap():
    rows = [
        {"symbol": "HI", "price": 25.0, "change_pct": 0.9},
        {"symbol": "PN", "price": 4.4, "change_pct": 0.14},
        {"symbol": "HOT", "price": 3.0, "change_pct": 0.55},
        {"symbol": "MID", "price": 8.0, "change_pct": 0.20},
    ]
    assert under20_gainer_symbols(rows, below_price=20.0) == ["HOT", "MID", "PN"]


def test_seed_symbols_for_active_puts_under20_gainers_before_volume():
    gainers = [
        {"symbol": "PN", "price": 4.4, "change_pct": 0.14},
        {"symbol": "HOT", "price": 2.0, "change_pct": 0.40},
    ]
    seeds = seed_symbols_for_active(
        ["VOL1", "VOL2", "HOT"],
        gainers,
        below_price=20.0,
    )
    assert seeds[:3] == ["HOT", "PN", "VOL1"]
    assert "VOL2" in seeds


def test_discovery_for_active_prefers_hottest_gainers():
    ordered = discovery_for_active(
        ["ZZZ", "PN", "AAA"],
        [
            {"symbol": "PN", "change_pct": 0.14},
            {"symbol": "HOT", "change_pct": 0.50},
        ],
    )
    assert ordered[:2] == ["HOT", "PN"]
    assert "ZZZ" in ordered
