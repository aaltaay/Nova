"""The offline leaderboard rebuild (research/leaderboard, ADR 023): the minute
boundary, the split-adjusted prior close, the top-N-plus-presets store and its
ranks, the universe, idempotence, the S5 read-back and the independent spot check."""
from __future__ import annotations

import pytest

from tests.test_leaderboard_reconstruct_helpers import (
    build,
    rows_at,
    session,
    ts,
    write_closes,
    write_minutes,
)

import lb_io  # noqa: E402  (research/leaderboard on sys.path via the helpers)
import s5_universe  # noqa: E402
import spot_check  # noqa: E402
from leaderboard import store  # noqa: E402
from leaderboard.ranking import BOARD_RULES, rank_rows  # noqa: E402


def test_a_bar_is_used_only_once_its_window_has_closed(tmp_path):
    root, db = tmp_path / "massive", tmp_path / "lb.sqlite3"
    prev, day = session(0), session(1)
    write_minutes(root, prev, [("AAA", 9, 30, 10.0, 100)])
    write_closes(root, prev, {"AAA": 10.0, "BBB": 5.0, "ETFX": 1.0, "UNKN": 1.0})
    write_minutes(root, day, [
        ("AAA", 4, 0, 11.0, 100), ("AAA", 4, 5, 12.0, 50), ("BBB", 4, 5, 6.0, 10),
        ("ETFX", 4, 0, 9.0, 1_000_000), ("UNKN", 4, 0, 9.0, 1_000_000),
    ])
    types = {"AAA": "CS", "BBB": "ADRC", "ETFX": "ETF"}

    build(root, day, types, db=db)

    first = rows_at(db, day, 4, 1)
    assert set(first) == {"AAA"}   # an ETF and a ticker missing from the reference never rank
    assert (first["AAA"]["price"], first["AAA"]["volume"]) == (11.0, 100.0)
    at_0405 = rows_at(db, day, 4, 5)   # the 04:05 bar closes at 04:06
    assert set(at_0405) == {"AAA"}
    assert (at_0405["AAA"]["price"], at_0405["AAA"]["volume"]) == (11.0, 100.0)
    at_0406 = rows_at(db, day, 4, 6)
    assert (at_0406["AAA"]["price"], at_0406["AAA"]["volume"]) == (12.0, 150.0)
    assert at_0406["BBB"]["change_pct"] == pytest.approx(0.2)
    assert at_0406["AAA"]["exchange"] == "NASDAQ"
    assert at_0406["AAA"]["market_cap"] is None and at_0406["AAA"]["float_shares"] is None

    with store.connect(db) as con:
        minutes = store.coverage_minutes(con, day.isoformat(), "reconstructed")
        count = con.execute("SELECT COUNT(*) FROM rows").fetchone()[0]
        cov = store.coverage_at(con, day.isoformat(), "reconstructed", ts(day, 4, 6))
    assert len(minutes) == 960 and minutes[0] == ts(day, 4, 1) and minutes[-1] == ts(day, 20, 0)
    assert cov == [{"board": "market", "state": "rebuilt", "row_count": 2, "run_id": None}]

    build(root, day, types, db=db)   # idempotent: the day is replaced, not appended
    with store.connect(db) as con:
        assert con.execute("SELECT COUNT(*) FROM rows").fetchone()[0] == count


