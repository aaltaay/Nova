"""A daily bar stored mid-session is not the finished day (#839).

IBKR's daily series, fetched while a session runs, carries that day's unfinished bar. Each stored row now
keeps when Nova wrote it (``written_ts``); a row is the finished session only when it was written at or
after 20:00 ET of its own date. A later short payload advancing the series' ``fetched_ts`` does not
certify an older row it did not return. The examples are the incident's: AIFF 2026-09-25, stored at 09:18
with the premarket high $1.89; the finished day's high was $2.17.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

import archive.db as archive_db
import bars_store
import large_cap_metrics as lcm
from ibkr import historical_service
from stock_read import history, level_map

ET = ZoneInfo("America/New_York")
SYM = "AIFF"


def et(y: int, m: int, d: int, hh: int = 0, mm: int = 0, ss: int = 0) -> float:
    return datetime(y, m, d, hh, mm, ss, tzinfo=ET).timestamp()


def day_t(d: str) -> str:
    """A stored daily bar's time: its session date at midnight UTC."""
    return f"{d}T00:00:00Z"


def dbar(d: str, h: float, lo: float = 1.0, c: float | None = None, o: float | None = None) -> dict:
    return {"t": day_t(d), "o": o if o is not None else lo, "h": h, "l": lo, "c": c if c is not None else h,
            "v": 1000}


def write_at(monkeypatch, when: float, bars: list[dict], *, symbol: str = SYM, timeframe: str = "1Day") -> None:
    with monkeypatch.context() as m:
        m.setattr(bars_store, "time", SimpleNamespace(time=lambda: when))
        bars_store.write_payload({"symbol": symbol, "timeframe": timeframe, "bars": bars,
                                  "coverage": bars_store.coverage_from_bars(bars, filling=False)})


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(archive_db, "cache_dir", lambda: tmp_path)
    archive_db.init_db()
    history._cache.clear()
    lcm.reset_for_testing()
    historical_service.reset_for_testing()
    asked: list[tuple[str, str]] = []
    monkeypatch.setattr(historical_service, "schedule_fill",
                        lambda sym, tf, limit, *, priority="open_chart": asked.append((sym, tf)))
    return asked


# -- the state of one stored daily row ---------------------------------------------------------------------
def test_a_row_is_final_only_when_written_at_or_after_twenty_hundred_et_of_its_own_date():
    t = day_t("2026-09-24")
    next_morning = et(2026, 9, 25, 9, 0)
    assert bars_store.daily_bar_state(t, et(2026, 9, 24, 9, 18), next_morning) == "partial"
    assert bars_store.daily_bar_state(t, et(2026, 9, 24, 19, 59, 59), next_morning) == "partial"
    assert bars_store.daily_bar_state(t, et(2026, 9, 24, 20, 0, 0), next_morning) == "final"
    assert bars_store.daily_bar_state(t, et(2026, 9, 25, 9, 40), next_morning) == "final"


def test_the_twenty_hundred_boundary_follows_eastern_summer_and_winter_time():
    # 00:30 UTC the next day is 19:30 EST in January (not over) and 20:30 EDT in September (over).
    jan_write = datetime(2026, 1, 16, 0, 30, tzinfo=ZoneInfo("UTC")).timestamp()
    sep_write = datetime(2026, 9, 25, 0, 30, tzinfo=ZoneInfo("UTC")).timestamp()
    later = et(2026, 10, 1, 9, 0)
    assert bars_store.daily_bar_state(day_t("2026-01-15"), jan_write, later) == "partial"
    assert bars_store.daily_bar_state(day_t("2026-09-24"), sep_write, later) == "final"
    assert bars_store.daily_session_end(day_t("2026-01-15")) == et(2026, 1, 15, 20, 0)
    assert bars_store.daily_session_end(day_t("2026-09-24")) == et(2026, 9, 24, 20, 0)


