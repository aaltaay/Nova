"""A review day the Massive files do not hold is read from the desk's IBKR candles, or refused with the reason.

2026-11-18: ``nova_chart`` for HIHO that morning answered ``REVIEW_SHOT_FAILED`` after 25 s. The files ended on
2026-10-16, the route answered HTTP 500, the page drew nothing and the screenshot waited for a paint that
could not come. These tests pin the desk reader, the one-source rule, and the 404 that names why.
"""
from __future__ import annotations

import json
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import nova_review_desk as desk  # noqa: E402
import nova_review_http as review_http  # noqa: E402
import nova_review_load as review_load  # noqa: E402

DAY = "2026-11-18"          # Eastern Standard Time: 09:17 ET is 14:17Z


def _bar(stamp: str, price: float, volume: int = 100) -> dict:
    return {"t": stamp, "o": price, "h": price + 0.02, "l": price - 0.01, "c": price + 0.01, "v": volume}


SERIES = {
    "1Min": [
        _bar("2026-11-17T20:59:00Z", 1.10),            # the day before: never on the page
        _bar("2026-11-18T14:17:00Z", 1.92),
        _bar("2026-11-18T14:18:00Z", 1.96),
        _bar("2026-11-18T14:30:00Z", 1.80),            # 09:30 ET, after a 09:25 cut
    ],
    "5Min": [_bar("2026-11-18T14:15:00Z", 1.90), _bar("2026-11-18T14:25:00Z", 1.85)],
    "10Sec": [_bar("2026-11-18T14:17:30Z", 1.92)],
    "1Day": [_bar("2026-11-17T00:00:00Z", 1.20), _bar("2026-11-18T00:00:00Z", 1.50)],
}


def _desk(series=None, *, source="ibkr", coverage=None):
    held = SERIES if series is None else series
    asked = []

    def fetch(url: str) -> dict:
        asked.append(url)
        timeframe = url.split("timeframe=")[1].split("&")[0]
        return {"symbol": "HIHO", "timeframe": timeframe, "bars": held.get(timeframe, []), "source": source,
                "coverage": coverage or {"filling": False, "history_pending": False}}

    fetch.asked = asked
    return fetch


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(desk, "sleep", lambda _sec: None)


def _no_file(*_args):
    raise LookupError(f"no minute_aggs_v1 file for {DAY}")


def test_desk_bars_keep_only_the_asked_eastern_day(monkeypatch):
    monkeypatch.setattr(desk, "fetch_json", _desk())
    rows = desk.desk_bars("HIHO", DAY, "1m")
    assert [row["time_et"].strftime("%Y-%m-%d %H:%M") for row in rows] == [
        f"{DAY} 09:17", f"{DAY} 09:18", f"{DAY} 09:30"]
    assert rows[0]["open"] == 1.92 and rows[0]["volume"] == 100
    assert [row["date"] for row in desk.desk_daily("HIHO", "2026-05-19", DAY)] == ["2026-11-17", DAY]


def test_a_day_without_files_is_drawn_from_the_desk_and_says_so(monkeypatch):
    monkeypatch.setattr(desk, "fetch_json", _desk())
    body = review_load.load_review("hiho", DAY, None, "09:25", bars_reader=_no_file,
                                   daily_reader=_no_file, fallback=desk.READERS)
    assert body["source"] == "desk-ibkr"
    assert {tf: frame["source"] for tf, frame in body["timeframes"].items()} == {
        "1m": "ibkr-history", "5m": "ibkr-history", "10s": "ibkr-history", "1d": "ibkr-daily"}
    # The 09:25 cut still holds: the 09:30 minute and the 09:25 five-minute bar are not on the page.
    assert [bar["t"][11:16] for bar in body["timeframes"]["1m"]["bars"]] == ["09:17", "09:18"]
    assert [bar["t"][11:16] for bar in body["timeframes"]["5m"]["bars"]] == ["09:15"]
    assert body["levels"]["prior_close"] == pytest.approx(1.21)
    # The day's own daily candle is its minutes, never IBKR's official row for a day still trading.
    assert body["timeframes"]["1d"]["bars"][-1] == {"t": DAY, "o": 1.92, "h": 1.98, "l": 1.91, "c": 1.97, "v": 200.0}


def test_the_files_win_when_they_hold_the_day(monkeypatch):
    def never(_url):
        raise AssertionError("the desk was asked although the files hold the day")

    monkeypatch.setattr(desk, "fetch_json", never)
    body = review_load.load_review("hiho", DAY, ["1m"], "09:25", bars_reader=lambda *_a: [],
                                   daily_reader=lambda *_a: [], fallback=desk.READERS)
    assert body["source"] == "front-door"


def test_a_sim_replay_on_the_desk_is_refused_not_drawn(monkeypatch):
    monkeypatch.setattr(desk, "fetch_json", _desk(source="sim_replay"))
    with pytest.raises(LookupError, match="not showing IBKR's live history"):
        desk.desk_bars("HIHO", DAY, "1m")


def test_a_queued_fill_is_waited_for(monkeypatch):
    answers = [
        {"bars": [], "source": "ibkr", "coverage": {"filling": True, "history_pending": True}},
        {"bars": [_bar("2026-11-17T20:59:00Z", 1.10)], "source": "ibkr", "coverage": {"filling": True}},
        {"bars": SERIES["1Min"], "source": "ibkr", "coverage": {"filling": False}},
    ]
    monkeypatch.setattr(desk, "fetch_json", lambda _url: answers.pop(0))
    assert len(desk.desk_bars("HIHO", DAY, "1m")) == 3
    assert answers == []


def test_a_day_the_desk_does_not_hold_names_both_reasons(monkeypatch):
    monkeypatch.setattr(desk, "fetch_json", _desk({"1Min": [_bar("2026-11-17T20:59:00Z", 1.10)]}))
    with pytest.raises(LookupError) as caught:
        review_load.load_review("hiho", DAY, None, "09:25", bars_reader=_no_file, daily_reader=_no_file,
                                fallback=desk.READERS)
    text = str(caught.value)
    assert "no minute_aggs_v1 file" in text and "holds no IBKR 1-minute candle of HIHO" in text


def test_a_desk_that_is_down_says_so(monkeypatch):
    monkeypatch.setenv("NOVA_API_BASE", "http://127.0.0.1:9")      # the discard port: nothing listens
    monkeypatch.setattr(desk, "fetch_json", desk._http_json)
    with pytest.raises(desk.DeskUnavailable, match="did not answer"):
        desk.desk_series("HIHO", "1Min")


def test_no_data_is_http_404_with_a_code_and_a_passed_reader_gets_no_fallback(monkeypatch):
    def never(_url):
        raise AssertionError("a reader passed in must not reach the desk")

    monkeypatch.setattr(desk, "fetch_json", never)
    httpd = review_http.serve(0, bars_reader=_no_file, daily_reader=lambda *_a: [])
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{httpd.server_address[1]}/api/review?symbol=HIHO&date={DAY}&as_of=09:25"
        with pytest.raises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(url)
        assert caught.value.code == 404
        body = json.loads(caught.value.read().decode())
        assert body["ok"] is False and body["code"] == "REVIEW_NO_DATA" and "no minute_aggs_v1 file" in body["error"]
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_only_the_front_door_itself_falls_back_to_the_desk():
    assert review_http.default_fallback(None) == desk.READERS
    assert review_http.default_fallback(lambda *_a: []) is None
