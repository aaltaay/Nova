"""SSR and halts, as the short check reads them (ADR 048 1.8 and 1.10)."""
from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from short_sale import halts, ssr

ET = ZoneInfo("America/New_York")


def _ts(day: str, hhmm: str) -> float:
    return datetime.fromisoformat(f"{day}T{hhmm}:00").replace(tzinfo=ET).timestamp()


# -- SSR ------------------------------------------------------------------------------------------
def test_a_trade_at_90_percent_of_the_prior_close_puts_ssr_on():
    got = ssr.judge(symbol="FADE", prior_close=5.60, seen=[5.04, 4.66], today_complete=False,
                    yesterday_low=None, yesterday_prior=None, why_unknown="x")
    assert got.state == "on" and got.since == "today" and got.trigger == pytest.approx(5.04)
    assert got.effective_on and "4.66" in got.text


def test_yesterdays_trigger_carries_into_today():
    got = ssr.judge(symbol="FADE", prior_close=4.80, seen=[4.70], today_complete=True,
                    yesterday_low=4.66, yesterday_prior=5.60, why_unknown="x")
    assert got.state == "on" and got.since == "yesterday"


def test_off_only_when_today_and_yesterday_are_both_known_clear():
    clear = dict(symbol="ABC", prior_close=10.0, seen=[9.5], yesterday_low=9.4, yesterday_prior=10.0, why_unknown="x")
    assert ssr.judge(today_complete=True, **clear).state == "off"
    unknown = ssr.judge(today_complete=False, **clear)
    assert unknown.state == "unknown" and unknown.effective_on
    assert ssr.judge(today_complete=True, **{**clear, "yesterday_low": None}).state == "unknown"


def test_the_live_read_needs_the_daily_bar_read_after_0930_and_the_day_low(monkeypatch):
    from ibkr import ticks

    now = _ts("2026-10-07", "10:15")
    monkeypatch.setattr(ticks, "last_quotes", lambda syms: {"ABC": {"price": 9.6, "prev_close": 10.0}})
    monkeypatch.setattr(ticks, "get_ticker", lambda sym: SimpleNamespace(low=9.3))
    monkeypatch.setattr(ssr, "_stored_low", lambda *a: None)
    ssr.reset_for_tests()
    ssr.remember_history_for_tests("ABC", {
        "day": "2026-10-07", "fetched_at": _ts("2026-10-07", "09:40"), "error": None,
        "all": [{"date": "2026-10-06", "low": 9.2}, {"date": "2026-10-07", "low": 9.4}],
        "rth": [{"date": "2026-10-05", "close": 9.8}, {"date": "2026-10-06", "close": 10.0}]})
    got = ssr.live("ABC", now)
    assert got.state == "off" and got.low == 9.3
    ssr.remember_history_for_tests("ABC", {
        "day": "2026-10-07", "fetched_at": _ts("2026-10-07", "09:10"), "error": None,
        "all": [{"date": "2026-10-06", "low": 9.2}, {"date": "2026-10-07", "low": 9.4}],
        "rth": [{"date": "2026-10-05", "close": 9.8}]})
    assert ssr.live("ABC", now).state == "unknown"    # read before 09:30: the premarket is not covered
    ssr.reset_for_tests()


def test_a_replay_is_on_when_its_prints_reach_the_trigger_and_otherwise_unknown(monkeypatch):
    import sim.prior_close as prior

    monkeypatch.setattr(prior, "previous_close", lambda sym, day, **k: 5.60)
    at = _ts("2026-09-22", "10:00")
    assert ssr.replay("FADE", at, "2026-09-22", lambda s, a, b: [(at - 60, 5.10), (at - 30, 5.00)]).state == "on"
    assert ssr.replay("FADE", at, "2026-09-22", lambda s, a, b: [(at - 60, 5.30)]).state == "unknown"


