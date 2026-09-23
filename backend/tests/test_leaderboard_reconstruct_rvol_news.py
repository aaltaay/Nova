"""The offline leaderboard rebuild (ADR 022) without hindsight: time-of-day RVOL
from the prior 20 sessions only, split-adjusted, and news first seen after the
prior close and at or before the minute."""
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

import lb_core  # noqa: E402  (research/leaderboard on sys.path via the helpers)
import lb_io  # noqa: E402

BASE_BARS = [("AAA", 4, 0, 11.0, 500), ("AAA", 6, 0, 11.0, 300)]


def _prior_sessions(root, n: int, *, vol=lambda i: 100.0) -> None:
    """``n`` prior sessions of AAA: ``vol(i)`` at 04:00 and three times that at 06:00."""
    for i in range(n):
        v = vol(i)
        write_minutes(root, session(i), [("AAA", 4, 0, 10.0, v), ("AAA", 6, 0, 10.0, 3 * v)])
        write_closes(root, session(i), {"AAA": 10.0})


def test_rvol_divides_by_the_prior_20_sessions_at_the_same_time_of_day(tmp_path):
    root, db = tmp_path / "massive", tmp_path / "lb.sqlite3"
    # 22 prior sessions; the two oldest carry a billion shares and must not count.
    _prior_sessions(root, 22, vol=lambda i: 1e9 if i < 2 else 100.0)
    day = session(22)
    write_minutes(root, day, BASE_BARS)

    build(root, day, {"AAA": "CS"}, db=db)

    at_0401 = rows_at(db, day, 4, 1)["AAA"]
    assert at_0401["rvol"] == pytest.approx(500 / 100) and at_0401["rvol_basis"] == "time_of_day_20"
    # 06:00: the 06:00 bars (today's and the priors') have not closed -> 500 / 100.
    assert rows_at(db, day, 6, 0)["AAA"]["rvol"] == pytest.approx(5.0)
    # 06:01: (500 + 300) / (100 + 300).
    assert rows_at(db, day, 6, 1)["AAA"]["rvol"] == pytest.approx(2.0)


def test_later_bars_and_later_sessions_never_change_an_earlier_minute(tmp_path):
    root = tmp_path / "massive"
    _prior_sessions(root, 22)
    day = session(22)
    write_minutes(root, day, BASE_BARS)
    build(root, day, {"AAA": "CS", "ZZZ": "CS"}, db=tmp_path / "before.sqlite3")
    before = {hm: rows_at(tmp_path / "before.sqlite3", day, *hm) for hm in [(4, 1), (5, 30), (6, 1)]}

    # The rest of the day happens, a later session is added, and the day's own
    # aggregate file appears -- none of it may reach back into 06:01 or earlier.
    write_minutes(root, day, BASE_BARS + [("AAA", 6, 1, 50.0, 1e8), ("ZZZ", 6, 5, 99.0, 1e8)])
    write_closes(root, day, {"AAA": 1.0, "ZZZ": 1.0})
    write_minutes(root, session(23), [("AAA", 4, 0, 1.0, 1e12), ("ZZZ", 4, 0, 1.0, 1e12)])
    write_closes(root, session(23), {"AAA": 1.0, "ZZZ": 1.0})
    build(root, day, {"AAA": "CS", "ZZZ": "CS"}, db=tmp_path / "after.sqlite3")

    for hm, rows in before.items():
        assert rows_at(tmp_path / "after.sqlite3", day, *hm) == rows
    assert rows_at(tmp_path / "after.sqlite3", day, 6, 2)["AAA"]["price"] == 50.0


@pytest.mark.parametrize(("n_prior", "expected"), [(9, None), (10, 5.0)])
def test_rvol_needs_ten_prior_sessions_in_which_the_symbol_printed(tmp_path, n_prior, expected):
    root, db = tmp_path / "massive", tmp_path / "lb.sqlite3"
    _prior_sessions(root, n_prior)
    day = session(n_prior)
    write_minutes(root, day, BASE_BARS)

    build(root, day, {"AAA": "CS"}, db=db)

    row = rows_at(db, day, 4, 1)["AAA"]
    assert row["rvol"] == (pytest.approx(expected) if expected else None)
    assert row["rvol_basis"] == ("time_of_day_20" if expected else None)


