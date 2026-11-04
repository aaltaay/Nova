"""Correcting the live minutes master's builder got wrong (``archive/live_minute_repair``).

A stored live minute moves only when it carries a fingerprint: cut down to its last updates' shares
(``fragment``), or master's whole count where a second counter's return counted again (``phantom``). It
then takes the builder's own count from ``l1_ticks``. Nothing else moves.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

import archive.db as archive_db
from archive import live_minute_repair as repair
from archive.capture import session_date_for_ts
from constants import ARCHIVE_DB_FILENAME

ET = ZoneInfo("America/New_York")
NOW = datetime(2026, 11, 5, 9, 0, tzinfo=ET).timestamp()     # the day after: nothing is "recent"


def at(hh: int, mm: int, ss: float = 0.0, day: tuple[int, int, int] = (2026, 11, 4)) -> float:
    return datetime(*day, hh, mm, tzinfo=ET).timestamp() + ss


@pytest.fixture
def conn(monkeypatch, tmp_path):
    monkeypatch.setattr(archive_db, "cache_dir", lambda: tmp_path)
    archive_db.init_db()
    db = sqlite3.connect(str(tmp_path / ARCHIVE_DB_FILENAME))
    yield db
    db.close()


def tick(db, symbol: str, ts: float, day_volume: float | None) -> None:
    db.execute("INSERT INTO l1_ticks (symbol, ts, price, volume, day_high, session_date) VALUES (?, ?, 1.0, ?, NULL, ?)",
               (symbol, ts, day_volume, session_date_for_ts(ts)))


def bar(db, symbol: str, ts: float, volume: float, source: str = "ibkr_l1") -> None:
    db.execute("INSERT INTO bars_intraday (symbol, timeframe, ts, open, high, low, close, volume, source, session_date) "
               "VALUES (?, '1Min', ?, 1.0, 1.0, 1.0, 1.0, ?, ?, ?)", (symbol, ts, volume, source, session_date_for_ts(ts)))


def stored(db, symbol: str, ts: float) -> float:
    return db.execute("SELECT volume FROM bars_intraday WHERE symbol = ? AND ts = ?", (symbol, ts)).fetchone()[0]


def plans(db) -> list:
    return [repair.plan_day(db, day, symbols, now=NOW) for day, symbols in repair.live_days(db).items()]


def run(db, *, apply: bool = False) -> tuple[dict, int | None]:
    planned = plans(db)
    written = repair.apply(db, [c for p in planned for c in p.changes]) if apply else None
    return repair.report(planned, applied=written), written


def counts(master: list[float], fixed: list[float] | None = None, after_gap: bool = False) -> repair.MinuteCounts:
    return repair.MinuteCounts(master=master, fixed=list(master) if fixed is None else fixed, after_gap=after_gap)


# -- the rule ----------------------------------------------------------------------------------------


def test_classify_reads_the_two_fingerprints():
    clean = counts([0.0, 100.0, 200.0, 641.0])                         # the whole minute: 941
    assert repair.classify(941, clean) == ("whole", 941.0)
    assert repair.classify(641, clean) == ("fragment", 941.0)          # its last update only
    assert repair.classify(841, clean) == ("fragment", 941.0)          # its last two
    assert repair.classify(300, clean) == ("other", 300.0)             # a middle stretch: not master's write
    assert repair.classify(0, clean) == ("other", 0.0)                 # a zero never replaced a stored volume
    assert repair.classify(5_000, clean) == ("other", 5_000.0)         # more than any count of the ticks
    # A second counter's return: master counted 186,236,451 shares again; the builder now does not.
    phantom = counts([0.0, 0.0, 186_333_470.0, 3_238.0], fixed=[0.0, 0.0, 97_020.0, 3_238.0])
    assert repair.classify(186_336_708, phantom) == ("phantom", 100_258.0)
    assert repair.classify(3_238, phantom) == ("fragment", 100_258.0)
    assert repair.classify(100_258, phantom) == ("whole", 100_258.0)
    assert repair.classify(641, counts([0.0, 641.0], after_gap=True)) == ("gap", 641.0)


def test_minute_counts_take_the_streaming_line_only_and_count_it_both_ways():
    ticks = [
        (at(9, 30, 0), 1_000), (at(9, 30, 10), 1_100),
        (at(9, 30, 12.374), 900),                        # the table reprice, on the desk's clock: not the line
        (at(9, 30, 20), 950), (at(9, 30, 30), 1_150),    # a second counter, then the real total's return
        (at(9, 35, 0), 5_000),                           # 270 s of silence: a restart or a dropped line
        (at(20, 30, 0), 9_000),                          # outside the session: nothing, and a baseline after
    ]
    minutes = repair.minute_counts(ticks)
    assert minutes[at(9, 30)].master == [0.0, 100.0, 0.0, 200.0]
    assert minutes[at(9, 30)].fixed == [0.0, 100.0, 0.0, 50.0]
    assert minutes[at(9, 30)].after_gap is False
    assert minutes[at(9, 35)].after_gap is True
    assert at(20, 30) not in minutes


# -- the archive -------------------------------------------------------------------------------------


def test_the_cris_open_minute_is_raised_to_its_whole_count(conn):
    """CRIS 2026-11-04 04:00 stored 641 while IBKR's day volume grew 130,136 that minute."""
    m = at(4, 0)
    for ss, day_volume in ((0, 366_699), (12, 401_000), (31, 455_550), (47, 496_194), (59, 496_835)):
        tick(conn, "CRIS", m + ss, day_volume)
    tick(conn, "CRIS", m + 61, 497_000)
    bar(conn, "CRIS", m, 641)
    conn.commit()

    result, _ = run(conn)
    assert result["totals"]["fragment"] == 1 and result["totals"]["shares_added"] == 130_136 - 641
    assert stored(conn, "CRIS", m) == 641                             # a dry run writes nothing

    _, written = run(conn, apply=True)
    assert written == 1 and stored(conn, "CRIS", m) == 130_136
    again, written = run(conn, apply=True)
    assert written == 0 and again["totals"]["whole"] == 1             # a second run finds it whole


