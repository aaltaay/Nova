"""Followed traders (``backend/followed_traders``, operator ask 2026-10-13): the feed's day read field by field,
per-share P/L, exits from IBKR's history, the lines it holds, the routes, and the gate that keeps it all off
unless ``NOVA_FOLLOW_FEED_URL`` is set. Schema: architecture/schema/followed-traders.md.
"""
from __future__ import annotations

import asyncio
import copy
import json
import time
from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from followed_traders import config, exits, feed, lines, pricing, routes, scoring, view
from followed_traders.constants_followed import FOLLOWED_FEED_URL_ENV, FOLLOWED_MAX_LINES
from sim.session_clock import ET

BASE = "http://127.0.0.1:8787"


def _ts(clock: str, date: str = "2026-10-13") -> str:
    return f"{date}T{clock}-04:00"


def _epoch(clock: str, date: str = "2026-10-13") -> float:
    return datetime.fromisoformat(_ts(clock, date)).timestamp()


def _trade(trader="ALPHA", side="long", symbol="ABCD", entry=2.00, price=None, entry_clock="10:00:00",
           status="open", exit_clock=None, exit_since=None, entry_since=None, known=True, adds=()):
    return {
        "trader": trader, "side": side, "symbol": symbol, "entry_price": entry,
        "price": entry if price is None else price,
        "entry_ts": _ts(entry_clock), "entry_since_ts": _ts(entry_since) if entry_since else None,
        "entry_known": known, "adds": [{"ts": _ts(c), "price": p, "prev_price": q} for c, p, q in adds],
        "exit_ts": _ts(exit_clock) if exit_clock else None,
        "exit_since_ts": _ts(exit_since) if exit_since else None, "status": status,
        "entry_evidence": "frames/" + "a" * 32 + ".jpg",
        "exit_evidence": ("frames/" + "b" * 32 + ".jpg") if exit_clock else None,
    }


def _raw_day(trades=None, date="2026-10-13", today="2026-10-13"):
    return {
        "date": date, "today": today, "dates": [today],
        "status": {"video": {"id": "x", "title": "Morning show"}, "live": True, "clock": "10:30:00",
                   "updated_at": _ts("10:30:05"), "bar_visible": True, "traders": ["ALPHA", "BRAVO"],
                   "positions": {}},
        "trades": trades if trades is not None else [_trade()],
        "events": [{"type": "open", "anything": "ignored"}],
    }


@pytest.fixture(autouse=True)
def _clean(monkeypatch, tmp_path):
    exits.reset_for_tests()
    lines.reset_for_tests()
    monkeypatch.delenv(FOLLOWED_FEED_URL_ENV, raising=False)
    monkeypatch.setattr(exits, "_path", lambda: tmp_path / "followed-exits.json")
    yield
    exits.reset_for_tests()
    lines.reset_for_tests()


# -- the gate ---------------------------------------------------------------------------------------


def test_unset_is_off(monkeypatch):
    assert config.feed_url() is None and not config.enabled()
    monkeypatch.setenv(FOLLOWED_FEED_URL_ENV, "   ")
    assert not config.enabled()


def test_url_is_trimmed_and_must_be_http(monkeypatch):
    monkeypatch.setenv(FOLLOWED_FEED_URL_ENV, " http://127.0.0.1:8787/ ")
    assert config.feed_url() == BASE
    monkeypatch.setenv(FOLLOWED_FEED_URL_ENV, "file:///etc/passwd")
    assert config.feed_url() is None
    monkeypatch.setenv(FOLLOWED_FEED_URL_ENV, "127.0.0.1:8787")
    assert config.feed_url() is None


def _paths(app: FastAPI) -> set[str]:
    return {getattr(r, "path", "") for r in app.routes}


def test_no_route_without_the_env(monkeypatch):
    from app_routers import register_routers

    off = FastAPI()
    register_routers(off)
    assert not any(p.startswith("/api/followed-traders") for p in _paths(off))
    monkeypatch.setenv(FOLLOWED_FEED_URL_ENV, BASE)
    on = FastAPI()
    register_routers(on)
    assert "/api/followed-traders/day" in _paths(on)
    assert "/api/followed-traders/config" in _paths(on)


def test_the_desk_app_has_no_route_by_default():
    from main import app

    assert not any(p.startswith("/api/followed-traders") for p in _paths(app))


# -- the feed's day, field by field -----------------------------------------------------------------


def test_parse_day_reads_times_as_epoch_and_ignores_unread_fields():
    raw = _raw_day([_trade(status="closed", exit_clock="10:05:00", exit_since="10:04:00",
                           adds=[("10:01:00", 2.10, 2.00)], price=2.10)])
    day = feed.parse_day(raw)
    t = day["trades"][0]
    assert t["entry_ts"] == _epoch("10:00:00")
    assert t["exit_ts"] == _epoch("10:05:00") and t["exit_since_ts"] == _epoch("10:04:00")
    assert t["adds"] == [{"ts": _epoch("10:01:00"), "price": 2.10, "prev_price": 2.00}]
    assert day["status"]["title"] == "Morning show" and day["status"]["updated_at"] == _epoch("10:30:05")
    assert "events" not in day