def test_the_current_day_is_forming_until_twenty_hundred_then_unfinished_if_nobody_refetched():
    t = day_t("2026-09-24")
    w = et(2026, 9, 24, 9, 18)
    assert bars_store.daily_bar_state(t, w, et(2026, 9, 24, 15, 0)) == "forming"
    assert bars_store.daily_bar_state(t, w, et(2026, 9, 24, 19, 59, 59)) == "forming"
    assert bars_store.daily_bar_state(t, w, et(2026, 9, 24, 20, 0)) == "partial"
    assert bars_store.daily_bar_state(t, w, et(2026, 9, 25, 0, 5)) == "partial"        # a midnight read


def test_friday_stored_at_three_is_still_unfinished_on_monday():
    assert bars_store.daily_bar_state(day_t("2026-10-16"), et(2026, 10, 16, 15, 0), et(2026, 10, 19, 9, 0)) == "partial"


def test_a_row_without_a_write_time_is_unknown_once_its_day_is_over():
    t = day_t("2026-09-24")
    assert bars_store.daily_bar_state(t, None, et(2026, 9, 25, 9, 0)) == "unknown"
    assert bars_store.daily_bar_state(t, None, et(2026, 9, 24, 12, 0)) == "forming"


# -- the store keeps the evidence per row ------------------------------------------------------------------
def test_a_later_short_payload_advances_the_series_fetch_but_not_the_older_rows_evidence(store, monkeypatch):
    write_at(monkeypatch, et(2026, 9, 24, 9, 18), [dbar("2026-09-23", 1.6), dbar("2026-09-24", 1.89)])
    write_at(monkeypatch, et(2026, 9, 25, 10, 0), [dbar("2026-09-25", 2.5)])          # today only
    got = bars_store.read(SYM, "1Day", 10, provenance=True)
    assert got["coverage"]["fetched_ts"] == et(2026, 9, 25, 10, 0)
    w = {b["t"][:10]: b["w"] for b in got["bars"]}
    assert w == {"2026-09-23": et(2026, 9, 24, 9, 18), "2026-09-24": et(2026, 9, 24, 9, 18),
                 "2026-09-25": et(2026, 9, 25, 10, 0)}
    now = et(2026, 9, 25, 10, 5)
    states = [bars_store.daily_bar_state(b["t"], b["w"], now) for b in got["bars"]]
    assert states == ["final", "partial", "forming"]


def test_an_empty_answer_finalizes_nothing_and_changes_no_revision(store, monkeypatch):
    write_at(monkeypatch, et(2026, 9, 24, 9, 18), [dbar("2026-09-24", 1.89)])
    rev = bars_store.daily_revision(SYM)
    write_at(monkeypatch, et(2026, 9, 25, 10, 0), [])
    got = bars_store.read(SYM, "1Day", 10, provenance=True)
    assert got["bars"][0]["w"] == et(2026, 9, 24, 9, 18)
    assert bars_store.daily_revision(SYM) == rev


def test_a_daily_write_bumps_only_that_symbols_revision(store, monkeypatch):
    before, other = bars_store.daily_revision(SYM), bars_store.daily_revision("ACN")
    write_at(monkeypatch, et(2026, 9, 25, 9, 40), [dbar("2026-09-24", 2.17)])
    write_at(monkeypatch, et(2026, 9, 25, 9, 40), [{"t": "2026-09-25T13:30:00Z", "o": 1, "h": 1, "l": 1, "c": 1, "v": 1}],
             timeframe="1Min")
    assert bars_store.daily_revision(SYM) == before + 1
    assert bars_store.daily_revision("ACN") == other


