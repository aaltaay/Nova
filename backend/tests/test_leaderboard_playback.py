"""Recorded boards played back: no hindsight, never across a gap, halts from the log (ADR 023)."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from constants_leaderboard import LEADERBOARD_RECORD_SETTLE_SEC, LEADERBOARD_SCHEMA_VERSION
from leaderboard import auto_record, halts, playback, queue, recorder, store

ET = ZoneInfo("America/New_York")
DAY = "2026-09-18"  # a Friday, an exchange day
LONG_AFTER = datetime(2026, 9, 19, 12, 0, tzinfo=ET).timestamp()


def et(hh: int, mm: int, ss: int = 0) -> int:
    return int(datetime(2026, 9, 18, hh, mm, ss, tzinfo=ET).timestamp())


def desk(symbol, price, prev, volume=400_000, **extra):
    return {"symbol": symbol, "price": price, "prev_close": prev, "volume": volume, **extra}


GAINERS = [
    desk("AAA", 9.0, 3.0, float=4e6),       # +200%
    desk("BBB", 15.0, 6.0),                 # price out of LEADERS range
    desk("CCC", 5.0, 2.5),                  # +100%
    desk("DDD", 4.0, 2.5, float=60e6),      # float too big
    desk("EEE", 3.5, 2.5),                  # +40%
]


@pytest.fixture(autouse=True)
def fresh():
    queue.reset_for_tests()
    recorder.reset_for_tests()
    halts.reset_for_tests()
    auto_record.reset_for_tests()
    recorder.start_for_tests("run-1")
    yield
    queue.reset_for_tests()
    recorder.reset_for_tests()


def record(minute_ts, *, gainers=GAINERS, feed_live=True, halt_feed_ok=True, run_id="run-1", state="live"):
    batch = recorder.build_minute(
        minute_ts, {"gainers": (gainers, state), "losers": ([], "live")},
        feed_live=feed_live, halt_feed_ok=halt_feed_ok, run_id=run_id,
    )
    for kind, items in batch.items():
        queue.enqueue(kind, items)
    queue.flush_blocking()
    return batch


def start_run(run_id, ts, stopped=None, reason=None):
    with store.connect() as db:
        store.start_run(db, run_id, ts)
        if stopped is not None:
            store.stop_run(db, run_id, stopped, reason or "shutdown")


def test_the_board_at_a_moment_is_the_last_snapshot_taken_by_then():
    record(et(7, 41))
    record(et(7, 42), gainers=GAINERS[:2])
    # 07:42:00 plus less than the settle: the 07:42 snapshot was not taken yet.
    early = playback.board_at(DAY, et(7, 42) + LEADERBOARD_RECORD_SETTLE_SEC / 2, now=LONG_AFTER)
    assert early["minute_ts"] == et(7, 41) and len(early["boards"]["gainers"]["rows"]) == 5
    later = playback.board_at(DAY, et(7, 42, 30), now=LONG_AFTER)
    assert later["covered"] and later["minute_ts"] == et(7, 42)
    assert [r["symbol"] for r in later["boards"]["gainers"]["rows"]] == ["AAA", "BBB"]
    assert later["source"] == "recorded" and later["gap"] is None


def test_rows_keep_the_desk_order_and_unknowns_null():
    record(et(7, 41))
    out = playback.board_at(DAY, et(7, 41, 30), now=LONG_AFTER)
    rows = out["boards"]["gainers"]["rows"]
    assert [r["rank"] for r in rows] == [1, 2, 3, 4, 5]
    assert rows[1]["float_shares"] is None and rows[1]["rvol"] is None and rows[1]["has_news"] is None
    assert rows[0]["change_pct"] == pytest.approx(2.0)
    assert "session_date" not in rows[0]


def test_playback_leaders_and_auto_record_share_one_ranking():
    record(et(7, 50))
    shown = playback.board_at(DAY, et(7, 50, 20), now=LONG_AFTER)["leaders"]
    assert shown["board"] == "gainers"
    assert shown["symbols"] == ["AAA", "CCC", "EEE"]
    assert auto_record.pick_leaders(GAINERS, et(7, 50, 20)) == shown["symbols"]


def test_a_contradicted_float_is_kept_so_playback_and_auto_record_still_agree():
    """#532: the desk row's float check is recorded with the row, so a played-back minute refuses the
    same contradicted float auto-record refused live -- and keeps one small shares outstanding rescues."""
    gainers = [
        desk("SECZ", 9.0, 3.0, float=8.45e6, float_contradicted=True, shares_outstanding=163.27e6),
        desk("WHLR", 6.0, 2.5, float=54e3, float_contradicted=True, shares_outstanding=568e3),
        desk("CCC", 5.0, 2.5),
        desk("EEE", 3.5, 2.5, float=4e6, float_contradicted=False, shares_outstanding=5e6),
    ]
    record(et(7, 51), gainers=gainers)
    out = playback.board_at(DAY, et(7, 51, 20), now=LONG_AFTER)
    rows = {r["symbol"]: r for r in out["boards"]["gainers"]["rows"]}
    assert (rows["SECZ"]["float_contradicted"], rows["SECZ"]["shares_outstanding"]) == (True, 163.27e6)
    assert rows["EEE"]["float_contradicted"] is False and rows["CCC"]["float_contradicted"] is None
    assert out["leaders"]["symbols"] == ["WHLR", "CCC", "EEE"]
    assert auto_record.pick_leaders(gainers, et(7, 51, 20)) == out["leaders"]["symbols"]


def test_a_restart_is_a_gap_with_its_reason_never_the_last_board():
    start_run("run-1", et(7, 0), stopped=et(7, 12, 30), reason="shutdown")
    for m in range(0, 13):
        record(et(7, m))
    start_run("run-2", et(7, 30))
    for m in range(31, 35):
        record(et(7, m), run_id="run-2")
    out = playback.board_at(DAY, et(7, 20), now=LONG_AFTER)
    assert out["covered"] is False and out["boards"] == {} and out["minute_ts"] is None
    assert out["gap"]["reason"] == "not_running"
    assert (out["gap"]["start"], out["gap"]["end"]) == (et(7, 13), et(7, 31))
    assert out["gap"]["stop"] == "shutdown"


def test_an_unexpected_stop_says_so():
    start_run("run-1", et(7, 0))  # never stamped stopped
    record(et(7, 0))
    record(et(7, 10), run_id="run-2")
    gap = playback.board_at(DAY, et(7, 5), now=LONG_AFTER)["gap"]
    assert gap["reason"] == "not_running" and gap["stop"] == "unexpected"


def test_feed_down_minutes_record_no_rows_and_play_back_as_a_gap():
    record(et(8, 0))
    batch = record(et(8, 1), feed_live=False)
    assert batch["rows"] == [] and {c["state"] for c in batch["coverage"]} == {"feed_down"}
    record(et(8, 2), feed_live=False)
    record(et(8, 3))
    gap = playback.board_at(DAY, et(8, 1, 30), now=LONG_AFTER)["gap"]
    assert gap["reason"] == "feed_down" and (gap["start"], gap["end"]) == (et(8, 1), et(8, 3))


def test_a_day_with_nothing_recorded_and_outside_the_session():
    none = playback.board_at("2026-09-17", et(9, 0) - 86_400, now=LONG_AFTER)
    assert none["gap"]["reason"] == "not_recorded" and none["boards"] == {}
    early = playback.board_at(DAY, et(3, 59), now=LONG_AFTER)
    assert early["gap"]["reason"] == "outside_session"


def test_halted_comes_only_from_the_log_and_false_only_when_the_feed_answered():
    record(et(9, 45))
    record(et(9, 46), halt_feed_ok=False)
    halts.observe_ibkr("CCC", {"halt_start": et(9, 44, 10), "kind": "luld", "halt_code": 2}, now=et(9, 44, 11))
    queue.flush_blocking()
    rows = {r["symbol"]: r for r in playback.board_at(DAY, et(9, 45, 30), now=LONG_AFTER)["boards"]["gainers"]["rows"]}
    assert rows["CCC"]["halted"] is True and rows["AAA"]["halted"] is False
    later = {r["symbol"]: r for r in playback.board_at(DAY, et(9, 46, 30), now=LONG_AFTER)["boards"]["gainers"]["rows"]}
    assert later["CCC"]["halted"] is True and later["AAA"]["halted"] is None
    halts.observe_ibkr("CCC", None, now=et(9, 45, 40))
    queue.flush_blocking()
    after = {r["symbol"]: r for r in playback.board_at(DAY, et(9, 46, 30), now=LONG_AFTER)["boards"]["gainers"]["rows"]}
    assert after["CCC"]["halted"] is None  # resumed; this minute's halt feed was down


def test_coverage_spans_and_gaps():
    for m in (0, 1, 2):
        record(et(7, m))
    record(et(7, 3), feed_live=False)
    record(et(7, 4))
    out = playback.coverage(DAY, now=LONG_AFTER)
    assert out["source"] == "recorded"
    assert out["spans"] == [[et(7, 0), et(7, 3)], [et(7, 4), et(7, 5)]]
    reasons = [(g["reason"], g["start"], g["end"]) for g in out["gaps"]]
    assert ("not_running", et(4, 0), et(7, 0)) in reasons
    assert ("feed_down", et(7, 3), et(7, 4)) in reasons
    assert reasons[-1][0] == "not_running" and reasons[-1][2] == et(20, 1)


def test_days_list_both_sources_and_the_store():
    record(et(7, 0))
    out = playback.days(10)
    assert out["store"]["ok"] and out["schema_version"] == LEADERBOARD_SCHEMA_VERSION == 3
    day = out["days"][0]
    assert day["date"] == DAY and day["recorded"]["minutes"] == 1 and day["reconstructed"] is None
    assert "gainers" in day["recorded"]["boards"]


def test_an_unknown_store_version_refuses(tmp_path, monkeypatch):
    import sqlite3

    monkeypatch.setenv("NOVA_LEADERBOARD_DIR", str(tmp_path / "future"))
    (tmp_path / "future").mkdir()
    db = sqlite3.connect(tmp_path / "future" / "leaderboard.sqlite3")
    db.execute("PRAGMA user_version=9")
    db.close()
    with pytest.raises(sqlite3.DatabaseError):
        with store.connect():
            pass
    assert playback.days(5)["store"]["ok"] is False


def test_a_write_failure_is_kept_as_the_recorders_error(monkeypatch):
    def boom(*_a, **_k):
        raise OSError("disk full")

    monkeypatch.setattr(store, "write_batch", boom)
    queue.enqueue("minutes", [{"session_date": DAY, "minute_ts": et(7, 0), "run_id": "r", "feed_live": 1, "halt_feed_ok": 1}])
    queue.drain_once()
    status = recorder.status()
    assert status["ok"] is False and "disk full" in status["error"] and status["since"]
    monkeypatch.undo()
    queue.enqueue("minutes", [{"session_date": DAY, "minute_ts": et(7, 1), "run_id": "r", "feed_live": 1, "halt_feed_ok": 1}])
    queue.drain_once()
    assert recorder.status()["ok"] is True


def test_the_record_window_is_exchange_days_04_to_20():
    assert recorder.in_record_window(et(4, 0)) and recorder.in_record_window(et(20, 0))
    assert not recorder.in_record_window(et(3, 59)) and not recorder.in_record_window(et(20, 1))
    saturday = int(datetime(2026, 9, 19, 9, 0, tzinfo=ET).timestamp())
    assert not recorder.in_record_window(saturday)


def test_news_first_seen_is_the_earliest_headline_by_that_minute():
    early = desk("NEWS", 5.0, 3.0, has_news=True, newest_headline_at=et(6, 55))
    batch = recorder.build_minute(et(7, 0), {"gainers": ([early], "live")}, feed_live=True, halt_feed_ok=True, run_id="r")
    assert batch["rows"][0]["news_first_seen_ts"] == et(6, 55)
    newer = desk("NEWS", 5.0, 3.0, has_news=True, newest_headline_at=et(7, 20))
    batch = recorder.build_minute(et(7, 30), {"gainers": ([newer], "live")}, feed_live=True, halt_feed_ok=True, run_id="r")
    assert batch["rows"][0]["news_first_seen_ts"] == et(6, 55)
    future = desk("LATE", 5.0, 3.0, has_news=True, newest_headline_at=et(7, 45))
    batch = recorder.build_minute(et(7, 31), {"gainers": ([future], "live")}, feed_live=True, halt_feed_ok=True, run_id="r")
    assert batch["rows"][0]["news_first_seen_ts"] is None