def test_parse_day_status_may_be_null():
    raw = _raw_day()
    raw["status"] = None
    assert feed.parse_day(raw)["status"] is None


@pytest.mark.parametrize("mutate, field", [
    (lambda d: d.pop("trades"), "trades"),
    (lambda d: d["trades"][0].pop("entry_known"), "trades[0].entry_known"),
    (lambda d: d["trades"][0].update(side="flat"), "trades[0].side"),
    (lambda d: d["trades"][0].update(status="maybe"), "trades[0].status"),
    (lambda d: d["trades"][0].update(entry_price="2.00"), "trades[0].entry_price"),
    (lambda d: d["trades"][0].update(entry_ts="2026-10-13T10:00:00"), "trades[0].entry_ts"),
    (lambda d: d["trades"][0].update(adds=[{"ts": _ts("10:01:00")}]), "trades[0].adds[0].price"),
    (lambda d: d.update(date="13/10/2026"), "date"),
    (lambda d: d["status"].pop("bar_visible"), "status.bar_visible"),
])
def test_parse_day_names_the_field_it_cannot_read(mutate, field):
    raw = _raw_day()
    mutate(raw)
    with pytest.raises(feed.FeedError) as err:
        feed.parse_day(raw)
    assert err.value.state == "bad_answer"
    assert str(err.value).startswith(field)


def test_evidence_name_takes_only_the_feeds_frames():
    assert feed.evidence_name("frames/" + "0f" * 16 + ".jpg") == "0f" * 16
    for bad in (None, "", "../status.json", "frames/../../x.jpg", "frames/ABC.jpg", "latest.jpg"):
        assert feed.evidence_name(bad) is None


class _Resp:
    def __init__(self, status=200, body=None, chunks=()):
        self.status_code, self._body, self._chunks = status, body, chunks

    def json(self):
        if isinstance(self._body, Exception):
            raise self._body
        return self._body

    def iter_content(self, _n):
        return iter(self._chunks)

    def close(self):
        pass


def test_fetch_day_states_why_the_feed_did_not_answer(monkeypatch):
    import requests

    def boom(*_a, **_k):
        raise requests.ConnectionError("refused")

    monkeypatch.setattr(feed.http_pool, "get", boom)
    with pytest.raises(feed.FeedError) as err:
        feed.fetch_day(BASE, None)
    assert err.value.state == "unreachable" and "could not connect" in str(err.value)

    monkeypatch.setattr(feed.http_pool, "get", lambda *_a, **_k: _Resp(status=500))
    with pytest.raises(feed.FeedError, match="HTTP 500"):
        feed.fetch_day(BASE, None)

    monkeypatch.setattr(feed.http_pool, "get", lambda *_a, **_k: _Resp(body=ValueError("x")))
    with pytest.raises(feed.FeedError) as err:
        feed.fetch_day(BASE, None)
    assert err.value.state == "bad_answer"


def test_fetch_day_asks_the_date(monkeypatch):
    seen = {}

    def get(_pool, url, **kw):
        seen.update(url=url, params=kw["params"])
        return _Resp(body=_raw_day())

    monkeypatch.setattr(feed.http_pool, "get", get)
    feed.fetch_day(BASE, "2026-10-12")
    assert seen == {"url": f"{BASE}/api/day", "params": {"date": "2026-10-12"}}


def test_fetch_evidence_caps_the_size(monkeypatch):
    monkeypatch.setattr(feed.http_pool, "get", lambda *_a, **_k: _Resp(chunks=[b"x" * (3 * 1024 * 1024)]))
    with pytest.raises(feed.FeedError, match="over"):
        feed.fetch_evidence(BASE, "2026-10-13", "a" * 32)


# -- per-share arithmetic -------------------------------------------------------------------------


def test_pl_long_and_short():
    assert pricing.pl_point("long", 2.00, 2.50) == {"per_share": 0.5, "pct": 25.0}
    assert pricing.pl_point("short", 2.00, 2.50) == {"per_share": -0.5, "pct": -25.0}
    assert pricing.pl_range("long", 10.0, 9.0, 11.0) == {
        "low_per_share": -1.0, "high_per_share": 1.0, "low_pct": -10.0, "high_pct": 10.0}
    assert pricing.pl_range("short", 10.0, 9.0, 11.0) == {
        "low_per_share": -1.0, "high_per_share": 1.0, "low_pct": -10.0, "high_pct": 10.0}
    assert pricing.pl_range("short", 10.0, 9.5, 9.8) == {
        "low_per_share": 0.2, "high_per_share": 0.5, "low_pct": 2.0, "high_pct": 5.0}