def test_rows_stored_before_the_write_time_existed_read_unknown(tmp_path, monkeypatch):
    monkeypatch.setattr(archive_db, "cache_dir", lambda: tmp_path)
    conn = archive_db.get_connection()
    try:
        conn.executescript("""
            CREATE TABLE bars_intraday (
                id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT NOT NULL, timeframe TEXT NOT NULL,
                ts REAL NOT NULL, open REAL NOT NULL, high REAL NOT NULL, low REAL NOT NULL, close REAL NOT NULL,
                volume REAL NOT NULL DEFAULT 0, source TEXT NOT NULL, session_date TEXT NOT NULL,
                UNIQUE(symbol, timeframe, ts));
        """)
        ts = datetime(2026, 9, 24, tzinfo=ZoneInfo("UTC")).timestamp()
        conn.execute("INSERT INTO bars_intraday (symbol, timeframe, ts, open, high, low, close, volume, source,"
                     " session_date) VALUES (?, '1Day', ?, 1, 1.89, 1, 1.5, 10, 'ibkr', '2026-09-23')", (SYM, ts))
        conn.commit()
    finally:
        conn.close()
    archive_db.init_db()
    got = bars_store.read(SYM, "1Day", 5, provenance=True)
    assert got["bars"][0]["w"] is None
    assert bars_store.daily_bar_state(got["bars"][0]["t"], None, et(2026, 9, 25, 9, 0)) == "unknown"
    assert "w" not in bars_store.read(SYM, "1Day", 5)["bars"][0]                # the chart's wire is unchanged


# -- the stock read: yesterday, the daily map, runs and the 200-day ---------------------------------------
def _year(end: str, n: int = 205) -> list[dict]:
    """``n`` days ending ``end`` closing 1.50 with highs at 1.60 (no runs)."""
    last = date.fromisoformat(end)
    return [dbar((last - timedelta(days=n - 1 - i)).isoformat(), 1.6, 1.4, 1.5) for i in range(n)]


def _seed_aiff(monkeypatch) -> None:
    write_at(monkeypatch, et(2026, 9, 24, 21, 0), _year("2026-09-24"))              # finished through 09-24
    write_at(monkeypatch, et(2026, 9, 25, 9, 18), [dbar("2026-09-25", 1.89, 1.45, 1.80)])   # the 09:18 snapshot


def _yday(lm: dict) -> list[dict]:
    return [m for z in lm["intraday"] + lm["daily"] for m in z["members"] if m["kind"] in ("yday_high", "yday_low")]


def test_a_0918_snapshot_read_the_next_session_is_not_yesterday(store, monkeypatch):
    _seed_aiff(monkeypatch)
    now = et(2026, 9, 28, 9, 30)
    out = history.summary(SYM, now)
    last = out["daily"][-1]
    assert (last["d"], last["state"], last["through"]) == ("2026-09-25", "partial", et(2026, 9, 25, 9, 18))
    assert out["unfinished"] == [{"date": "2026-09-25", "state": "partial", "stored_through": et(2026, 9, 25, 9, 18)}]
    assert out["sma200"] is None                                    # one of its 200 closes is a snapshot
    assert out["runs"] == []
    lm = level_map.build([], out["daily"], price=1.9, prior_close=None, vwap=None, now=now, sma200=out["sma200"],
                          daily_note=history.daily_note(out))
    assert _yday(lm) == []                                          # never 1.89 as yesterday's high
    assert all(m["price"] != 1.89 for z in lm["daily"] for m in z["members"])
    assert "Sep 25" in lm["daily_note"] and "09:18" in lm["daily_note"]
    assert store == [(SYM, "1Day")]                                 # the paced background fill was asked once
    history.summary(SYM, now)
    assert store == [(SYM, "1Day")]                                 # a second read does not respray it


