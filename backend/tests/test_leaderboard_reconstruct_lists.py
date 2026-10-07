"""A rebuilt day's Losers and Gappers (ADR 023 amendment 2026-10-06): the rebuild
writes them beside the whole-market board, Gappers by the live premarket rule and
frozen at 09:30 as the live list is, and a day counts complete only with all three."""
from __future__ import annotations

import pytest

from tests.test_leaderboard_reconstruct_helpers import (
    build,
    rows_at,
    session,
    states_at,
    write_closes,
    write_minutes,
)

import build_leaderboard  # noqa: E402  (research/leaderboard on sys.path via the helpers)

CLOSES = {
    "GAPA": 10.0,   # +20% premarket, then under the prior close after the open
    "GAPB": 5.0,    # exactly +10%: the live floor is inclusive
    "NEAR": 3.0,    # +9.99...%: under the floor
    "CHEAP": 0.30,  # +50% but under $0.50
    "DROPA": 10.0,  # -20%
    "DROPB": 8.0,   # -5%
    "FLAT": 5.0,    # unchanged: neither a gapper nor a loser
    "LATE": 2.0,    # +50%, but only after the 09:30 freeze
}


def _day(root):
    prev, day = session(0), session(1)
    write_minutes(root, prev, [("FLAT", 9, 30, 5.0, 100)])
    write_closes(root, prev, CLOSES)
    write_minutes(root, day, [
        ("GAPA", 7, 0, 12.0, 1_000), ("GAPA", 9, 40, 9.0, 1_000),
        ("GAPB", 7, 0, 5.5, 1_000), ("NEAR", 7, 0, 3.3, 1_000), ("CHEAP", 7, 0, 0.45, 1_000),
        ("DROPA", 7, 0, 8.0, 1_000), ("DROPB", 7, 0, 7.6, 1_000), ("FLAT", 7, 0, 5.0, 1_000),
        ("LATE", 9, 35, 3.0, 1_000),
    ])
    return day


def _ranked(board: dict[str, dict]) -> list[str]:
    return [symbol for symbol, _ in sorted(board.items(), key=lambda item: item[1]["rank"])]


def test_premarket_gappers_follow_the_live_rule_and_losers_the_worst_first(tmp_path):
    root, db = tmp_path / "massive", tmp_path / "lb.sqlite3"
    day = _day(root)
    build(root, day, {s: "CS" for s in CLOSES}, db=db)

    gappers = rows_at(db, day, 7, 1, "gappers")
    assert _ranked(gappers) == ["GAPA", "GAPB"]          # NEAR under 10%, CHEAP under $0.50
    assert [gappers[s]["rank"] for s in ("GAPA", "GAPB")] == [1, 2]
    assert gappers["GAPA"]["gap_pct"] == pytest.approx(0.2)   # the move, as on the live list
    assert gappers["GAPB"]["change_pct"] == pytest.approx(0.1)

    losers = rows_at(db, day, 7, 1, "losers")
    assert _ranked(losers) == ["DROPA", "DROPB"]          # FLAT is no loser
    assert losers["DROPA"]["rank"] == 1 and losers["DROPA"]["change_pct"] == pytest.approx(-0.2)

    assert set(rows_at(db, day, 7, 1)) == set(CLOSES) - {"LATE"}   # the market board as before
    assert states_at(db, day, 7, 1) == {"gappers": ("rebuilt", 2), "losers": ("rebuilt", 2), "market": ("rebuilt", 7)}
    # Before anything printed every board still answers for its minute: empty, not unbuilt.
    assert states_at(db, day, 4, 1) == {"gappers": ("rebuilt", 0), "losers": ("rebuilt", 0), "market": ("rebuilt", 0)}


def test_gappers_freeze_at_0930_and_reprice_their_members(tmp_path):
    root, db = tmp_path / "massive", tmp_path / "lb.sqlite3"
    day = _day(root)
    build(root, day, {s: "CS" for s in CLOSES}, db=db)

    assert states_at(db, day, 9, 29)["gappers"] == ("rebuilt", 2)
    assert states_at(db, day, 9, 30)["gappers"] == ("frozen", 2)
    assert _ranked(rows_at(db, day, 9, 30, "gappers")) == ["GAPA", "GAPB"]

    late = rows_at(db, day, 9, 45, "gappers")
    assert states_at(db, day, 9, 45)["gappers"] == ("frozen", 2)
    assert _ranked(late) == ["GAPA", "GAPB"]              # LATE gapped after the freeze: not added
    assert late["GAPA"]["rank"] == 1                      # the 09:30 order, though GAPA is now down
    assert late["GAPA"]["price"] == 9.0 and late["GAPA"]["gap_pct"] == pytest.approx(-0.1)
    assert rows_at(db, day, 9, 45)["LATE"]["change_pct"] == pytest.approx(0.5)   # the market board still sees it
    assert _ranked(rows_at(db, day, 9, 45, "losers")) == ["DROPA", "GAPA", "DROPB"]
    assert _ranked(rows_at(db, day, 20, 0, "gappers")) == ["GAPA", "GAPB"]


def test_losers_keep_the_top_n_like_the_board(tmp_path):
    root, db = tmp_path / "massive", tmp_path / "lb.sqlite3"
    day = _day(root)
    build(root, day, {s: "CS" for s in CLOSES}, db=db, top_n=1)

    assert _ranked(rows_at(db, day, 7, 1, "losers")) == ["DROPA"]
    assert _ranked(rows_at(db, day, 7, 1, "gappers")) == ["GAPA"]


def test_a_day_is_complete_only_with_all_three_boards(tmp_path):
    root, db = tmp_path / "massive", tmp_path / "lb.sqlite3"
    day = _day(root)
    build(root, day, {s: "CS" for s in CLOSES}, db=db)
    assert build_leaderboard.complete_days(db) == {day.isoformat()}