def test_held_states_what_it_cannot_know():
    assert pricing.held(1000.0, None, True, 1600.0) == {"min_sec": 600, "max_sec": 600}
    # entered somewhere in 900..1000, left somewhere in 1500..1600
    assert pricing.held(1000.0, 900.0, True, 1600.0, 1500.0) == {"min_sec": 500, "max_sec": 700}
    # already open when the feed started: only a floor
    assert pricing.held(1000.0, None, False, 1600.0) == {"min_sec": 600, "max_sec": None}


def _tick(ts, price, sets=True):
    return {"ts": float(ts), "price": price, "exchange": "X", "conditions": "", "sets_price": sets}


def test_exit_at_is_the_last_price_setting_trade_by_that_second():
    trades = [_tick(100, 1.00), _tick(105, 1.10), _tick(109, 9.99, sets=False), _tick(110, 1.20)]
    assert pricing.exit_at(trades, 109.7) == {"price": 1.10, "trade_ts": 105.0}
    assert pricing.exit_at(trades, 110.0) == {"price": 1.20, "trade_ts": 110.0}
    assert pricing.exit_at(trades, 99.0) is None


def test_ranges_from_trades_and_bars():
    trades = [_tick(99, 5.0), _tick(100, 1.0), _tick(150, 1.5), _tick(160, 0.1, sets=False), _tick(201, 9.0)]
    assert pricing.range_from_trades(trades, 100.4, 200.0) == (1.0, 1.5)
    assert pricing.range_from_trades(trades, 300.0, 400.0) is None

    t0 = _epoch("09:30:00")

    def bar(t, lo, hi, v=10):
        stamp = datetime.fromtimestamp(t0 + t).astimezone().isoformat()
        return {"t": stamp, "o": lo, "h": hi, "l": lo, "c": hi, "v": v}

    bars = [bar(0, 1.0, 2.0), bar(60, 1.5, 3.0), bar(120, 0.5, 4.0, v=0), bar(180, 0.9, 1.1)]
    assert pricing.range_from_bars(bars, t0 + 70, t0 + 130) == (1.5, 3.0)   # 120's bar has no volume
    assert pricing.range_from_bars(bars, t0 + 59, t0 + 181) == (0.9, 3.0)
    assert pricing.range_from_bars(bars, t0 + 500, t0 + 600) is None


def test_priceable_tickers():
    for ok in ("A", "ABCD", "BRK.B", "NVDL", "AB1"):
        assert pricing.priceable(ok)
    for bad in ("", "abcd", "TOOLONGX", "AB CD", "$X", "1ABC"):
        assert not pricing.priceable(bad)


# -- the answer ---------------------------------------------------------------------------------------


LIVE = {"state": "live", "why": None}


def _compose(trades, *, now=None, prices=LIVE, now_for=None, exit_for=None, **day_kw):
    day = feed.parse_day(_raw_day(trades, **day_kw))
    now = _epoch("10:30:10") if now is None else now
    return view.compose(day, now=now, prices=prices,
                        now_for=now_for or (lambda t: lines.now_state("live", price=2.50, trade_ts=now - 1)),
                        exit_for=exit_for or (lambda t: exits.stated("at", price=1.80, trade_ts=t["exit_ts"] - 2,
                                                                     to_ts=t["exit_ts"], source="ibkr_trades")))


def test_compose_groups_by_trader_with_open_and_closed():
    body = _compose([
        _trade("ALPHA", symbol="AAA", entry_clock="10:00:00"),
        _trade("BRAVO", side="short", symbol="BBB", entry_clock="10:01:00", status="closed", exit_clock="10:20:00"),
        _trade("ALPHA", symbol="CCC", entry_clock="10:02:00"),
        _trade("ALPHA", symbol="DDD", entry_clock="10:03:00", status="unknown"),
    ])
    assert body["feed"] == {"state": "ok", "error": None}
    assert [t["name"] for t in body["traders"]] == ["ALPHA", "BRAVO"]
    alpha, bravo = body["traders"]
    assert [r["symbol"] for r in alpha["open"]] == ["CCC", "AAA"]          # newest entry first
    assert alpha["open"][0]["pl"] == {"per_share": 0.5, "pct": 25.0}
    assert alpha["open"][0]["held"] == {"min_sec": 1690, "max_sec": 1690}
    unknown = alpha["closed"][0]
    assert unknown["exit"]["state"] == "unavailable" and "never saw it close" in unknown["exit"]["why"]
    assert unknown["pl"] is None and unknown["held"] == {"min_sec": None, "max_sec": None}
    short = bravo["closed"][0]
    assert short["exit"]["price"] == 1.80 and short["pl"] == {"per_share": 0.2, "pct": 10.0}
    assert short["now"] is None
    assert short["evidence"]["exit"] == "/api/followed-traders/evidence/2026-10-13/frames/" + "b" * 32 + ".jpg"
    assert body["capture"]["age_sec"] == 5.0 and body["capture"]["title"] == "Morning show"