def test_the_refetched_day_reaches_yesterday_runs_and_the_200_day_after_a_first_read(store, monkeypatch):
    _seed_aiff(monkeypatch)
    now = et(2026, 9, 28, 9, 30)
    first = history.summary(SYM, now)
    other = history.summary("ACN", now)
    write_at(monkeypatch, et(2026, 9, 28, 9, 31), [dbar("2026-09-25", 2.17, 1.45, 1.80)])   # IBKR's finished bar
    out = history.summary(SYM, et(2026, 9, 28, 9, 32))
    assert out is not first and out["unfinished"] == []
    assert out["daily"][-1]["h"] == 2.17 and out["daily"][-1]["state"] == "final"
    assert [r["date"] for r in out["runs"]] == ["2026-09-25"]       # 2.17 over 1.50 is a run; 1.89 was not
    assert out["sma200"] is not None and out["sma200"] != first["sma200"]
    lm = level_map.build([], out["daily"], price=1.9, prior_close=None, vwap=None, now=now, sma200=out["sma200"],
                          daily_note=history.daily_note(out))
    assert {m["kind"]: m["price"] for m in _yday(lm)}["yday_high"] == 2.17
    assert lm["daily_note"] is None
    assert history.summary("ACN", now) is other                     # another symbol's cache stays valid


def test_a_forming_today_beside_yesterdays_partial_row(store, monkeypatch):
    _seed_aiff(monkeypatch)
    write_at(monkeypatch, et(2026, 9, 28, 10, 0), [dbar("2026-09-28", 3.10, 1.9, 3.0)])   # a later short payload
    now = et(2026, 9, 28, 10, 5)
    out = history.summary(SYM, now)
    assert [(b["d"], b["state"]) for b in out["daily"][-2:]] == [("2026-09-25", "partial"), ("2026-09-28", "forming")]
    lm = level_map.build([], out["daily"], price=3.0, prior_close=None, vwap=None, now=now, sma200=out["sma200"],
                          daily_note=history.daily_note(out))
    assert _yday(lm) == []
    assert all(m["price"] != 3.10 for z in lm["daily"] for m in z["members"])     # today is never a daily level


def test_a_yesterday_with_no_record_of_when_it_was_stored_is_not_yesterday(store, monkeypatch):
    write_at(monkeypatch, et(2026, 9, 24, 21, 0), _year("2026-09-24", 30))
    conn = archive_db.get_connection()
    try:
        conn.execute("UPDATE bars_intraday SET written_ts = NULL WHERE ts = ?",
                     (datetime(2026, 9, 24, tzinfo=ZoneInfo("UTC")).timestamp(),))
        conn.commit()
    finally:
        conn.close()
    now = et(2026, 9, 25, 9, 30)
    out = history.summary(SYM, now)
    assert out["unfinished"] == [{"date": "2026-09-24", "state": "unknown", "stored_through": None}]
    lm = level_map.build([], out["daily"], price=1.5, prior_close=None, vwap=None, now=now,
                          daily_note=history.daily_note(out))
    assert _yday(lm) == []                                          # 09-23 is not renamed yesterday either
    assert "Sep 24" in lm["daily_note"]


def test_sparse_finished_history_is_read_as_it_is(store, monkeypatch):
    write_at(monkeypatch, et(2026, 9, 24, 21, 0), _year("2026-09-24", 3))
    now = et(2026, 9, 25, 9, 30)
    out = history.summary(SYM, now)
    assert out["daily_days"] == 3 and out["unfinished"] == [] and out["sma200"] is None
    lm = level_map.build([], out["daily"], price=1.5, prior_close=None, vwap=None, now=now,
                          daily_note=history.daily_note(out))
    assert {m["kind"] for m in _yday(lm)} == {"yday_high", "yday_low"} and lm["daily_note"] is None
    assert store == []                                              # nothing to repair


def test_sim_reads_the_days_before_the_replayed_one_and_names_an_unfinished_prior_day(store, monkeypatch):
    write_at(monkeypatch, et(2026, 9, 24, 21, 0), _year("2026-09-23", 30))
    write_at(monkeypatch, et(2026, 9, 24, 9, 18), [dbar("2026-09-24", 1.89, 1.45, 1.80)])
    write_at(monkeypatch, et(2026, 9, 27, 21, 0), [dbar("2026-09-25", 9.0), dbar("2026-09-26", 9.5)])
    playhead = et(2026, 9, 25, 9, 30)                               # replaying 09-25
    out = history.summary(SYM, playhead, replay=True)
    assert [b["d"] for b in out["daily"]][-2:] == ["2026-09-23", "2026-09-24"]   # never the day itself, or later
    assert out["daily"][-1]["state"] == "partial"
    lm = level_map.build([], out["daily"], price=1.5, prior_close=None, vwap=None, now=playhead,
                          daily_note=history.daily_note(out))
    assert _yday(lm) == [] and "Sep 24" in lm["daily_note"]