# -- Halts ----------------------------------------------------------------------------------------
@pytest.fixture
def feeds(monkeypatch):
    from ibkr import halt_status, nasdaq_halt_feed
    from luld import live as luld_live

    state = SimpleNamespace(halted=False, resume=None, rss=None, answering=True, clear_since=None, side=None)
    monkeypatch.setattr(halt_status, "halted_now", lambda syms, now=None: {s: state.halted for s in syms})
    monkeypatch.setattr(halt_status, "snapshot", lambda sym, now=None: {"halt_start": 100.0})
    monkeypatch.setattr(halt_status, "last_resume", lambda sym: state.resume)
    monkeypatch.setattr(halt_status, "clear_since", lambda sym: state.clear_since)
    monkeypatch.setattr(nasdaq_halt_feed, "last_resume", lambda sym, now=None: state.rss)
    monkeypatch.setattr(nasdaq_halt_feed, "answering", lambda now=None: state.answering)
    monkeypatch.setattr(luld_live, "halt_side", lambda sym: state.side)
    monkeypatch.setattr(halts, "_bar_prices", lambda *a: [])
    return state


def test_halted_and_unknown_refuse(feeds):
    feeds.halted = True
    assert halts.live("RDYN", 1000.0).state == "halted"
    feeds.halted = None
    got = halts.live("RDYN", 1000.0)
    assert got.state == "unknown" and "cannot tell" in got.text


def test_an_up_halt_cools_off_for_ten_minutes_and_a_down_halt_does_not(feeds):
    feeds.resume = {"resumed_at": 1000.0, "halt_start": 700.0, "source": "ibkr"}
    feeds.side = {"start": 700.0, "side": "up"}
    got = halts.live("RDYN", 1300.0)
    assert got.state == "cooloff" and got.until == 1600.0 and got.side == "up"
    assert halts.live("RDYN", 1600.0).state == "clear"
    feeds.side = {"start": 700.0, "side": "down"}
    assert halts.live("RDYN", 1300.0).state == "clear"


def test_a_halt_nova_cannot_place_counts_as_up(feeds):
    feeds.rss = {"resumed_at": 1000.0, "halt_start": 700.0, "source": "nasdaq"}
    got = halts.live("RDYN", 1100.0)
    assert got.state == "cooloff" and "counts as up" in got.text


def test_prices_place_a_halt_when_luld_cannot():
    def rising(sym, a, b):
        return [(a + 10, 4.0), (b - 10, 4.6)]

    def falling(sym, a, b):
        return [(a + 10, 4.6), (b - 10, 4.0)]

    assert halts.direction("RDYN", 1000.0, prices=rising) == "up"
    assert halts.direction("RDYN", 1000.0, prices=falling) == "down"
    assert halts.direction("RDYN", None, prices=rising) is None


def test_no_resume_is_a_fact_only_while_the_halt_list_answers_or_the_line_watched_10_minutes(feeds):
    feeds.answering = False
    assert halts.live("RDYN", 1000.0).state == "unknown"
    feeds.clear_since = 300.0
    assert halts.live("RDYN", 1000.0).state == "clear"


def test_tick_49_remembers_the_resumption_and_since_when_it_read_trading():
    from ibkr import halt_status

    halt_status.reset()
    halt_status.observe_code("RDYN", 0, now=100.0)
    assert halt_status.clear_since("RDYN") == 100.0 and halt_status.last_resume("RDYN") is None
    halt_status.observe_code("RDYN", 2, now=200.0)
    assert halt_status.clear_since("RDYN") is None
    halt_status.observe_code("RDYN", 0, now=500.0)
    resumed = halt_status.last_resume("RDYN")
    assert resumed["resumed_at"] == 500.0 and resumed["halt_start"] == 200.0
    assert halt_status.clear_since("RDYN") == 500.0
    halt_status.reset()


def test_a_replay_reads_the_days_halt_log_at_the_playhead(monkeypatch):
    from leaderboard import store as lb_store

    events = [{"symbol": "RDYN", "ts": 1000.0, "event": "start"}, {"symbol": "RDYN", "ts": 1300.0, "event": "end"}]

    class DB:
        def close(self):
            pass

    monkeypatch.setattr(lb_store, "read_only", lambda database=None: DB())
    monkeypatch.setattr(lb_store, "halt_events", lambda db, day, until=None, symbols=None:
                        [e for e in events if until is None or e["ts"] <= until])
    assert halts.replay("RDYN", 1100.0, "2026-09-22").state == "halted"
    assert halts.replay("RDYN", 1400.0, "2026-09-22").state == "cooloff"   # placed nowhere: counts as up
    assert halts.replay("RDYN", 1950.0, "2026-09-22").state == "clear"
    monkeypatch.setattr(lb_store, "halt_events", lambda *a, **k: [])
    assert halts.replay("RDYN", 1950.0, "2026-09-22").state == "unknown"