def test_rvol_is_unknown_when_the_prior_mean_by_that_time_is_zero(tmp_path):
    root, db = tmp_path / "massive", tmp_path / "lb.sqlite3"
    for i in range(12):   # printed every session, but never before 09:30
        write_minutes(root, session(i), [("NOPRE", 9, 30, 5.0, 100)])
    day = session(12)
    write_minutes(root, day, [("NOPRE", 4, 0, 5.0, 100), ("NOPRE", 9, 30, 5.0, 100)])

    build(root, day, {"NOPRE": "CS"}, db=db)

    assert rows_at(db, day, 4, 1)["NOPRE"]["rvol"] is None   # no mean to divide by: unknown, not infinite
    assert rows_at(db, day, 9, 31)["NOPRE"]["rvol"] == pytest.approx(2.0)


def test_prior_volume_is_split_adjusted(tmp_path):
    root, db = tmp_path / "massive", tmp_path / "lb.sqlite3"
    # A 1-for-10 reverse split executes before session 15: earlier sessions traded 10x the shares.
    _prior_sessions(root, 20, vol=lambda i: 1000.0 if i < 15 else 100.0)
    day = session(20)
    write_minutes(root, day, BASE_BARS)

    build(root, day, {"AAA": "CS"}, db=db, splits=[lb_io.Split("AAA", session(15), 10.0, 1.0)])

    assert rows_at(db, day, 4, 1)["AAA"]["rvol"] == pytest.approx(5.0)


def test_news_first_seen_keeps_the_earliest_article_inside_the_window():
    articles = [("aaa", 5.0), ("AAA", 3.0), ("AAA", 3.0), ("BBB", 1.0), ("CCC", 11.0), ("DDD", 10.0)]
    assert lb_core.news_first_seen(articles, 1.0, 10.0) == {"AAA": 3.0, "DDD": 10.0}


def test_has_news_counts_from_the_prior_close_and_only_once_published(tmp_path):
    root, db = tmp_path / "massive", tmp_path / "lb.sqlite3"
    prev, day = session(0), session(1)
    names = ("AAA", "BBB", "CCC")
    write_minutes(root, prev, [(s, 9, 30, 10.0, 100) for s in names])
    write_closes(root, prev, {s: 10.0 for s in names})
    write_minutes(root, day, [(s, 4, 0, 11.0, 100) for s in names])
    articles = [
        ("AAA", ts(prev, 15, 59)),   # before the prior close: yesterday's news
        ("AAA", ts(prev, 18, 0)),
        ("AAA", ts(day, 8, 0)),
        ("BBB", ts(day, 8, 0)),
        ("CCC", ts(prev, 12, 0)),
        ("CCC", ts(day, 20, 1)),     # after the session
    ]
    types = {s: "CS" for s in names}

    build(root, day, types, db=db, articles=articles)

    early = rows_at(db, day, 7, 59)
    assert (early["AAA"]["has_news"], early["AAA"]["news_first_seen_ts"]) == (1, ts(prev, 18, 0))
    assert (early["BBB"]["has_news"], early["BBB"]["news_first_seen_ts"]) == (0, None)
    at_0800 = rows_at(db, day, 8, 0)   # published at or before the minute counts
    assert (at_0800["BBB"]["has_news"], at_0800["BBB"]["news_first_seen_ts"]) == (1, ts(day, 8, 0))
    assert rows_at(db, day, 20, 0)["CCC"]["has_news"] == 0

    build(root, day, types, db=db, articles=articles, news_known=False)
    unknown = rows_at(db, day, 8, 0)
    assert all(r["has_news"] is None and r["news_first_seen_ts"] is None for r in unknown.values())


def test_news_archive_is_unknown_past_its_reach():
    window = (float(ts(session(0), 16, 0)), float(ts(session(1), 20, 0)))
    reach_short = lb_io.NewsArchive({"2026-06"}, lb_io._utc_naive(window[1] - 60), [("AAA", window[0] + 1)], window)
    reach_ok = lb_io.NewsArchive({"2026-06"}, lb_io._utc_naive(window[1] + 60), [("AAA", window[0] + 1)], window)
    missing_month = lb_io.NewsArchive(set(), lb_io._utc_naive(window[1] + 60), [], window)
    assert reach_short.for_window(window).known is False
    assert missing_month.for_window(window).known is False
    assert reach_ok.for_window(window).known is True and reach_ok.for_window(window).articles == [("AAA", window[0] + 1)]