def test_the_prior_close_is_split_adjusted_on_the_execution_date(tmp_path):
    root, db = tmp_path / "massive", tmp_path / "lb.sqlite3"
    prev, day = session(0), session(1)
    write_minutes(root, prev, [("RSX", 9, 30, 0.08, 1000), ("FWD", 9, 30, 100.0, 10), ("OLD", 9, 30, 4.0, 10)])
    # Unadjusted: RSX closed at 0.08 before its 1-for-23 reverse split, FWD at 100 before a 2-for-1.
    write_closes(root, prev, {"RSX": 0.08, "FWD": 100.0, "OLD": 4.0})
    write_minutes(root, day, [("RSX", 7, 0, 1.75, 500), ("FWD", 7, 0, 52.0, 10), ("OLD", 7, 0, 4.4, 10)])
    splits = [
        lb_io.Split("RSX", day, 23.0, 1.0),
        lb_io.Split("FWD", day, 1.0, 2.0),
        lb_io.Split("OLD", prev, 10.0, 1.0),   # already in the prior session's own close
    ]

    build(root, day, {"RSX": "CS", "FWD": "CS", "OLD": "CS"}, db=db, splits=splits)

    rows = rows_at(db, day, 7, 1)
    assert rows["RSX"]["prev_close"] == pytest.approx(0.08 * 23)
    assert rows["RSX"]["change_pct"] == pytest.approx(1.75 / (0.08 * 23) - 1)   # -4.9%, not +2088%
    assert rows["FWD"]["prev_close"] == pytest.approx(50.0)
    assert rows["FWD"]["change_pct"] == pytest.approx(0.04)
    assert rows["OLD"]["prev_close"] == pytest.approx(4.0)

    # The independent pandas path of spot_check.py agrees row for row.
    split_dicts = [{"ticker": s.ticker, "execution_date": s.execution_date.isoformat(),
                    "split_from": s.split_from, "split_to": s.split_to} for s in splits]
    minutes = spot_check.load_minutes(spot_check.day_file(root, "minute_aggs_v1", day), {"RSX", "FWD", "OLD"})
    closes = spot_check.prior_closes(spot_check.day_file(root, "day_aggs_v1", prev), split_dicts, prev, day)
    board = spot_check.independent_board(minutes, closes, ts(day, 4, 0), ts(day, 7, 1))
    counts, problems = spot_check.compare(sorted(rows.values(), key=lambda r: r["rank"]), board)
    assert problems == [] and counts["rank"] == counts["change"] == 3


def _preset_day(root):
    """Twelve prior sessions; S5X printed 100 shares at 04:00 in each, nobody else did."""
    for i in range(12):
        write_minutes(root, session(i), [("S5X", 4, 0, 10.0, 100)])
    prev, day = session(11), session(12)
    write_closes(root, prev, {s: 10.0 for s in ("G1", "G2", "G3", "S5X")} | {"FLT": 6.0, "LDR": 4.76})
    write_minutes(root, day, [
        ("G1", 4, 0, 50.0, 10), ("G2", 4, 0, 40.0, 10), ("G3", 4, 0, 30.0, 10),   # +400/300/200%, > $10
        ("FLT", 4, 0, 6.6, 200_000),           # +10% at $6.60, but a 50M float
        ("LDR", 4, 0, 5.0, 200_000),           # +5%, $5, 200k shares, float unknown -> the leader
        ("S5X", 4, 0, 10.2, 1000),             # +2%, 10x its time-of-day volume -> S5
    ])
    return day


def test_top_n_keeps_every_leaders_and_s5_pick_with_its_board_rank(tmp_path):
    root = tmp_path / "massive"
    day = _preset_day(root)
    types = {s: "CS" for s in ("G1", "G2", "G3", "FLT", "LDR", "S5X")}
    floats = {"FLT": 50_000_000.0}
    full_db, small_db = tmp_path / "full.sqlite3", tmp_path / "small.sqlite3"

    build(root, day, types, db=full_db, floats=floats, top_n=100)
    build(root, day, types, db=small_db, floats=floats, top_n=2)

    full = rows_at(full_db, day, 4, 1)
    small = rows_at(small_db, day, 4, 1)
    assert set(full) == set(types)
    assert set(small) == {"G1", "G2", "LDR", "S5X"}   # top 2 + the LEADERS pick + the S5 pick
    assert {s: r["rank"] for s, r in small.items()} == {s: full[s]["rank"] for s in small}
    assert (small["LDR"]["rank"], small["S5X"]["rank"]) == (5, 6)
    assert small["S5X"]["rvol"] == pytest.approx(10.0) and small["S5X"]["rvol_basis"] == "time_of_day_20"
    assert small["LDR"]["rvol"] is None and small["LDR"]["rvol_basis"] is None
    assert full["FLT"]["float_shares"] == 50_000_000.0

    # Stored ranks are rank_rows(..., BOARD_RULES) over the whole market at that minute.
    unranked = [{k: v for k, v in row.items() if k != "rank"} for row in full.values()]
    assert {r["symbol"]: r["rank"] for r in rank_rows(unranked, BOARD_RULES)} == {
        s: r["rank"] for s, r in full.items()
    }

    with store.connect(small_db) as con:
        picks = dict(s5_universe.s5_by_minute(con, day.isoformat()))
    assert picks[ts(day, 4, 1)] == ["S5X"]
    assert len(picks) == 960