def test_compose_against_the_average_after_adds():
    body = _compose([_trade(entry=2.00, price=2.20, adds=[("10:05:00", 2.20, 2.00)])])
    row = body["traders"][0]["open"][0]
    assert row["entry"]["first_price"] == 2.00 and row["entry"]["avg_price"] == 2.20
    assert row["pl"] == {"per_share": 0.3, "pct": 13.64}


def test_compose_a_window_exit_is_a_range():
    def exit_for(t):
        return exits.stated("range", low=1.70, high=1.90, from_ts=t["exit_since_ts"], to_ts=t["exit_ts"],
                            source="ibkr_trades")

    body = _compose([_trade(status="closed", exit_clock="10:20:00", exit_since="10:15:00")], exit_for=exit_for)
    row = body["traders"][0]["closed"][0]
    assert row["exit"]["price"] is None and (row["exit"]["low"], row["exit"]["high"]) == (1.70, 1.90)
    assert row["pl"] == {"low_per_share": -0.3, "high_per_share": -0.1, "low_pct": -15.0, "high_pct": -5.0}
    assert row["held"] == {"min_sec": 900, "max_sec": 1200}


def test_compose_off_live_prices_nothing_now():
    body = _compose([_trade()], prices={"state": "past_day", "why": "not today"})
    row = body["traders"][0]["open"][0]
    assert row["now"] == {"state": "off", "price": None, "trade_ts": None, "why": "not today"}
    assert row["pl"] is None


def test_feed_down_says_so_and_lists_nothing():
    body = view.feed_down("unreachable", "could not connect (ConnectionError)", None, 1.0)
    assert body["feed"] == {"state": "unreachable", "error": "could not connect (ConnectionError)"}
    assert body["traders"] == [] and body["capture"] is None and body["prices"] is None


# -- exits from IBKR's history ----------------------------------------------------------------------


def _run(coro):
    return asyncio.run(coro)


def test_exit_view_is_pending_until_read_then_kept(monkeypatch):
    sent = []
    key = ("ABCD", _epoch("10:20:00"), None)
    assert exits.view(*key, now=0.0)["state"] == "pending"
    exits.pump(0.0, ibkr_ready=False, spawn=lambda n, f: sent.append(n))
    assert sent == []                                    # IBKR not ready: nothing asked
    exits.pump(0.0, ibkr_ready=True, spawn=lambda n, f: sent.append(n))
    exits.pump(0.0, ibkr_ready=True, spawn=lambda n, f: sent.append(n))
    assert sent == ["followed.exit.ABCD"]                # one read in flight at a time
    got = exits.stated("at", price=1.5, to_ts=key[1], source="ibkr_trades")
    exits._finish(key, "done", got)
    assert exits.view(*key, now=1.0) == got


def test_exit_shed_waits_and_failures_end_unavailable(monkeypatch):
    monkeypatch.setattr(exits, "_clock", lambda: 100.0)
    key = ("ABCD", 5000.0, None)
    exits.view(*key, now=0.0)
    exits.pump(0.0, ibkr_ready=True, spawn=lambda n, f: None)
    exits._finish(key, "shed", "an open chart is loading")
    pending = exits.view(*key, now=101.0)
    assert pending["state"] == "pending" and "open chart" in pending["why"]
    for _ in range(3):
        exits.pump(10_000.0, ibkr_ready=True, spawn=lambda n, f: None)
        exits._finish(key, "failed", "ConnectionError: down")
    assert exits.view(*key, now=10_001.0)["state"] == "unavailable"


def test_exit_read_point_and_window(monkeypatch):
    from ibkr import historical_trades

    calls = []

    async def recent(symbol, end, back_sec, *, max_pages, headroom, timeout):
        calls.append((symbol, end, back_sec, max_pages))
        return {"trades": [_tick(end - 30, 2.0), _tick(end - 5, 2.1), _tick(end - 1, 1.9)], "since": end - back_sec,
                "complete": True, "pages": 1, "minutes": [], "minutes_note": None}

    monkeypatch.setattr(historical_trades, "recent_trades", recent)
    point = _run(exits.read(("ABCD", 1000.4, None)))
    assert point["state"] == "at" and point["price"] == 1.9 and point["trade_ts"] == 1000.0
    assert calls[-1] == ("ABCD", 1001.0, 600.0, 1)
    window = _run(exits.read(("ABCD", 1000.0, 960.0)))
    assert window["state"] == "range" and (window["low"], window["high"]) == (1.9, 2.1)
    assert window["source"] == "ibkr_trades" and window["price"] is None
    assert calls[-1] == ("ABCD", 1001.0, 42.0, 3)


