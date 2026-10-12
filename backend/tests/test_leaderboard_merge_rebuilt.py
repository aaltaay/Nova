"""Rebuilt days copied from a staging store into the leaderboard store in short transactions (2026-10-12):
the live recorder loses a batch it cannot write within the store's lock timeout, so a ten-year rebuild
builds into staging stores and ``merge_rebuilt`` copies each finished day a few minutes at a time."""
from __future__ import annotations

import sqlite3

from tests.test_leaderboard_reconstruct_helpers import build, rows_at, session, states_at, write_closes, write_minutes

import build_leaderboard  # noqa: E402  (research/leaderboard on sys.path via the helpers)
import merge_rebuilt  # noqa: E402


def _day(root, price):
    prev, day = session(0), session(1)
    write_closes(root, prev, {"AAA": 1.0, "BBB": 2.0})
    write_minutes(root, prev, [("AAA", 9, 30, 1.0, 100)])
    write_minutes(root, day, [("AAA", 9, 30, price, 1_000), ("BBB", 16, 10, 2.6, 500)])
    write_closes(root, day, {"AAA": price, "BBB": 2.2})
    return day


def test_a_finished_day_is_copied_whole_and_replaces_an_older_rebuild(tmp_path):
    root, live, stage = tmp_path / "massive", tmp_path / "live.sqlite3", tmp_path / "stage.sqlite3"
    day = _day(root, 1.5)
    build(root, day, {"AAA": "CS", "BBB": "CS"}, db=live)              # an older rebuild already in the store
    assert rows_at(live, day, 10, 0)["AAA"]["price"] == 1.5
    day = _day(root, 1.8)
    build(root, day, {"AAA": "CS", "BBB": "CS"}, db=stage)

    assert build_leaderboard.complete_days(live) == {day.isoformat()}       # whole already: skipped
    assert merge_rebuilt.merge([stage], live, minutes=7, pause=0, log=lambda _l: None) == 0

    live.unlink()
    for suffix in ("-wal", "-shm"):
        live.with_name(live.name + suffix).unlink(missing_ok=True)
    build(root, day, {"AAA": "CS"}, db=live)                           # a partial older rebuild: no BBB
    with sqlite3.connect(live) as con:                                  # cut off before its After Hours
        con.execute("DELETE FROM coverage WHERE board = 'afterhours'")
    assert build_leaderboard.complete_days(live) == set()
    assert merge_rebuilt.merge([stage], live, minutes=7, pause=0, log=lambda _l: None) == 1
    assert rows_at(live, day, 10, 0)["AAA"]["price"] == 1.8            # the staged rows, no older one left
    assert rows_at(live, day, 17, 0, "afterhours")["BBB"]["rank"] == 1
    assert states_at(live, day, 17, 0) == states_at(stage, day, 17, 0)
    assert build_leaderboard.complete_days(live) == {day.isoformat()}
    assert merge_rebuilt.merge([stage], live, pause=0, log=lambda _l: None) == 0
