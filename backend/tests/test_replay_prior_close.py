"""The replayed session's previous close is IBKR's own figure, or none (#542).

Nova took the prior session's 15:59 one-minute close (the last trade before the
closing auction) or a stored daily bar fetched with extended hours (its close is
the last after-hours trade). WHLR 2026-09-23 read 1.97 -- the daily bar even
closed at 3.5514 -- against IBKR's 1.87; GRML 2026-09-21 read 4.51 against 2.85,
so at 9.41 the head showed +109% instead of about +230%.
"""
from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
import threading
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

import pytest

import bars_store
from archive import db as archive_db
from leaderboard import store as lb_store
from leaderboard.rows import make_row
from sim import capture_player, history_download, history_playback, history_store, prior_close, session_clock

ET = ZoneInfo("America/New_York")


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(archive_db, "cache_dir", lambda: tmp_path)
    archive_db.init_db()
    capture_player.reset_for_tests()
    history_playback.clear()
    session_clock.reset_for_tests()
    yield tmp_path
    capture_player.reset_for_tests()
    history_playback.clear()
    session_clock.reset_for_tests()


def at(day: str, hh: int, mm: int) -> int:
    return int(datetime.combine(datetime.fromisoformat(day).date(), time(hh, mm), ET).timestamp())


def utc_iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).isoformat()


def stale_proxies(symbol: str, prior_day: str, minute_close: float, daily_close: float) -> None:
    """What Nova used to read: the prior session's 15:59 minute bar and its extended-hours daily bar."""
    bars_store.write_payload(dict(symbol=symbol, timeframe="1Min", bars=[
        dict(t=utc_iso(at(prior_day, 15, 59)), o=1, h=9, l=1, c=minute_close, v=10)]))
    bars_store.write_payload(dict(symbol=symbol, timeframe="1Day", bars=[
        dict(t=f"{prior_day}T00:00:00+00:00", o=1, h=9, l=1, c=daily_close, v=10)]))


def leaderboard_rows(symbol: str, day: str, source: str, closes: list[float], board: str = "gainers") -> None:
    rows = [make_row(symbol=symbol, minute_ts=at(day, 9, 30) + 60 * i, board=board, source=source,
                     rank=1, price=5.0, prev_close=close) for i, close in enumerate(closes)]
    with lb_store.connect() as db:
        lb_store.write_batch(db, rows=rows)


def capture(root, day: str, symbol: str, quotes: list[dict] | None = None):
    directory = root / "sim_capture" / day / symbol
    directory.mkdir(parents=True)
    ts = at(day, 9, 45)
    (directory / "prints.jsonl").write_text(json.dumps(dict(ts=ts, symbol=symbol, price=9.41)) + "\n")
    if quotes:
        (directory / "quotes.jsonl").write_text("".join(json.dumps(dict(q, symbol=symbol)) + "\n" for q in quotes))
    return ts


# --- The two reported replays ------------------------------------------------


def test_whlr_historical_replay_reads_the_leaderboards_tick9_not_the_1559_close():
    stale_proxies("WHLR", "2026-09-22", minute_close=1.97, daily_close=3.5514)
    leaderboard_rows("WHLR", "2026-09-23", "recorded", [1.87, 1.87, 1.87])
    spec = history_store.window("WHLR", "2026-09-23", "04:00", "09:30")
    history_store.create(spec, "trades")
    history_playback.select(spec)
    assert history_playback.snapshot("WHLR")["prev_close"] == 1.87


def test_grml_capture_replay_reads_the_rebuilt_prior_close_not_the_after_hours_daily(isolated):
    stale_proxies("GRML", "2026-09-19", minute_close=2.90, daily_close=4.51)
    leaderboard_rows("GRML", "2026-09-21", "reconstructed", [2.85, 2.85], board="market")
    ts = capture(isolated, "2026-09-21", "GRML")
    assert capture_player.load("2026-09-21", "GRML")["ok"]
    assert capture_player.snapshot().prev_close == 2.85
    # Every reader of the loaded capture states the same close (#542).
    assert capture_player.quote_at(ts)["prev_close"] == 2.85
    change = 9.41 / capture_player.snapshot().prev_close - 1
    assert round(change * 100) == 230