def test_a_phantom_minute_comes_down_to_the_shares_that_traded(conn):
    """FRGT 2026-10-06 19:48: a stale 145,465,583 between 331,702,034 and 331,799,053 -- master counted
    the return, 186M shares on a 220M-share day."""
    m = at(19, 48, day=(2026, 10, 6))
    for ss, day_volume in ((1, 331_702_034), (20, 145_465_583), (20, 331_799_053), (29, 331_802_291)):
        tick(conn, "FRGT", m + ss, day_volume)
    bar(conn, "FRGT", m, 331_802_291 - 145_465_583)                 # master's whole count of that minute
    conn.commit()

    result, written = run(conn, apply=True)
    assert result["totals"]["phantom"] == 1 and written == 1
    assert result["totals"]["shares_removed"] == (331_802_291 - 145_465_583) - (331_802_291 - 331_702_034)
    assert stored(conn, "FRGT", m) == 331_802_291 - 331_702_034


def test_only_a_fingerprint_moves_a_row(conn):
    m = at(10, 0)
    for symbol in ("WHOLE", "MIDDLE", "HIST", "RECENT"):
        for ss, day_volume in ((1, 10_000), (20, 10_500), (40, 10_800), (59, 11_000)):
            tick(conn, symbol, m + ss, day_volume)
    bar(conn, "WHOLE", m, 1_000)                                     # already the whole minute
    bar(conn, "MIDDLE", m, 300)                                      # matches no suffix (500 + 300 + 200)
    bar(conn, "NOTICKS", m, 77)                                      # nothing recorded for it
    bar(conn, "HIST", m, 200, source="ibkr")                         # IBKR's own bar, though it looks cut down
    late = NOW - 60
    tick(conn, "RECENT", late + 1, 20_000)
    tick(conn, "RECENT", late + 30, 20_500)
    bar(conn, "RECENT", float(int(late // 60) * 60), 100)            # a builder may still write it
    conn.commit()

    result, written = run(conn, apply=True)
    assert written == 0
    assert {k: result["totals"][k] for k in repair.KINDS} == {
        "whole": 1, "fragment": 0, "phantom": 0, "other": 1, "gap": 0, "no_ticks": 1, "recent": 1}
    assert [stored(conn, s, m) for s in ("WHOLE", "MIDDLE", "NOTICKS", "HIST")] == [1_000, 300, 77, 200]


def test_a_restart_never_turns_the_shares_traded_while_away_into_a_spike(conn):
    """The backend was down 09:40-09:45 while 2M shares traded. Its first update after it was a baseline;
    counting the jump would put 2M on one minute."""
    tick(conn, "ABCD", at(9, 40, 10), 1_000_000)
    tick(conn, "ABCD", at(9, 40, 20), 1_000_100)
    tick(conn, "ABCD", at(9, 45, 30), 3_000_000)
    tick(conn, "ABCD", at(9, 45, 40), 3_000_200)
    bar(conn, "ABCD", at(9, 45), 200)
    conn.commit()

    result, written = run(conn, apply=True)
    assert written == 0 and result["totals"]["gap"] == 1
    assert stored(conn, "ABCD", at(9, 45)) == 200


def test_a_row_written_again_after_the_plan_is_left_alone(conn):
    m = at(11, 0)
    for ss, day_volume in ((1, 1_000), (30, 1_400), (59, 1_500)):
        tick(conn, "ABCD", m + ss, day_volume)
    bar(conn, "ABCD", m, 100)
    conn.commit()
    planned = plans(conn)
    assert [(c.stored, c.volume) for p in planned for c in p.changes] == [(100.0, 500.0)]
    conn.execute("UPDATE bars_intraday SET volume = 450 WHERE symbol = 'ABCD'")    # the live builder wrote it
    conn.commit()

    assert repair.apply(conn, [c for p in planned for c in p.changes]) == 0
    assert stored(conn, "ABCD", m) == 450


def test_the_report_lists_each_day_and_the_most_moved(conn):
    for day, symbol in (((2026, 11, 3), "AAA"), ((2026, 11, 4), "BBB")):
        m = at(9, 31, day=day)
        for ss, day_volume in ((1, 5_000), (30, 9_000), (59, 9_100)):
            tick(conn, symbol, m + ss, day_volume)
        bar(conn, symbol, m, 100)
    conn.commit()

    result, _ = run(conn)
    assert result["schema_version"] == 1 and result["applied"] is None
    assert [(d["day"], d["fragment"], d["shares_added"], d["shares_removed"]) for d in result["days"]] == [
        ("2026-11-03", 1, 4_000, 0), ("2026-11-04", 1, 4_000, 0)]
    assert [(t["symbol"], t["day"], t["shares_moved"]) for t in result["top"]] == [
        ("AAA", "2026-11-03", 4_000), ("BBB", "2026-11-04", 4_000)]