def test_exit_read_falls_back_to_minute_bars_on_a_busy_window(monkeypatch):
    from ibkr import historical_service, historical_trades

    async def recent(symbol, end, back_sec, **_kw):
        return {"trades": [_tick(end - 1, 2.0)], "since": end - 10, "complete": False, "pages": 3,
                "minutes": [], "minutes_note": None}

    async def bars(symbol, tf, limit, *, priority):
        assert (tf, priority) == ("1Min", "background")
        stamp = datetime.fromtimestamp(960.0 + 86_400).astimezone().isoformat()
        return {"bars": [{"t": stamp, "o": 2, "h": 2.4, "l": 1.6, "c": 2, "v": 100}]}

    monkeypatch.setattr(historical_trades, "recent_trades", recent)
    monkeypatch.setattr(historical_service, "request_bars", bars)
    got = _run(exits.read(("ABCD", 1000.0 + 86_400, 940.0 + 86_400)))
    assert got["state"] == "range" and got["source"] == "ibkr_1min_bars" and (got["low"], got["high"]) == (1.6, 2.4)


# -- Level 1 lines ------------------------------------------------------------------------------------


def test_plan_caps_the_lines():
    syms = [f"S{i}" for i in range(FOLLOWED_MAX_LINES + 2)] + ["S0", "bad ticker"]
    held, over = lines.plan(syms)
    assert held == syms[:FOLLOWED_MAX_LINES] and over == set(syms[FOLLOWED_MAX_LINES:FOLLOWED_MAX_LINES + 2])


def test_lines_are_asked_once_and_released_when_idle(monkeypatch):
    monkeypatch.setattr(lines, "_owners", lambda sym: {"followed"})
    sent = []
    spawn = lambda name, factory: sent.append(name)   # noqa: E731
    lines.want(["AAA", "BBB"], 0.0, spawn=spawn)
    lines._in_flight = False
    lines.want(["BBB", "AAA"], 3.0, spawn=spawn)
    assert sent == ["followed.lines"]                 # same set, all held: nothing asked again
    assert lines.release_if_idle(10.0, spawn=spawn) is False
    assert lines.release_if_idle(3.0 + 21.0, spawn=spawn) is True
    assert sent == ["followed.lines", "followed.lines"]
    lines._in_flight = False
    assert lines.release_if_idle(100.0, spawn=spawn) is True and len(sent) == 2


def test_a_missing_line_is_asked_again(monkeypatch):
    monkeypatch.setattr(lines, "_owners", lambda sym: set())     # dropped by a reconnect
    sent = []
    lines.want(["AAA"], 0.0, spawn=lambda n, f: sent.append(n))
    lines._in_flight = False
    lines.want(["AAA"], 1.0, spawn=lambda n, f: sent.append(n))
    lines.want(["AAA"], 6.0, spawn=lambda n, f: sent.append(n))
    assert len(sent) == 2


def test_quotes_state_each_line(monkeypatch):
    from ibkr import ticks

    monkeypatch.setattr(ticks, "last_quotes", lambda syms: {
        "AAA": {"price": 2.5, "last_trade_ts": 99.0, "quote_quality": None},
        "BBB": {"price": 1.0, "last_trade_ts": None, "quote_quality": "close_fallback"},
        "DDD": {"price": 3.0, "last_trade_ts": None, "quote_quality": None},
    })
    monkeypatch.setattr(ticks, "refused_view", lambda: {"refused": [{"symbol": "DDD", "message": "Max tickers"}]})
    got = lines.quotes(["AAA", "BBB", "CCC", "DDD"])
    assert got["AAA"] == {"state": "live", "price": 2.5, "trade_ts": 99.0, "why": None}
    assert got["BBB"]["state"] == "no_trade" and got["BBB"]["price"] is None
    assert got["CCC"]["state"] == "waiting"
    assert got["DDD"]["state"] == "no_line" and "Max tickers" in got["DDD"]["why"]


# -- the routes ---------------------------------------------------------------------------------------


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv(FOLLOWED_FEED_URL_ENV, BASE)
    monkeypatch.setattr(routes, "_ibkr_ready", lambda: True)
    monkeypatch.setattr(routes, "_replay_desk", lambda: False)
    monkeypatch.setattr(lines, "_spawn_ib", lambda name, factory: None)
    monkeypatch.setattr(exits, "_spawn_ib", lambda name, factory: None)
    monkeypatch.setattr(lines, "_owners", lambda sym: {"followed"})
    monkeypatch.setattr(lines, "quotes", lambda syms: {s: lines.now_state("live", price=2.5, trade_ts=1.0)
                                                       for s in syms})
    app = FastAPI()
    app.include_router(routes.router)
    return TestClient(app)