def test_a_recorded_tick9_wins_over_the_leaderboard(isolated):
    leaderboard_rows("GRML", "2026-09-21", "reconstructed", [2.85])
    ts = at("2026-09-21", 9, 40)
    capture(isolated, "2026-09-21", "GRML", quotes=[
        # Before 04:00 a line can still carry the close before; it does not count.
        dict(ts=at("2026-09-21", 3, 0), bid=2.8, ask=2.9, prev_close=4.10),
        dict(ts=ts, bid=9.3, ask=9.4, prev_close=2.86),
        dict(ts=ts + 1, bid=9.3, ask=9.4, prev_close=2.86),
        dict(ts=ts + 2, bid=9.3, ask=9.4, prev_close=None),
    ])
    assert capture_player.load("2026-09-21", "GRML")["ok"]
    assert capture_player.snapshot().prev_close == 2.86


def test_no_leaderboard_row_and_no_regular_hours_close_is_a_stated_absence(isolated):
    stale_proxies("WHLR", "2026-09-22", minute_close=1.97, daily_close=3.5514)
    capture(isolated, "2026-09-23", "WHLR")
    assert capture_player.load("2026-09-23", "WHLR")["ok"]
    assert capture_player.snapshot().prev_close is None
    assert capture_player.replay_quote()["prev_close"] is None
    assert prior_close.previous_close("WHLR", "2026-09-23") is None


# --- Resolution order ---------------------------------------------------------


def test_recorded_rows_before_rebuilt_ones_and_the_days_most_common_value():
    leaderboard_rows("WHLR", "2026-09-23", "reconstructed", [1.80])
    leaderboard_rows("WHLR", "2026-09-23", "recorded", [1.87, 1.87, 1.99], board="gappers")
    assert prior_close.previous_close("whlr", "2026-09-23") == 1.87
    assert prior_close.previous_close("WHLR", "2026-09-22") is None
    assert prior_close.previous_close("OTHER", "2026-09-23") is None


def test_the_downloads_regular_hours_close_answers_when_the_leaderboard_cannot():
    spec = history_store.window("IMCC", "2026-09-18", "04:00", "09:30")
    job = history_store.create(spec, "trades")
    history_store.update(job["id"], prior_close=dict(close=3.21, date="2026-09-17", source="ibkr_rth_daily"))
    assert prior_close.previous_close("IMCC", "2026-09-18") == 3.21
    leaderboard_rows("IMCC", "2026-09-18", "recorded", [3.25])
    assert prior_close.previous_close("IMCC", "2026-09-18") == 3.25


def test_a_recorded_value_short_circuits_every_store(monkeypatch):
    def refuse(*_a, **_k):
        raise AssertionError("no store is read once the recording answers")
    monkeypatch.setattr(lb_store, "day_prev_close", refuse)
    assert prior_close.previous_close("GRML", "2026-09-21", recorded=2.86) == 2.86


def test_an_unreadable_store_degrades_to_none_and_says_so(monkeypatch, caplog):
    def broken(*_a, **_k):
        raise RuntimeError("disk gone")
    monkeypatch.setattr(history_store, "prior_close", broken)
    with caplog.at_level(logging.WARNING):
        assert prior_close.previous_close("GRML", "2026-09-21") is None
    assert "prior close unread" in caplog.text


# --- The leaderboard read ------------------------------------------------------


def test_reading_an_absent_leaderboard_creates_nothing():
    assert not lb_store.path().exists()
    assert lb_store.day_prev_close("2026-09-23", "WHLR") is None
    assert not lb_store.path().exists() and not lb_store.root().exists()


def test_a_newer_leaderboard_schema_is_refused_and_logged(caplog):
    leaderboard_rows("WHLR", "2026-09-23", "recorded", [1.87])
    db = sqlite3.connect(lb_store.path())
    try:
        db.execute("PRAGMA user_version=99")
    finally:
        db.close()
    with caplog.at_level(logging.WARNING):
        assert lb_store.day_prev_close("2026-09-23", "WHLR") is None
    assert "prior close unread" in caplog.text


