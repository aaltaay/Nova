"""The one leaderboard ranking and the row builder (ADR 022) -- pure."""
from __future__ import annotations

import math

import pytest

from constants_leaderboard import LEADERBOARD_RVOL_BASIS_DAILY, LEADERBOARD_RVOL_BASIS_TOD
from leaderboard.ranking import BOARD_RULES, LEADERS_RULES, S5_RULES, RankingRules, leader_symbols, rank_rows, refusal
from leaderboard.rows import from_desk_row, make_row

MINUTE = 1_790_000_040  # a whole minute


def row(symbol, change, price=5.0, volume=500_000, float_shares=None, rvol=None, basis=None):
    return {"symbol": symbol, "change_pct": change, "price": price, "volume": volume,
            "float_shares": float_shares, "rvol": rvol, "rvol_basis": basis}


def test_board_orders_by_change_then_volume_then_symbol_and_keeps_unknowns_last():
    rows = [row("B", 0.5, volume=10), row("A", 0.5, volume=10), row("C", 0.9), row("D", None), row("E", 0.5, volume=99)]
    assert [r["symbol"] for r in rank_rows(rows, BOARD_RULES)] == ["C", "E", "A", "B", "D"]
    assert [r["rank"] for r in rank_rows(rows)] == [1, 2, 3, 4, 5]


def test_one_row_per_symbol_keeps_the_better_one():
    ranked = rank_rows([row("A", 0.1), row("a", 0.4)])
    assert [(r["symbol"], r["change_pct"]) for r in ranked] == [("a", 0.4)]


def test_leaders_rules_price_float_volume_and_top_three():
    rows = [
        row("CHEAP", 2.0, price=2.5),
        row("PRICEY", 1.9, price=12.0),
        row("BIGFLOAT", 1.8, float_shares=50_000_000),
        row("THIN", 1.7, volume=5_000),
        row("OK1", 1.6, float_shares=4_000_000),
        row("UNKNOWNFLOAT", 1.5),
        row("OK2", 1.4, float_shares=9_000_000),
        row("OK3", 1.3),
    ]
    assert leader_symbols(rows, LEADERS_RULES) == ["OK1", "UNKNOWNFLOAT", "OK2"]
    assert refusal(rows[0], LEADERS_RULES) == "price"
    assert refusal(rows[2], LEADERS_RULES) == "float"
    assert refusal(rows[3], LEADERS_RULES) == "volume"


def test_a_value_a_rule_needs_is_never_read_as_a_pass():
    strict = RankingRules(max_float=10_000_000, float_unknown_ok=False)
    assert refusal(row("X", 0.3), strict) == "float_unknown"
    assert refusal(row("X", 0.3, price=None), LEADERS_RULES) == "price_unknown"
    assert refusal(row("X", None), LEADERS_RULES) == "change_unknown"
    assert refusal(row("X", 0.3, volume=None), LEADERS_RULES) == "volume_unknown"


def test_s5_never_compares_rvol_across_bases():
    rows = [
        row("DAILY", 0.9, rvol=40.0, basis=LEADERBOARD_RVOL_BASIS_DAILY),
        row("TOD", 0.5, rvol=6.0, basis=LEADERBOARD_RVOL_BASIS_TOD),
        row("WEAK", 0.8, rvol=2.0, basis=LEADERBOARD_RVOL_BASIS_TOD),
        row("NONE", 0.7),
    ]
    assert leader_symbols(rows, S5_RULES) == ["TOD"]
    assert refusal(rows[0], S5_RULES) == "rvol_basis"
    assert refusal(rows[3], S5_RULES) == "rvol_unknown"


def test_make_row_computes_change_and_keeps_unknowns_null():
    r = make_row(symbol="abc", minute_ts=MINUTE, board="market", source="reconstructed", rank=1,
                 price=6.0, prev_close=4.0, volume=math.nan, float_shares=0, has_news=None)
    assert r["symbol"] == "ABC" and r["change_pct"] == pytest.approx(0.5)
    assert r["volume"] is None and r["float_shares"] is None and r["has_news"] is None
    assert make_row(symbol="X", minute_ts=MINUTE, board="market", source="reconstructed", rank=1,
                    price=6.0)["change_pct"] is None


@pytest.mark.parametrize("kwargs", [
    {"board": "nope"}, {"source": "guessed"}, {"minute_ts": MINUTE + 1}, {"symbol": " "},
    {"rvol": 3.0}, {"rvol": 3.0, "rvol_basis": "made_up"},
])
def test_make_row_refuses_what_it_cannot_vouch_for(kwargs):
    base = {"symbol": "X", "minute_ts": MINUTE, "board": "market", "source": "reconstructed", "rank": 1}
    with pytest.raises(ValueError):
        make_row(**{**base, **kwargs})


def test_a_close_fallback_row_records_no_price():
    desk = {"symbol": "zz", "price": 2.0, "prev_close": 2.0, "quote_quality": "close_fallback",
            "rel_volume": 3.0, "float": 5e6, "has_news": True, "gap_percent": 0.1}
    r = from_desk_row(desk, minute_ts=MINUTE, board="gainers", rank=4)
    assert r["price"] is None and r["change_pct"] is None and r["prev_close"] == 2.0
    assert r["rvol"] == 3.0 and r["rvol_basis"] == LEADERBOARD_RVOL_BASIS_DAILY
    assert (r["float_shares"], r["has_news"], r["rank"], r["source"]) == (5e6, True, 4, "recorded")


def test_change_is_never_copied_from_the_gap():
    desk = {"symbol": "TOPS", "price": 1.21, "prev_close": 0.712, "change_pct": 0.0534, "gap_percent": 0.0534}
    r = from_desk_row(desk, minute_ts=MINUTE, board="afterhours", rank=1)
    assert r["change_pct"] == pytest.approx((1.21 - 0.712) / 0.712)
    assert r["gap_pct"] == pytest.approx(0.0534)