def _serve(monkeypatch, raw):
    monkeypatch.setattr(feed, "fetch_day", lambda base, date: feed.parse_day(copy.deepcopy(raw)))


def test_route_config(client):
    assert client.get("/api/followed-traders/config").json() == {"schema_version": 1, "enabled": True}


def test_route_day_prices_open_and_marks_exits_pending(client, monkeypatch):
    today = routes.desk_day(time.time())[0]
    raw = _raw_day([_trade(symbol="AAA"), _trade(symbol="BBB", status="closed", exit_clock="10:20:00")],
                   date=today, today=today)
    _serve(monkeypatch, raw)
    body = client.get("/api/followed-traders/day").json()
    alpha = body["traders"][0]
    assert body["prices"] == {"state": "live", "why": None}
    assert alpha["open"][0]["now"]["price"] == 2.5 and alpha["open"][0]["pl"]["per_share"] == 0.5
    assert alpha["closed"][0]["exit"]["state"] == "pending"


def test_route_day_past_day_and_replay_desk(client, monkeypatch):
    _serve(monkeypatch, _raw_day([_trade()], date="2026-10-12", today="2026-10-13"))
    assert client.get("/api/followed-traders/day?date=2026-10-12").json()["prices"]["state"] == "past_day"
    today = routes.desk_day(time.time())[0]
    _serve(monkeypatch, _raw_day([_trade()], date=today, today=today))
    monkeypatch.setattr(routes, "_replay_desk", lambda: True)
    body = client.get("/api/followed-traders/day").json()
    assert body["prices"]["state"] == "replay_desk"
    assert body["traders"][0]["open"][0]["now"]["state"] == "off"


@pytest.mark.parametrize("clock, date, today, resets", [
    # 00:30 ET is still the day before: the desk's day, and this page's, turns at 04:00 ET, the premarket.
    ("00:30:00", "2026-10-14", "2026-10-13", "2026-10-14T04:00:00-04:00"),
    ("03:59:59", "2026-10-14", "2026-10-13", "2026-10-14T04:00:00-04:00"),
    ("04:00:00", "2026-10-14", "2026-10-14", "2026-10-15T04:00:00-04:00"),
    ("21:00:00", "2026-10-13", "2026-10-13", "2026-10-14T04:00:00-04:00"),
])
def test_desk_day_turns_at_four_et(clock, date, today, resets):
    got, resets_at = routes.desk_day(_epoch(clock, date))
    assert got == today and resets_at == datetime.fromisoformat(resets).timestamp()


def test_desk_day_ends_at_four_et_across_the_clock_change():
    # Clocks go back at 02:00 on 2026-11-01: that day's 04:00 ET is 09:00 UTC, 25 hours after the one before.
    _, resets_at = routes.desk_day(_epoch("10:00:00", "2026-10-31"))
    assert resets_at == datetime.fromisoformat("2026-11-01T09:00:00+00:00").timestamp()


def test_route_day_asks_the_feed_for_the_desks_day_and_says_when_it_ends(client, monkeypatch):
    asked = []
    today, resets_at = routes.desk_day(time.time())

    def fetch(base, date):
        asked.append(date)
        # The feed's own today turns at midnight; between 00:00 and 04:00 ET it is a day ahead of the desk's.
        return feed.parse_day(_raw_day([_trade()], date=date, today="2099-01-01"))

    monkeypatch.setattr(feed, "fetch_day", fetch)
    body = client.get("/api/followed-traders/day").json()
    assert asked == [today]
    assert body["date"] == today and body["today"] == today and body["prices"]["state"] == "live"
    assert abs(body["resets_at"] - resets_at) < 1


def test_route_day_feed_down_is_stated(client, monkeypatch):
    def down(base, date):
        raise feed.FeedError("unreachable", "timed out after 3 s")

    monkeypatch.setattr(feed, "fetch_day", down)
    body = client.get("/api/followed-traders/day").json()
    assert body["feed"] == {"state": "unreachable", "error": "timed out after 3 s"} and body["traders"] == []


def test_route_day_refuses_a_bad_date(client):
    resp = client.get("/api/followed-traders/day?date=yesterday")
    assert resp.status_code == 400 and resp.json()["detail"]["reason"] == "FOLLOWED_BAD_DATE"


def test_route_day_unpriceable_symbol(client, monkeypatch):
    _serve(monkeypatch, _raw_day([_trade(symbol="J8D?")]))
    row = client.get("/api/followed-traders/day").json()["traders"][0]["open"][0]
    assert row["now"]["state"] == "no_line" and "not a ticker" in row["now"]["why"]


