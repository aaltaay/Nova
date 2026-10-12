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


def test_a_day_is_complete_only_with_all_its_boards(tmp_path):
    """Market, Losers and Gappers over every minute, and After Hours over 16:01-20:00 -- which needs the
    session's own day file (its official close): a day built before that file landed is built again."""
    root, db = tmp_path / "massive", tmp_path / "lb.sqlite3"
    day = _day(root)
    build(root, day, {s: "CS" for s in CLOSES}, db=db)
    assert build_leaderboard.complete_days(db) == set()
    assert "afterhours" not in states_at(db, day, 16, 30)
    write_closes(root, day, {s: 1.0 for s in CLOSES})
    build(root, day, {s: "CS" for s in CLOSES}, db=db)
    assert build_leaderboard.complete_days(db) == {day.isoformat()}


# After Hours (2026-10-12): the scan's 50 biggest moves since the 16:00 close among stocks that traded after it,
# then the live list's rule (up 10% on the day, $0.50 or more) and order (the biggest move on the day first).
AH_PRIOR = {"RUNR": 2.0, "POPP": 4.0, "DAYUP": 1.0, "FLAT": 5.0, "PENNY": 0.20, "QUIET": 3.0}
AH_CLOSE = {"RUNR": 3.0, "POPP": 4.0, "DAYUP": 1.5, "FLAT": 5.0, "PENNY": 0.40, "QUIET": 3.6}


def _ah_day(root):
    prev, day = session(0), session(1)
    write_minutes(root, prev, [("FLAT", 9, 30, 5.0, 100)])
    write_closes(root, prev, AH_PRIOR)
    write_minutes(root, day, [
        ("RUNR", 10, 0, 3.0, 1_000), ("RUNR", 16, 5, 3.3, 500),     # +65% on the day, +10% after the close
        ("POPP", 10, 0, 4.0, 1_000), ("POPP", 16, 0, 4.8, 500),     # +20% on the day, all of it after the close
        ("DAYUP", 10, 0, 1.5, 1_000), ("DAYUP", 17, 0, 1.45, 500),  # +45% on the day, but down after the close
        ("FLAT", 10, 0, 5.0, 1_000), ("FLAT", 16, 30, 5.2, 500),    # +4%: up after the close, under 10% on the day
        ("PENNY", 10, 0, 0.40, 1_000), ("PENNY", 16, 10, 0.45, 500),  # +125% but under $0.50
        ("QUIET", 10, 0, 3.6, 1_000),                               # +20% on the day, no after-hours print
    ])
    write_closes(root, day, AH_CLOSE)
    return day


def test_after_hours_rebuilds_the_scan_then_the_live_lists_rule(tmp_path):
    root, db = tmp_path / "massive", tmp_path / "lb.sqlite3"
    day = _ah_day(root)
    build(root, day, {s: "CS" for s in AH_PRIOR}, db=db)

    assert "afterhours" not in states_at(db, day, 16, 0)         # the 16:00 bar has not closed
    assert _ranked(rows_at(db, day, 16, 1, "afterhours")) == ["POPP"]
    late = rows_at(db, day, 17, 30, "afterhours")
    assert _ranked(late) == ["RUNR", "POPP"]                     # the move on the day orders them
    assert late["RUNR"]["prev_close"] == 2.0 and late["RUNR"]["change_pct"] == pytest.approx(0.65)
    assert states_at(db, day, 20, 0)["afterhours"] == ("rebuilt", 2)


def test_after_hours_keeps_only_the_scans_rows(tmp_path):
    from lb_core import afterhours_rows

    rows = [{"symbol": s, "price": 10.0, "prev_close": 5.0, "change_pct": 1.0, "volume": 1.0} for s in "ABC"]
    assert [r["symbol"] for r in afterhours_rows(rows, [0.3, 0.1, 0.2], scan_rows=2)] == ["A", "C"]
    assert afterhours_rows(rows, [None, -0.1, 0.0]) == []        # no print after the close, or no gain since it
