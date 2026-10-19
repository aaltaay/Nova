"""Nova's trading day (04:00 ET, weekends and holidays walk back: ``market.session_key_et``) governs every
"today" that was once the ET calendar date: the news window, the NEWS badge cache, the stock read's
"yesterday", the average-volume cache day. Clocks: Mon 00:30, Mon 10:00, Mon 21:00 and Sat 10:00 ET
(2026-10-19 is a Monday; Friday 2026-10-16's session is on screen until Monday 04:00).
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

import market
import scanner
import scanner_news_badge as snb
import ticker_alpaca
from stock_read import history, level_map

ET = ZoneInfo("America/New_York")


def at(day: str, hh: int, mm: int = 0) -> datetime:
    return datetime.fromisoformat(f"{day}T{hh:02d}:{mm:02d}:00").replace(tzinfo=ET)


MON_0030 = at("2026-10-19", 0, 30)      # still Friday's session
MON_1000 = at("2026-10-19", 10)
MON_2100 = at("2026-10-19", 21)
SAT_1000 = at("2026-10-17", 10)
THU_16_UTC = "2026-10-15T20:00:00Z"     # Thursday 16:00 ET (EDT = UTC-4)
FRI_16_UTC = "2026-10-16T20:00:00Z"
CLOCKS = [(MON_0030, THU_16_UTC), (MON_1000, FRI_16_UTC), (MON_2100, FRI_16_UTC), (SAT_1000, THU_16_UTC)]


def freeze(monkeypatch, when: datetime) -> None:
    """``market.now_et`` is the one clock the session helpers read (``datetime.now`` ignores ``time.time``)."""
    monkeypatch.setattr(market, "now_et", lambda: when)


class _Resp:
    status_code = 200

    @staticmethod
    def json():
        return {"news": [], "bars": {}}


@pytest.mark.parametrize("when,expected", CLOCKS + [
    (at("2026-11-27", 10), "2026-11-25T21:00:00Z"),   # day after Thanksgiving: Wednesday 16:00 EST (UTC-5)
])
def test_news_window_starts_at_the_previous_exchange_close(when, expected):
    # Mon 00:30: Friday's session is on screen, its news began at Thursday's close. Mon 10:00: Friday evening
    # and the weekend. Mon 21:00: the 16:00-20:00 releases stay. Sat 10:00: Friday's window all weekend.
    assert market.news_window_start_param(when) == expected


@pytest.mark.parametrize("when,expected", CLOCKS)
def test_scanner_news_lookup_sends_the_window(monkeypatch, when, expected):
    freeze(monkeypatch, when)
    sent: dict = {}

    def fake_get(_name, _url, **kw):
        sent.update(kw["params"])
        return _Resp()

    monkeypatch.setattr(scanner.http_pool, "get", fake_get)
    scanner._check_news(["ABC"], {"k": "v"})
    # Alpaca reads a bare date as 00:00 UTC (probed 2026-10-19), 20:00 ET the evening before.
    assert sent["start"] == expected and "T" in sent["start"]


@pytest.mark.parametrize("when,expected", CLOCKS)
def test_ticker_news_lookup_sends_the_window(monkeypatch, when, expected):
    freeze(monkeypatch, when)
    sent: dict = {}

    def fake_get(_url, **kw):
        sent.update(kw["params"])
        return _Resp()

    monkeypatch.setattr(ticker_alpaca.requests, "get", fake_get)
    ticker_alpaca.fetch_ticker_news("ABC", {"k": "v"})
    assert sent["start"] == expected


def test_badge_cache_keeps_the_sessions_headlines_through_midnight_and_the_weekend(monkeypatch):
    snb.reset_for_testing()
    freeze(monkeypatch, at("2026-10-16", 21))
    snb.record({"ABC": "2026-10-16T21:30:00Z"})          # a 17:30 ET earnings release
    assert snb.headline_for("ABC") == "2026-10-16T21:30:00Z"
    for when in (at("2026-10-17", 0, 5), MON_0030, SAT_1000, at("2026-10-19", 3, 59)):
        freeze(monkeypatch, when)
        assert snb.headline_for("ABC") == "2026-10-16T21:30:00Z", when
    freeze(monkeypatch, at("2026-10-19", 4))             # Monday's session opens: the cache starts over
    assert snb.headline_for("ABC") is None


def _daily(d: str, high: float, low: float) -> dict:
    return {"d": d, "o": low, "h": high, "l": low, "c": high, "v": 1_000, "state": "final", "through": None}


def _yday_highs(lm: dict) -> list[float]:
    return [m["price"] for z in lm["intraday"] for m in z["members"] if m["kind"] == "yday_high"]


@pytest.mark.parametrize("when", [MON_0030, SAT_1000])
def test_yesterday_is_the_session_before_the_one_on_screen(when):
    """Friday's session is on screen: its own daily bar (the day's high) is not "yesterday's"."""
    daily = [_daily("2026-10-15", 6.0, 5.0), _daily("2026-10-16", 99.0, 1.0)]
    bars = [{"t": at("2026-10-16", 9, 30).timestamp(), "o": 7, "h": 7.1, "l": 6.9, "c": 7.0, "v": 1000}]
    lm = level_map.build(bars, daily, price=7.0, prior_close=6.0, vwap=7.0, now=when.timestamp())
    assert _yday_highs(lm) == [6.0]


def test_yesterday_on_monday_is_friday():
    daily = [_daily("2026-10-15", 6.0, 5.0), _daily("2026-10-16", 8.0, 7.0)]
    bars = [{"t": MON_1000.timestamp() - 3600, "o": 7, "h": 7.1, "l": 6.9, "c": 7.0, "v": 1000}]
    lm = level_map.build(bars, daily, price=7.0, prior_close=8.0, vwap=7.0, now=MON_1000.timestamp())
    assert _yday_highs(lm) == [8.0]


@pytest.mark.parametrize("when,fridays_is_today", [(MON_0030, True), (SAT_1000, True), (MON_1000, False)])
def test_the_daily_history_marks_the_session_on_screen_as_today(monkeypatch, when, fridays_is_today):
    def stored(d: str, high: float) -> dict:
        t = datetime.fromisoformat(d).replace(tzinfo=ZoneInfo("UTC")).timestamp()
        return {"t": t, "o": 5.0, "h": high, "l": 4.0, "c": 5.0, "v": 1e6}

    bars = [stored("2026-10-14", 5.0), stored("2026-10-15", 5.0), stored("2026-10-16", 9.0)]
    monkeypatch.setattr("sensors.feeds.get_bars", lambda sym, tf, limit, **_k: (bars, "ibkr"))
    monkeypatch.setattr("bars_store.daily_bar_state", lambda t, w, now: "final")
    history._cache.clear()
    out = history.summary("ABC", when.timestamp())
    run = next(r for r in out["runs"] if r["date"] == "2026-10-16")
    assert run["today"] is fridays_is_today
    assert out["sma200"] is None and out["unfinished"] == []


def test_the_average_volume_cache_day_is_the_trading_day(monkeypatch):
    import universe
    from runtime_state import get_runtime_state

    monkeypatch.setattr(universe, "fetch_avg_volume_batch", lambda syms, headers, cache: None)
    state = get_runtime_state()
    state.avg_volume_cache, state.avg_volume_date = {"ABC": 1.0}, ""
    freeze(monkeypatch, at("2026-10-16", 21))
    universe.ensure_avg_volume(["ABC"], {})
    assert state.avg_volume_date == "2026-10-16"
    state.avg_volume_cache["ABC"] = 2.0
    freeze(monkeypatch, MON_0030)                        # past midnight, still Friday's session: the cache stays
    universe.ensure_avg_volume(["ABC"], {})
    assert state.avg_volume_cache == {"ABC": 2.0}
    freeze(monkeypatch, MON_1000)
    universe.ensure_avg_volume(["ABC"], {})
    assert state.avg_volume_cache == {} and state.avg_volume_date == "2026-10-19"


def test_the_avg_volume_bars_window_ends_on_the_trading_day(monkeypatch):
    freeze(monkeypatch, SAT_1000)
    sent: dict = {}

    def fake_get(_url, **kw):
        sent.update(kw["params"])
        return _Resp()

    monkeypatch.setattr(scanner.requests, "get", fake_get)
    scanner.fetch_avg_volume_batch(["ABC"], {"k": "v"}, {})
    assert sent["end"] == "2026-10-16" and sent["start"] == "2026-09-01"