def test_route_evidence_passes_the_image_through(client, monkeypatch):
    asked = []

    def fetch(base, date, name):
        asked.append((base, date, name))
        return b"\xff\xd8jpeg"

    monkeypatch.setattr(feed, "fetch_evidence", fetch)
    ok = client.get(f"/api/followed-traders/evidence/2026-10-13/frames/{'c' * 32}.jpg")
    assert ok.status_code == 200 and ok.content == b"\xff\xd8jpeg" and ok.headers["content-type"] == "image/jpeg"
    assert client.get("/api/followed-traders/evidence/2026-10-13/frames/notahexname.jpg").status_code == 404
    assert client.get("/api/followed-traders/evidence/latest/frames/" + "c" * 32 + ".jpg").status_code == 404
    assert asked == [(BASE, "2026-10-13", "c" * 32)]

    def down(base, date, name):
        raise feed.FeedError("unreachable", "could not connect")

    monkeypatch.setattr(feed, "fetch_evidence", down)
    bad = client.get(f"/api/followed-traders/evidence/2026-10-13/frames/{'d' * 32}.jpg")
    assert bad.status_code == 502 and bad.json()["detail"]["reason"] == "FOLLOWED_FEED_UNREACHABLE"


# -- the feed's stated problem, and its trades across days (feed format of 2026-10-13) -------------------


def test_status_carries_the_feeds_problem():
    raw = _raw_day()
    raw["status"].update(problem="the source asked to confirm a human", problem_at=_ts("13:04:02"))
    status = feed.parse_day(raw)["status"]
    assert status["problem"] == "the source asked to confirm a human" and status["problem_at"] == _epoch("13:04:02")
    body = view.capture(status, _epoch("13:05:00"))
    assert body["problem"] == "the source asked to confirm a human"


def test_a_status_holding_only_the_problem_is_read_as_said():
    raw = _raw_day()
    raw["status"] = {"problem": "no stream found", "problem_at": _ts("09:00:00")}
    status = feed.parse_day(raw)["status"]
    assert status["problem"] == "no stream found" and status["live"] is False and status["updated_at"] is None


def test_parse_range_tags_each_trade_with_its_day():
    raw = {"from": "2026-10-07", "to": "2026-10-13", "dates": ["2026-10-12", "2026-10-13"],
           "trades": [_trade() | {"date": "2026-10-12"}]}
    got = feed.parse_range(raw)
    assert got["trades"][0]["date"] == "2026-10-12" and got["dates"] == ["2026-10-12", "2026-10-13"]
    raw["trades"][0].pop("date")
    with pytest.raises(feed.FeedError, match=r"^trades\[0\]\.date"):
        feed.parse_range(raw)


def test_fetch_trades_leaves_out_from_for_every_day(monkeypatch):
    seen = []

    def get(_pool, url, **kw):
        seen.append((url, kw["params"]))
        return _Resp(body={"from": kw["params"].get("from", "0000-00-00"), "to": "2026-10-13", "dates": [],
                           "trades": []})

    monkeypatch.setattr(feed.http_pool, "get", get)
    feed.fetch_trades(BASE, None, "2026-10-13")
    feed.fetch_trades(BASE, "2026-10-07", "2026-10-13")
    assert seen == [(f"{BASE}/api/trades", {"to": "2026-10-13"}),
                    (f"{BASE}/api/trades", {"from": "2026-10-07", "to": "2026-10-13"})]


# -- scoring (operator decisions 2026-10-13: win > 0, loss < 0, scratch 0, unscored without one exit price) ---


def _scored(status="closed", exit_state="at", per_share=None):
    exit_ = exits.stated(exit_state, price=1.0) if status != "open" else None
    if per_share is None:
        pl = None
    elif exit_state == "at":
        pl = {"per_share": per_share, "pct": 0.0}
    else:
        pl = {"low_per_share": -1, "high_per_share": 1, "low_pct": -1, "high_pct": 1}
    return {"status": status, "exit": exit_, "pl": pl}


def test_result_is_win_loss_scratch_or_unscored():
    assert scoring.result(_scored(per_share=0.25)) == "win"
    assert scoring.result(_scored(per_share=-0.01)) == "loss"
    assert scoring.result(_scored(per_share=0.0)) == "scratch"
    assert scoring.result(_scored(exit_state="range", per_share=0.5)) == "unscored"
    assert scoring.result(_scored(exit_state="pending")) == "unscored"
    assert scoring.result(_scored(status="unknown", exit_state="unavailable")) == "unscored"
    assert scoring.result(_scored(status="open")) is None


def test_record_leaves_scratches_and_unscored_out_of_the_win_rate():
    rows = [{"result": r} for r in ("win", "win", "win", "win", "loss", "scratch", "unscored", None)]
    assert scoring.record(rows) == {"wins": 4, "losses": 1, "scratches": 1, "unscored": 1, "open": 1,
                                    "win_rate": 80.0}
    assert scoring.record([{"result": "scratch"}])["win_rate"] is None