# -- the Large Cap metrics --------------------------------------------------------------------------------
def test_large_cap_metrics_wait_for_a_finished_last_session_and_see_the_refetch(store, monkeypatch):
    write_at(monkeypatch, et(2026, 9, 24, 21, 0), _year("2026-09-24", 25))
    write_at(monkeypatch, et(2026, 9, 25, 9, 18), [dbar("2026-09-25", 1.89, 1.45, 1.80)])
    now = et(2026, 9, 26, 9, 30)
    monkeypatch.setattr(lcm, "time", SimpleNamespace(time=lambda: now, monotonic=lambda: 100.0))
    assert lcm.daily_bar_metrics(SYM) == lcm._EMPTY_DAILY          # not a 20-day high of a snapshot
    assert store == [(SYM, "1Day")]
    write_at(monkeypatch, et(2026, 9, 26, 9, 31), [dbar("2026-09-25", 2.17, 1.45, 1.80)])
    out = lcm.daily_bar_metrics(SYM)                                # inside the TTL: the refetch is seen
    assert out["high_20d"] == 2.17 and out["change_5d_pct"] == pytest.approx(1.80 / 1.50 - 1)


def test_large_cap_metrics_leave_out_todays_forming_bar(store, monkeypatch):
    write_at(monkeypatch, et(2026, 9, 25, 9, 40), _year("2026-09-24", 25) + [dbar("2026-09-25", 5.0, 1.4, 4.0)])
    monkeypatch.setattr(lcm, "time", SimpleNamespace(time=lambda: et(2026, 9, 25, 9, 45), monotonic=lambda: 100.0))
    out = lcm.daily_bar_metrics(SYM)
    assert out["high_20d"] == 1.6 and out["change_5d_pct"] == pytest.approx(0.0)
    assert store == []


def test_the_roster_check_asks_for_an_unfinished_last_session(store, monkeypatch):
    import large_cap_hooks

    write_at(monkeypatch, et(2026, 9, 24, 21, 0), _year("2026-09-24", 25))
    write_at(monkeypatch, et(2026, 9, 25, 9, 18), [dbar("2026-09-25", 1.89, 1.45, 1.80)])
    monkeypatch.setattr(large_cap_hooks, "time", SimpleNamespace(time=lambda: et(2026, 9, 26, 9, 30)))
    assert large_cap_hooks._short_of_daily_bars([SYM]) == [SYM]
    write_at(monkeypatch, et(2026, 9, 26, 9, 31), [dbar("2026-09-25", 2.17, 1.45, 1.80)])
    assert large_cap_hooks._short_of_daily_bars([SYM]) == []


# -- the repair is the paced fill, asked again after a shed ---------------------------------------------
def test_the_repair_asks_once_per_retry_window_so_a_shed_fill_is_asked_again(store, monkeypatch):
    clock = {"t": 1000.0}
    monkeypatch.setattr(historical_service, "time", SimpleNamespace(monotonic=lambda: clock["t"]), raising=False)
    assert historical_service.schedule_daily_repair(SYM, 260) is True
    assert historical_service.schedule_daily_repair(SYM, 260) is False
    assert historical_service.schedule_daily_repair("ACN", 260) is True
    clock["t"] += historical_service.IBKR_BARS_DAILY_REPAIR_RETRY_SEC
    assert historical_service.schedule_daily_repair(SYM, 260) is True
    assert store == [(SYM, "1Day"), ("ACN", "1Day"), (SYM, "1Day")]