def test_a_store_not_yet_migrated_is_read_as_found():
    """A version-1 store (before #498's catalyst tables) still answers; the read never migrates it."""
    leaderboard_rows("WHLR", "2026-09-23", "recorded", [1.87])
    db = sqlite3.connect(lb_store.path())
    try:
        db.execute("DROP TABLE catalyst_items")
        db.execute("DROP TABLE catalyst_checks")
        db.execute("PRAGMA user_version=1")
        db.commit()
    finally:
        db.close()
    assert lb_store.day_prev_close("2026-09-23", "WHLR") == 1.87
    db = sqlite3.connect(lb_store.path())
    try:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 1
    finally:
        db.close()


def test_the_read_only_connection_never_writes():
    leaderboard_rows("WHLR", "2026-09-23", "recorded", [1.87])
    db = lb_store.read_only()
    try:
        with pytest.raises(sqlite3.OperationalError):
            db.execute("DELETE FROM rows")
    finally:
        db.close()


# --- The historical download stores IBKR's regular-hours prior close ----------


class Gateway:
    def __init__(self, closes):
        self.closes, self.asked = closes, []

    async def open(self, symbol):
        return {"conId": 7}

    async def daily_closes(self, day):
        self.asked.append(day)
        if isinstance(self.closes, Exception):
            raise self.closes
        return self.closes

    async def trades(self, cursor):
        return []

    async def bars(self, job):
        return [dict(t=utc_iso(job["start_ts"]), o=1, h=1, l=1, c=1, v=1)]

    def close(self):
        pass


def run_bars_job(symbol: str, day: str, gateway: Gateway) -> dict:
    job = history_store.create(history_store.window(symbol, day, "04:00", "04:10"), "bars")
    return asyncio.run(history_download.run(job["id"], gateway, threading.Event(), paced=False))


def test_a_download_stores_the_prior_sessions_regular_hours_close_once():
    gateway = Gateway([("2026-09-16", 30.0), ("2026-09-17", 31.5)])
    result = run_bars_job("IMCC", "2026-09-18", gateway)
    assert result["status"] == "complete" and gateway.asked == ["2026-09-18"]
    assert result["prior_close"] == {"close": 31.5, "date": "2026-09-17", "source": "ibkr_rth_daily"}
    assert prior_close.previous_close("IMCC", "2026-09-18") == 31.5
    # A resumed run does not ask again.
    history_store.update(result["id"], status="paused")
    asyncio.run(history_download.run(result["id"], gateway, threading.Event(), paced=False))
    assert gateway.asked == ["2026-09-18"]


def test_a_series_missing_the_prior_session_stores_no_older_close():
    result = run_bars_job("IPOX", "2026-09-18", Gateway([("2026-09-15", 4.0)]))
    assert result["status"] == "complete" and result["prior_close"] is None
    assert prior_close.previous_close("IPOX", "2026-09-18") is None


@pytest.mark.parametrize("answer", [TimeoutError("no answer"), []])
def test_a_failed_or_empty_answer_never_fails_the_download_and_is_asked_again(answer, caplog):
    with caplog.at_level(logging.WARNING):
        result = run_bars_job("SLOW", "2026-09-18", Gateway(answer))
    assert result["status"] == "complete" and "prior_close" not in result
    assert "SLOW" in caplog.text


def test_recorded_close_ignores_non_numbers_and_ties_go_to_the_later_value():
    day = "2026-09-21"
    t = at(day, 9, 30)
    rows = [dict(ts=t, prev_close=2.85), dict(ts=t + 1, prev_close="2.9"), dict(ts=t + 2, prev_close=True),
            dict(ts=t + 3, prev_close=float("nan")), dict(ts=t + 4, prev_close=2.86)]
    assert prior_close.recorded_close(rows, day) == 2.86
    assert prior_close.recorded_close([], day) is None