def test_compose_scores_rows_and_keeps_records():
    body = _compose([
        _trade("ALPHA", symbol="AAA"),
        _trade("ALPHA", symbol="BBB", status="closed", exit_clock="10:20:00"),          # exit 1.80 < 2.00
        _trade("BRAVO", side="short", symbol="CCC", status="closed", exit_clock="10:21:00"),
    ])
    alpha, bravo = body["traders"]
    assert alpha["open"][0]["result"] is None and alpha["closed"][0]["result"] == "loss"
    assert alpha["record"] == {"wins": 0, "losses": 1, "scratches": 0, "unscored": 0, "open": 1, "win_rate": 0.0}
    assert bravo["record"]["wins"] == 1
    assert body["overall"] == {"wins": 1, "losses": 1, "scratches": 0, "unscored": 0, "open": 1, "win_rate": 50.0}


# -- exits kept on disk -----------------------------------------------------------------------------


def test_priced_exits_are_kept_and_never_asked_again(tmp_path):
    key = ("ABCD", _epoch("10:20:00"), None)
    exits.view(*key, now=0.0)
    exits.pump(0.0, ibkr_ready=True, spawn=lambda n, f: None)
    exits._finish(key, "done", exits.stated("at", price=1.5, trade_ts=key[1] - 1, to_ts=key[1], source="ibkr_trades"))
    kept = json.loads((tmp_path / "followed-exits.json").read_text(encoding="utf-8"))
    assert kept["schema_version"] == 1 and kept["exits"][0]["symbol"] == "ABCD"
    exits.reset_for_tests()                      # a restart: memory gone, the file stays
    sent = []
    assert exits.view(*key, now=1.0)["price"] == 1.5
    exits.pump(1.0, ibkr_ready=True, spawn=lambda n, f: sent.append(n))
    assert sent == []


def test_failures_are_not_kept(tmp_path, monkeypatch):
    monkeypatch.setattr(exits, "_clock", lambda: 0.0)
    key = ("ABCD", 5000.0, None)
    exits.view(*key, now=0.0)
    for _ in range(3):
        exits.pump(10_000.0, ibkr_ready=True, spawn=lambda n, f: None)
        exits._finish(key, "failed", "down")
    assert exits.view(*key, now=1.0)["state"] == "unavailable"
    assert not (tmp_path / "followed-exits.json").exists()


def test_an_unknown_version_is_refused_and_never_overwritten(tmp_path):
    path = tmp_path / "followed-exits.json"
    path.write_text(json.dumps({"schema_version": 99, "exits": []}), encoding="utf-8")
    key = ("ABCD", 1000.0, None)
    assert exits.view(*key, now=0.0)["state"] == "pending"
    exits.pump(0.0, ibkr_ready=True, spawn=lambda n, f: None)
    exits._finish(key, "done", exits.stated("at", price=1.0, to_ts=1000.0))
    assert json.loads(path.read_text(encoding="utf-8"))["schema_version"] == 99


def test_the_newest_exit_is_read_first():
    for ts in (1000.0, 3000.0, 2000.0):
        exits.view("ABCD", ts, None, now=0.0)
    exits.pump(0.0, ibkr_ready=True, spawn=lambda n, f: None)
    assert exits._in_flight == ("ABCD", 3000.0, None)


# -- the record route ------------------------------------------------------------------------------


def test_record_start_for_each_range():
    assert routes.record_start("day", "2026-10-13") == "2026-10-13"
    assert routes.record_start("week", "2026-10-13") == "2026-10-07"
    assert routes.record_start("all", "2026-10-13") is None


def test_route_record(client, monkeypatch):
    asked = []

    def trades(base, start, end):
        asked.append((start, end))
        return feed.parse_range({"from": start, "to": end, "dates": ["2026-10-12", "2026-10-13"], "trades": [
            _trade("ALPHA", symbol="AAA", status="closed", exit_clock="10:20:00") | {"date": "2026-10-12"},
            _trade("ALPHA", symbol="BBB") | {"date": "2026-10-13"},
        ]})

    monkeypatch.setattr(feed, "fetch_trades", trades)
    body = client.get("/api/followed-traders/record?range=week&date=2026-10-13").json()
    assert asked == [("2026-10-07", "2026-10-13")]
    assert body["range"] == "week" and body["pending"] == 1
    assert body["traders"] == [{"name": "ALPHA", "record": {"wins": 0, "losses": 0, "scratches": 0, "unscored": 1,
                                                            "open": 1, "win_rate": None}}]
    assert client.get("/api/followed-traders/record?range=month").json()["detail"]["reason"] == "FOLLOWED_BAD_RANGE"

    def down(base, start, end):
        raise feed.FeedError("unreachable", "could not connect")

    monkeypatch.setattr(feed, "fetch_trades", down)
    body = client.get("/api/followed-traders/record?range=all").json()
    assert body["feed"]["state"] == "unreachable" and body["traders"] == [] and body["overall"] is None
