"""The historical quote card's session figures (QA W7, 2026-09-22).

GRML 2026-09-21, window 13:00-13:30: the snapshot's ``open`` was the 13:00
print, so the card's Gap% read +223.51% against the session's +156.49%, and its
Vol / High / Low counted from 13:00 as if they were the day's. The snapshot now
names the regular session's open (``session_open``) and says whether volume /
high / low are the session's so far or only the window's (``stats_scope``).
"""
from datetime import datetime

import pytest

import bars_store
from archive import db
from sim import history_playback as playback, history_session, history_store as store, session_clock as clock

DAY = "2026-09-18"


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("NOVA_SIM_HISTORY_DIR", str(tmp_path / "history"))
    monkeypatch.setattr(db, "cache_dir", lambda: tmp_path)
    db.init_db()
    clock.reset_for_tests()
    playback.clear()
    yield
    clock.reset_for_tests()
    playback.clear()


def _at(hh: int, mm: int, ss: int = 0) -> float:
    return datetime.fromisoformat(f"{DAY}T{hh:02d}:{mm:02d}:{ss:02d}").replace(tzinfo=clock.ET).timestamp()


def _load(start: str, end: str, prints, covered_through: float | None = None):
    spec = store.window("IMCC", DAY, start, end)
    job = store.create(spec, "trades")
    rows = [dict(ts=int(ts), price=price, size=size) for ts, price, size in prints]
    store.commit_page(job["id"], spec["start_ts"], rows, int(covered_through or spec["end_ts"]), False)
    playback.select(spec)
    clock.set_paused(True)
    return spec


def _scrub_to(spec: dict, ts: float) -> None:
    clock.scrub_to_second(int(ts - spec["start_ts"]))


FULL_DAY = [
    (_at(4, 0, 10), 5.0, 100),
    (_at(9, 29, 59), 6.0, 100),
    (_at(9, 30, 1), 7.31, 500),
    (_at(9, 45), 8.0, 200),
]


def test_a_window_from_the_session_start_reports_the_session_and_its_open() -> None:
    spec = _load("04:00", "10:00", FULL_DAY)
    _scrub_to(spec, _at(9, 20))
    snap = playback.snapshot("IMCC")
    assert snap["session_open"] is None  # premarket: no open yet, like the live card
    assert snap["stats_scope"] == "session"
    _scrub_to(spec, _at(9, 50))
    snap = playback.snapshot("IMCC")
    assert snap["session_open"] == 7.31
    assert snap["stats_scope"] == "session"
    assert (snap["volume"], snap["high"], snap["low"]) == (900, 8.0, 5.0)


def test_a_midday_window_is_the_windows_figures_and_never_its_first_print_as_the_open() -> None:
    spec = _load("13:00", "13:30", [(_at(13, 0), 9.22, 1000), (_at(13, 10), 9.63, 500)])
    _scrub_to(spec, _at(13, 18))
    snap = playback.snapshot("IMCC")
    assert snap["open"] == 9.22  # the window's first print, still published for the window
    assert snap["session_open"] is None  # 09:30 was not downloaded and no bar is stored
    assert snap["stats_scope"] == "window"


def test_a_midday_window_takes_the_open_from_the_stored_0930_bar() -> None:
    t = datetime.fromtimestamp(_at(9, 30), clock.ET).isoformat()
    bars_store.write_payload(dict(symbol="IMCC", timeframe="1Min", bars=[dict(t=t, o=7.31, h=7.9, l=7.2, c=7.5, v=9000)]))
    spec = _load("13:00", "13:30", [(_at(13, 0), 9.22, 1000)])
    _scrub_to(spec, _at(13, 18))
    assert playback.snapshot("IMCC")["session_open"] == 7.31


def test_a_gap_over_the_open_is_not_bridged_by_a_later_print() -> None:
    """09:30 falls in an undownloaded stretch: the next range's first print is not the open."""
    spec = store.window("IMCC", DAY, "04:00", "10:00")
    job = store.create(spec, "trades")
    a = spec["start_ts"]
    store.commit_page(job["id"], a, [dict(ts=int(_at(4, 0, 10)), price=5.0, size=100)], int(_at(9, 0)), False)
    selected = playback._load(spec)
    ranges = [[int(a), int(_at(9, 0))], [int(_at(9, 40)), int(spec["end_ts"])]]
    eligible = selected.eligible + (dict(ts=int(_at(9, 40, 5)), price=8.8, size=100),)
    keys = list(selected.eligible_keys) + [int(_at(9, 40, 5))]
    assert history_session.session_open(spec, eligible, keys, ranges) is None


def test_a_session_window_with_a_gap_before_the_playhead_is_only_the_windows() -> None:
    spec = _load("04:00", "10:00", FULL_DAY, covered_through=_at(9, 0))
    _scrub_to(spec, _at(9, 50))
    assert playback.snapshot("IMCC")["stats_scope"] == "window"
