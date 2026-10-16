"""The Live Trader bot end to end on Paper (ADR 055): a sequence of faked feed answers and quotes, one watcher pass
after another, through the real ``followed_traders`` reads (sightings, closes on leaving, the ticker check), the
real execution door, the one short check and the real practice broker, on a scratch account and a scratch cache.

Made-up hosts (ALPHA, BRAVO, CHARLIE) and tickers; the clock is 2026-10-07, a Wednesday, pinned by ``short_market_open``.
"""
from __future__ import annotations

import asyncio
import copy
import json
import time
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

import ibkr.shortability as short_mod
import kill_switch
from bot import family_keys, switch
from bot.audit import list_entries
from bot.live_trader import book as lt_book
from bot.live_trader import lines as lt_lines
from bot.live_trader import market as lt_market
from bot.live_trader import settings as lt_settings
from bot.live_trader import watcher
from execution import inflight, service, telemetry
from followed_traders import exits, feed, routes
from followed_traders.constants_followed import FOLLOWED_FEED_URL_ENV
from ibkr import client as ibkr_client
from ibkr import safety as _safety
from practice import broker as practice_broker
from practice.broker import for_venue, reset_for_tests as reset_brokers
from sim.fill_model import Reference
from sim.mode import reset_for_tests as reset_venue, set_venue

ET = ZoneInfo("America/New_York")
DATE = "2026-10-07"
BASE = "http://127.0.0.1:8787"
# Names far apart: the page reads a name tag one letter off as the same host (followed_traders.sightings).
HOST, OTHER, NEXT = "ALPHA", "BRAVO", "CHARLIE"


def at(clock: str) -> float:
    return datetime.fromisoformat(f"{DATE}T{clock}").replace(tzinfo=ET).timestamp()


def iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, ET).isoformat()


def hms(ts: float) -> str:
    return datetime.fromtimestamp(ts, ET).strftime("%H:%M:%S")


class Feed:
    """The feed's day as the bot asks for it: trades, the status and the read log, changed by the test."""

    def __init__(self) -> None:
        self.trades: list[dict] = []
        self.clock = at("10:30:00")
        self.read_lag = 1.0                   # the read's time after the bar's clock (the feed's own delay)
        self.visible = True
        self.live = True
        self.down = False
        self.log: list[dict] = []
        self.dates = [DATE]
        self.days: dict[str, list[dict]] = {}     # another day's trades, by date

    def open(self, symbol, price, clock_ts, *, host=HOST, side="long", known=True) -> dict:
        t = {"trader": host, "side": side, "symbol": symbol, "entry_price": price, "price": price,
             "entry_ts": iso(clock_ts), "entry_since_ts": None, "entry_known": known, "adds": [], "exit_ts": None,
             "exit_since_ts": None, "status": "open", "entry_evidence": None, "exit_evidence": None}
        self.trades.append(t)
        return t

    @staticmethod
    def add(t, price, clock_ts) -> None:
        t["adds"].append({"ts": iso(clock_ts), "price": price, "prev_price": t["price"]})
        t["price"] = price

    @staticmethod
    def close(t, clock_ts) -> None:
        t.update(status="closed", exit_ts=iso(clock_ts))

    def bar(self, clock_ts, **hosts) -> None:
        self.log.append({"clock": hms(clock_ts), "traders": {
            n: {"positions": {}, "unparsed": []} for n in hosts}})

    def day(self, base, date, *, timeout=None):
        if self.down:
            raise feed.FeedError("unreachable", "could not connect")
        if date != DATE:
            return feed.parse_day({"date": date, "today": DATE, "dates": list(self.dates), "status": None,
                                   "trades": copy.deepcopy(self.days.get(date, [])), "events": []})
        raw = {"date": date, "today": date, "dates": list(self.dates),
               "status": {"video": {"id": "abcdefghijk", "title": "Live show"}, "live": self.live,
                          "clock": hms(self.clock), "updated_at": iso(self.clock + self.read_lag),
                          "bar_visible": self.visible, "traders": [HOST, OTHER], "positions": self.bar_now()},
               "trades": copy.deepcopy(self.trades), "events": []}
        return feed.parse_day(raw)

    def bar_now(self) -> dict:
        """Each host's bar as the feed confirms it: their open positions (``status.positions``)."""
        out: dict[str, dict] = {}
        for t in self.trades:                 # a host the feed has read keeps an empty bar, as the feed's tracker does
            out.setdefault(t["trader"], {})
            if t["status"] == "open":
                out[t["trader"]][f"{t['side']}:{t['symbol']}"] = t["price"]
        return out

    def reads(self, base, date, *, timeout=None):
        if not self.log:
            raise feed.FeedError("missing", "HTTP 404")
        return feed.parse_reads("\n".join(json.dumps(line) for line in self.log))


class Market:
    """The live feed as Paper and the bot see it, by symbol: last, bid, ask. Its clock is the test's."""

    def __init__(self, now: float) -> None:
        self.now = now
        self.px = {"XYZ": [100.00, 99.98, 100.02], "ABCD": [50.00, 49.99, 50.01], "FADE": [40.00, 39.99, 40.01],
                   "SOFI": [14.05, 14.04, 14.06]}
        self.caps: dict[str, object] = {}
        self.cover = at("15:55:00")
        self.lines: set[str] = set()

    def reference(self, symbol: str) -> Reference:
        got = self.px.get(symbol)
        return Reference(*got, live=True) if got else Reference(None, live=True)

    def admission(self, symbol: str):
        return (True, "OK", None) if symbol in self.px else (False, "dark", "PRACTICE_NO_LIVE_PRINT")

    def prints_between(self, symbol, after_ts, through_ts):
        return []

    def bid_at(self, symbol, ts):
        got = self.px.get(symbol)
        return got[1] if got else None

    def now_ts(self) -> float:
        return self.now

    def session_close_ts(self, ts: float) -> float:
        return ts + 86_400

    def quote(self, symbol):
        got = self.px.get(symbol)
        return None if got is None else {"last": got[0], "bid": got[1], "ask": got[2], "fresh": True}


TAPES: dict[str, dict] = {}


def _tape(symbol, exit_ts, exit_since_ts, now):
    got = TAPES.get(symbol)
    if got is None:
        return exits.stated("pending", to_ts=exit_ts, why="reading IBKR's tape")
    return exits.stated("at", price=got, to_ts=exit_ts, source="ibkr_trades")


@pytest.fixture
def desk(monkeypatch, tmp_path, short_market_open):
    """Paper, the desk armed, TRADER1's key on and the Bot switch on; the feed, quotes and caps faked."""
    reset_venue()
    reset_brokers()
    for mod in (service, inflight, telemetry, short_mod, exits, lt_settings, lt_book, watcher, lt_market, lt_lines):
        mod.reset_for_tests()
    routes._log_cache.clear()
    TAPES.clear()
    m = Market(at("10:30:00"))
    f = Feed()
    monkeypatch.setattr(practice_broker, "LiveReference", lambda: m)
    set_venue("paper")
    _safety.set_armed(True, reason="test")
    monkeypatch.setenv(FOLLOWED_FEED_URL_ENV, BASE)
    monkeypatch.setattr(feed, "fetch_day", f.day)
    monkeypatch.setattr(feed, "fetch_reads", f.reads)
    monkeypatch.setattr(exits, "view", _tape)
    monkeypatch.setattr(exits, "pump", lambda now, ibkr_ready, spawn=None: None)
    monkeypatch.setattr(exits, "_path", lambda: tmp_path / "followed-exits.json")
    monkeypatch.setattr(routes, "_ibkr_ready", lambda: True)
    monkeypatch.setattr(ibkr_client, "is_ready", lambda: True)
    # IBKR "connected" makes the door warm IBKR's margin what-if for a Paper buy: no IB loop here to ask it.
    from short_sale import whatif

    async def _no_answer(*args, **kwargs):
        return None

    monkeypatch.setattr(whatif, "request", lambda *a, **k: False)
    monkeypatch.setattr(whatif, "ask", _no_answer)
    monkeypatch.setattr(lt_market, "quote", m.quote)
    monkeypatch.setattr(lt_market, "cap", lambda s: m.caps.get(s, 50e9))
    monkeypatch.setattr(lt_market, "want_caps", lambda symbols: None)
    monkeypatch.setattr(lt_market, "cover_ts", lambda now: m.cover)
    monkeypatch.setattr(lt_market, "prewarm_borrow", lambda symbols: None)
    monkeypatch.setattr(lt_lines, "want", lambda symbols, now=None, spawn=None: m.lines.update(symbols))
    short_mod.remember_for_tests("FADE", short_mod.enrich_ibkr_listing(
        {"connected": True, "qualified": True, "shortable_shares": 50_000, "error": None}, fetched_at=time.time()))
    lt_settings.patch_host(HOST, {"key": True})
    switch.turn(True)
    yield SimpleNamespace(feed=f, market=m, broker=for_venue("paper"))
    for mod in (service, inflight, telemetry, short_mod, exits, watcher):
        mod.reset_for_tests()
    reset_brokers()
    reset_venue()


def run(d, clock: str | float, **feed_over):
    """One watcher pass at ``clock`` (the bar's clock; the pass runs a second after the feed read it)."""
    ts = at(clock) if isinstance(clock, str) else clock
    d.feed.clock = ts
    for k, v in feed_over.items():
        setattr(d.feed, k, v)
    now = ts + d.feed.read_lag + 1.0
    d.market.now = now
    asyncio.run(watcher.tick(now))
    return now


def lines_(outcome=None):
    return [r for r in list_entries(limit=400)
            if r["action"] == "live_trader" and (outcome is None or r["outcome"] == outcome)]


def held(d, symbol) -> float:
    return sum(float(r["qty"]) for r in d.broker.positions() if r["symbol"] == symbol)


# -- open, add, gone --------------------------------------------------------------------------------
def test_open_add_and_close_follow_the_host_with_real_paper_fills(desk):
    run(desk, "10:30:00")                                          # the watch begins on an empty bar
    t = desk.feed.open("XYZ", 100.00, at("10:30:10"))
    run(desk, "10:30:11")
    assert held(desk, "XYZ") == 4                                  # $500 at the ask plus 2 cents: 4 shares
    filled = [r for r in lines_("filled") if r["inputs"]["symbol"] == "XYZ"]
    assert filled and filled[0]["inputs"]["fill_price"] == pytest.approx(100.02)
    order = lines_("order")[0]
    assert order["inputs"]["change"]["kind"] == "open" and order["inputs"]["late_sec"] == pytest.approx(3.0)
    rows = desk.broker.closed_orders()
    assert rows[0]["order_origin"] == "live_trader" and rows[0]["order_source"] == "bot"

    desk.market.px["XYZ"] = [99.50, 99.48, 99.52]
    desk.feed.add(t, 99.70, at("10:31:00"))
    run(desk, "10:31:02")
    assert held(desk, "XYZ") == 4                                  # still settling
    run(desk, "10:31:06")
    assert held(desk, "XYZ") == 9                                  # one add: $500 at 99.54 is 5 shares (filled at the ask)
    pos = lt_book.positions()[f"{HOST}|long|XYZ"]
    assert pos["steps"] == 2 and pos["adds_followed"] == 1

    desk.feed.close(t, at("10:32:00"))
    run(desk, "10:32:01")
    assert held(desk, "XYZ") == 0
    (done,) = lt_book.closed_today()
    assert done["kind"] == "close" and done["pl_usd"] == pytest.approx(9 * 99.48 - (4 * 100.02 + 5 * 99.52), abs=0.01)
    assert lt_book.positions() == {}


def test_a_host_selling_part_sells_half_the_bots_shares_once_on_paper(desk):
    """Operator 2026-10-16, "Sell half, once": the host's average falls while the market rises -- they sold part
    (SHAWN's TSLA). The bot buys nothing, sells half its shares at market on Paper, and never trims it again."""
    run(desk, "10:30:00")
    t = desk.feed.open("XYZ", 100.00, at("10:30:10"))
    run(desk, "10:30:11")
    assert held(desk, "XYZ") == 4
    desk.market.px["XYZ"] = [101.00, 100.98, 101.02]           # the stock up, their average down: a sale
    desk.feed.add(t, 99.80, at("10:31:00"))
    run(desk, "10:31:06")
    assert held(desk, "XYZ") == 2
    pos = lt_book.positions()[f"{HOST}|long|XYZ"]
    assert pos["qty"] == 2 and pos["trimmed"] and pos["state"] == "open" and pos["adds_followed"] == 0
    assert any(r["inputs"]["code"] == "LT_ADD_IS_SALE" for r in lines_("skipped"))
    desk.feed.add(t, 99.60, at("10:32:00"))                    # another sale: nothing more is sold
    run(desk, "10:32:06")
    assert held(desk, "XYZ") == 2
    desk.feed.close(t, at("10:33:00"))
    run(desk, "10:33:01")
    assert held(desk, "XYZ") == 0
    (done,) = lt_book.closed_today()
    assert [f["kind"] for f in done["exit_fills"]] == ["trim", "close"]


def test_the_bots_shares_are_its_own_never_yours(desk):
    run(desk, "10:30:00")
    desk.broker.place("XYZ", "BUY", 100, order_type="MKT", source="manual")      # the operator's own 100
    t = desk.feed.open("XYZ", 100.00, at("10:30:10"))
    run(desk, "10:30:11")
    assert held(desk, "XYZ") == 104
    desk.feed.close(t, at("10:31:00"))
    run(desk, "10:31:01")
    assert held(desk, "XYZ") == 100                                # it sold its 4, never yours


# -- off air, hidden, the clock --------------------------------------------------------------------
def test_off_air_sells_when_another_host_has_held_the_bar_a_minute(desk):
    desk.feed.bar(at("10:29:00"), **{HOST: 1, OTHER: 1})
    run(desk, "10:30:00")
    desk.feed.open("XYZ", 100.00, at("10:30:10"))
    run(desk, "10:30:11")
    assert held(desk, "XYZ") == 4
    desk.feed.bar(at("10:40:00"), **{NEXT: 1})
    run(desk, "10:40:30")
    assert held(desk, "XYZ") == 4                                  # 30 s: a name tag misread for a few frames
    run(desk, "10:41:30")
    assert held(desk, "XYZ") == 0
    (done,) = lt_book.closed_today()
    assert done["kind"] == "off_air" and "went off air" in done["why"]


def test_back_on_air_the_same_position_is_taken_again_with_a_new_order_and_a_new_close(desk):
    desk.feed.bar(at("10:29:00"), **{HOST: 1, OTHER: 1})
    run(desk, "10:30:00")
    t = desk.feed.open("XYZ", 100.00, at("10:30:10"))
    run(desk, "10:30:11")
    desk.feed.bar(at("10:40:00"), **{NEXT: 1})
    run(desk, "10:41:30")
    assert held(desk, "XYZ") == 0                                  # off air: sold
    desk.feed.bar(at("14:00:00"), **{HOST: 1, OTHER: 1})
    run(desk, "14:00:05")
    assert held(desk, "XYZ") == 0                                  # back on air: waits for the bar's switch
    assert any("previous host's rows" in (r["inputs"].get("why") or "") for r in lines_("note"))
    run(desk, "14:08:10")
    assert held(desk, "XYZ") == 4                                  # no switch in 8 minutes: XYZ is theirs, taken
    desk.feed.close(t, at("14:10:00"))
    run(desk, "14:10:01")
    assert held(desk, "XYZ") == 0                                  # and sold for real, not a replayed receipt
    sends = [r for r in desk.broker.closed_orders() if r["order_origin"] == "live_trader"]
    assert len(sends) == 4 and len({r["order_id"] for r in sends}) == 4


def test_the_bar_hidden_ten_minutes_sells(desk):
    run(desk, "10:30:00")
    desk.feed.open("XYZ", 100.00, at("10:30:10"))
    run(desk, "10:30:11")
    run(desk, "10:35:00", visible=False)
    run(desk, "10:44:00", visible=False)
    assert held(desk, "XYZ") == 4
    run(desk, "10:45:05", visible=False)
    assert held(desk, "XYZ") == 0 and lt_book.closed_today()[0]["kind"] == "hidden"


def test_the_sell_all_time_sells_and_no_step_follows(desk):
    run(desk, "15:50:00")
    desk.feed.open("XYZ", 100.00, at("15:50:10"))
    run(desk, "15:50:11")
    assert held(desk, "XYZ") == 4
    desk.feed.open("ABCD", 50.00, at("15:55:00"))
    run(desk, "15:55:01")
    assert held(desk, "XYZ") == 0 and held(desk, "ABCD") == 0
    assert lt_book.closed_today()[0]["kind"] == "sell_all"
    assert any(r["inputs"]["code"] == "LT_AFTER_SELL_ALL" for r in lines_("skipped"))


# -- doubtful reads and the money rules -------------------------------------------------------------
def test_a_feed_reading_behind_the_stream_opens_nothing(desk):
    run(desk, "10:30:00")
    desk.feed.open("XYZ", 100.00, at("10:30:10"))
    run(desk, "10:30:11", read_lag=45.0)
    assert held(desk, "XYZ") == 0
    (skip,) = lines_("skipped")
    assert skip["inputs"]["code"] == "LT_FEED_BEHIND" and "behind the stream" in skip["reason"]


def test_the_allowance_stops_a_step_and_says_how_much_is_used(desk):
    lt_settings.patch_host(HOST, {"allowance_usd": 600.0})
    run(desk, "10:30:00")
    desk.feed.open("XYZ", 100.00, at("10:30:10"))
    run(desk, "10:30:11")
    desk.feed.open("ABCD", 50.00, at("10:30:20"))
    run(desk, "10:30:21")
    assert held(desk, "XYZ") == 4 and held(desk, "ABCD") == 0
    skip = [r for r in lines_("skipped") if r["inputs"]["symbol"] == "ABCD"][0]
    assert skip["inputs"]["code"] == "LT_ALLOWANCE" and "allowance used: $400 of $600" in skip["reason"]


def test_a_small_cap_is_skipped(desk):
    desk.market.caps["XYZ"] = 1.4e9
    run(desk, "10:30:00")
    desk.feed.open("XYZ", 100.00, at("10:30:10"))
    run(desk, "10:30:11")
    assert held(desk, "XYZ") == 0
    assert lines_("skipped")[0]["inputs"]["code"] == "LT_SMALL_CAP"


def test_a_glued_ticker_waits_for_its_check_then_trades_the_true_ticker(desk):
    run(desk, "10:30:00")
    desk.feed.open("SOF", 114.03, at("10:30:10"))                  # "SOFI 14.03" read glued
    run(desk, "10:30:11")
    assert held(desk, "SOF") == 0 and held(desk, "SOFI") == 0      # the check reads IBKR's tape first
    TAPES.update({"SOF": 9.10, "SOFI": 14.05})
    run(desk, "10:30:14")
    assert held(desk, "SOFI") == 35                                # $500 at 14.08: 35 shares of the true ticker
    assert held(desk, "SOF") == 0


def test_a_short_is_a_bracket_with_its_buy_stop_and_covered_when_the_host_covers(desk):
    run(desk, "10:30:00")
    t = desk.feed.open("FADE", 40.00, at("10:30:10"), side="short")
    run(desk, "10:30:11")
    assert held(desk, "FADE") == -12                               # $500 at 39.97: 12 shares short
    pos = lt_book.positions()[f"{HOST}|short|FADE"]
    (stop_id,) = pos["stop_order_ids"]
    stop = desk.broker.ledger.order_row(stop_id)
    assert stop["side"] == "BUY" and float(stop["stop_price"]) == pytest.approx(41.97)
    desk.feed.close(t, at("10:31:00"))
    run(desk, "10:31:01")
    assert held(desk, "FADE") == 0
    assert desk.broker.ledger.order_row(stop_id)["status"] == "Cancelled"


# -- the operator's switches ------------------------------------------------------------------------
def _app():
    """The Live Trader routes alone: importing the desk's app here would build it with the feed's routes on."""
    from fastapi import FastAPI

    from bot.live_trader.routes import router

    app = FastAPI()
    app.include_router(router)
    return app


def _key_off(which: str):
    """Turn one of the three keys off (operator decision 2026-10-15); returns how to turn it back on."""
    if which == "host_key":
        lt_settings.patch_host(HOST, {"key": False})
        return lambda: lt_settings.patch_host(HOST, {"key": True})
    if which == "family":
        family_keys.turn("live_trader", False)
        return lambda: family_keys.turn("live_trader", True)
    switch.turn(False)
    return lambda: switch.turn(True)


@pytest.mark.parametrize("which", ["host_key", "family", "bot_switch"])
def test_with_a_key_off_the_bot_places_no_order_not_even_the_hosts_close(desk, monkeypatch, which):
    monkeypatch.setenv("NOVA_API_KEY", "lt-test-key")
    client = TestClient(_app())
    run(desk, "10:30:00")
    t = desk.feed.open("XYZ", 100.00, at("10:30:10"))
    run(desk, "10:30:11")
    assert held(desk, "XYZ") == 4                                  # $500 at 100.02: 4 shares
    if which == "host_key":                                        # through the route the card uses
        got = client.patch(f"/api/bot/live-traders/{HOST}", json={"key": False},
                           headers={"X-Nova-Api-Key": "lt-test-key"})
        assert got.status_code == 200, got.text
        back_on = lambda: lt_settings.patch_host(HOST, {"key": True})  # noqa: E731
    else:
        back_on = _key_off(which)
    run(desk, "10:30:20")
    assert held(desk, "XYZ") == 4                                  # turning a key off sold nothing
    desk.feed.open("ABCD", 50.00, at("10:30:25"))
    desk.feed.close(t, at("10:30:30"))
    desk.feed.clock = at("10:30:31")
    run(desk, "10:30:31")
    run(desk, "10:30:33")
    assert held(desk, "XYZ") == 4 and held(desk, "ABCD") == 0      # no sell, no buy
    assert desk.broker.ledger.working_orders() == []               # nothing sent and left working either
    said = [r for r in lines_() if r["outcome"] == "note" and "not sold" in (r.get("reason") or "")]
    assert len(said) == 1                                          # said once
    back_on()
    run(desk, "10:30:40")
    assert held(desk, "XYZ") == 0                                  # on again: the host's close is made
    assert lt_book.closed_today()[0]["kind"] == "close"


@pytest.mark.parametrize("exit_mode", ["nova", "you"])
def test_a_position_from_an_earlier_day_a_key_held_is_sold_when_the_key_is_back_on(desk, monkeypatch, exit_mode):
    """The day rolls over while a key is off: nothing is sold then, and the pass the key is back on sells it -- with
    Exit: You too, the clock's exit is never the host's (Codex review, PR #1006)."""
    run(desk, "10:30:00")
    desk.feed.open("XYZ", 100.00, at("10:30:10"))
    run(desk, "10:30:11")
    assert held(desk, "XYZ") == 4
    lt_settings.patch_host(HOST, {"key": False, "exit": exit_mode})
    later = at("10:31:00")
    real = watcher._desk_day
    monkeypatch.setattr(watcher, "_desk_day", lambda ts: "2026-10-08" if ts >= later else real(ts))  # the next day
    asyncio.run(watcher._sell_earlier_days(later))
    asyncio.run(watcher._sell_earlier_days(later + 2))
    assert held(desk, "XYZ") == 4                                     # a key off: no order, not even this sell
    said = [r for r in lines_("note") if "earlier day: not sold" in (r.get("reason") or "")]
    assert len(said) == 1                                             # said once
    lt_settings.patch_host(HOST, {"key": True})
    asyncio.run(watcher._sell_earlier_days(later + 4))
    assert held(desk, "XYZ") == 0


def test_with_every_key_off_your_own_cover_of_the_bots_short_goes_through(desk):
    """Keys stop the bots, never you: a cover is a close at the door, and the bot's stale stop is taken back."""
    run(desk, "10:30:00")
    desk.feed.open("FADE", 40.00, at("10:30:10"), side="short")
    run(desk, "10:30:11")
    (stop_id,) = lt_book.positions()[f"{HOST}|short|FADE"]["stop_order_ids"]
    lt_settings.patch_host(HOST, {"key": False})
    family_keys.turn("live_trader", False)
    switch.turn(False)
    desk.broker.place("FADE", "BUY", 12, order_type="MKT", source="manual")     # you covered all of it
    run(desk, "10:30:20")
    assert held(desk, "FADE") == 0
    assert desk.broker.ledger.order_row(stop_id)["status"] == "Cancelled"     # a cancel places nothing
    assert lt_book.positions() == {}


def test_freeze_all_orders_stops_new_steps_but_not_the_close(desk):
    run(desk, "10:30:00")
    t = desk.feed.open("XYZ", 100.00, at("10:30:10"))
    run(desk, "10:30:11")
    asyncio.run(kill_switch.trip("test"))
    desk.feed.open("ABCD", 50.00, at("10:30:20"))
    desk.feed.close(t, at("10:30:20"))
    run(desk, "10:30:21")
    assert held(desk, "ABCD") == 0 and held(desk, "XYZ") == 0
    assert any(r["inputs"]["code"] == "LT_FROZEN" for r in lines_("skipped"))


def test_shares_sold_outside_leave_the_position_and_are_not_bought_back(desk):
    run(desk, "10:30:00")
    desk.feed.open("XYZ", 100.00, at("10:30:10"))
    run(desk, "10:30:11")
    desk.broker.place("XYZ", "SELL", 4, order_type="MKT", source="manual")     # you sold the bot's shares
    run(desk, "10:30:20")
    assert lt_book.positions() == {} and lt_book.closed_today()[0]["kind"] == "outside"
    run(desk, "10:30:30")
    assert held(desk, "XYZ") == 0


def test_a_restart_resumes_what_the_bot_holds(desk):
    run(desk, "10:30:00")
    t = desk.feed.open("XYZ", 100.00, at("10:30:10"))
    run(desk, "10:30:11")
    watcher.reset_for_tests()                                      # a restart: the snapshot is gone,
    lt_book.reset_for_tests()                                      # the book is read back from the cache
    assert lt_book.positions()[f"{HOST}|long|XYZ"]["qty"] == 4
    run(desk, "10:30:20")
    assert held(desk, "XYZ") == 4                                  # nothing bought twice
    desk.feed.close(t, at("10:31:00"))
    run(desk, "10:31:01")
    assert held(desk, "XYZ") == 0


def test_the_cards_answer_the_bots_page(desk, monkeypatch):
    app = _app()
    run(desk, "10:30:00")
    desk.feed.open("XYZ", 100.00, at("10:30:10"))
    run(desk, "10:30:11")
    body = TestClient(app).get("/api/bot/live-traders").json()
    assert body["venue"] == "paper" and body["can_trade"]["ok"] is True
    card = next(h for h in body["hosts"] if h["name"] == HOST)
    assert card["settings"]["key"] is True and card["settings"]["mode"] == "bot"
    (pos,) = card["positions"]
    assert pos["symbol"] == "XYZ" and pos["qty"] == 4 and pos["their_avg"] == 100.0
    assert card["allowance"] == {"used_usd": pytest.approx(400.08), "of_usd": 2500.0}
    assert card["events"][0]["outcome"] in ("filled", "order")
    monkeypatch.setenv("NOVA_API_KEY", "lt-test-key")
    bad = TestClient(app).patch(f"/api/bot/live-traders/{HOST}", json={"step_usd": 5},
                                headers={"X-Nova-Api-Key": "lt-test-key"})
    assert bad.status_code == 400 and bad.json()["detail"]["reason"] == "LIVE_TRADER_INVALID"


def test_the_report_puts_every_order_beside_the_change_that_caused_it(desk):
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from tools import live_trader_report

    run(desk, "10:30:00")
    t = desk.feed.open("XYZ", 100.00, at("10:30:10"))
    run(desk, "10:30:11")
    desk.market.caps["QQQQ"] = 2e9
    desk.market.px["QQQQ"] = [5.0, 4.99, 5.01]
    desk.feed.open("QQQQ", 5.00, at("10:30:20"))
    run(desk, "10:30:21")
    desk.feed.close(t, at("10:31:00"))
    run(desk, "10:31:01")
    lines = list_entries(limit=400)
    today = live_trader_report.desk_day(time.time())       # audit lines carry the wall clock; the test pins its own
    rows = live_trader_report.orders(lines, today)
    assert [(r["step"], r["change"], r["filled"]) for r in rows] == [("entry", "open", True), ("close", "close", True)]
    entry, close = rows
    assert entry["late_sec"] == pytest.approx(3.0) and entry["fill_price"] == pytest.approx(100.02)
    assert entry["ibkr_last"] == 100.0 and entry["fill_minus_last"] == pytest.approx(0.02)
    assert close["fill_price"] == pytest.approx(99.98) and close["late_sec"] == pytest.approx(3.0)
    (skip,) = live_trader_report.skips(lines, today)
    assert skip["code"] == "LT_SMALL_CAP"
    text = live_trader_report.markdown(today, rows, [skip])
    assert "| ALPHA | entry | XYZ long | open 100.00 |" in text and "LT_SMALL_CAP: 1" in text


# -- bad reads and the review's two findings ---------------------------------------------------------------
def test_a_fresh_desk_lists_the_feeds_hosts_with_their_keys_off(desk):
    """No Live Trader settings yet (a fresh desk): the idle bot still lists the hosts the feed read today, so each
    card -- and its key -- is there to turn on (found at the first live check, 2026-10-15)."""
    from bot.live_trader import view as lt_view

    lt_settings._path().unlink()
    lt_settings.reset_for_tests()
    desk.feed.open("XYZ", 100.00, at("10:29:00"), host=OTHER)
    run(desk, "10:30:00")
    got = lt_view.build()
    assert got["watcher"]["idle"] is True
    assert [h["name"] for h in got["hosts"]] == [OTHER, HOST]
    assert not any(h["settings"]["key"] for h in got["hosts"])
    assert held(desk, "XYZ") == 0                                  # idle: it reads names, it never trades
    desk.feed.down = True                                          # a read that fails keeps the day's names
    run(desk, "10:30:05")
    down = lt_view.build()
    assert [h["name"] for h in down["hosts"]] == [OTHER, HOST]
    assert down["watcher"]["feed"]["state"] == "unreachable" and "could not connect" in down["watcher"]["feed"]["error"]
    said = lt_view._watcher_text({"running": True, "idle": True}, {"state": "unreachable", "error": "could not connect"})
    assert said == "Idle: no host's key is on -- the TraderTV feed is not answering (could not connect)"
    desk.feed.down = False
    lt_settings.patch_host(HOST, {"key": True})
    desk.feed.open("ABCD", 50.00, at("10:30:10"))
    run(desk, "10:30:11")
    assert held(desk, "ABCD") == 9


def test_a_side_whose_reads_carry_an_unparsed_price_opens_nothing_until_it_reads(desk):
    """The read log's unparsed text, as the page reads it: a long row the reader could not read whole."""
    run(desk, "10:30:00")
    desk.feed.log.append({"clock": "10:30:09", "traders": {HOST: {"positions": {}, "unparsed": [
        "long:7.32|ABCD50.01|EFGH5.58|IJK"]}}})
    desk.feed.open("XYZ", 100.00, at("10:30:10"))
    run(desk, "10:30:11")
    assert held(desk, "XYZ") == 0
    assert watcher.status()["waits"][f"{HOST}|long|XYZ"]["code"] == "LT_ROW_UNREAD"
    desk.feed.bar(at("10:30:12"), **{HOST: {}})                    # it reads whole again
    run(desk, "10:30:40")
    assert held(desk, "XYZ") == 4


def test_a_row_the_previous_day_showed_is_never_bought(desk):
    desk.feed.dates = [DATE, "2026-10-06"]
    desk.feed.days["2026-10-06"] = [{
        "trader": OTHER, "side": "long", "symbol": "XYZ", "entry_price": 100.0, "price": 100.0,
        "entry_ts": "2026-10-06T15:00:00-04:00", "entry_since_ts": None, "entry_known": True, "adds": [],
        "exit_ts": "2026-10-06T15:40:00-04:00", "exit_since_ts": None, "status": "closed",
        "entry_evidence": None, "exit_evidence": None}]
    run(desk, "10:30:00")
    desk.feed.open("XYZ", 100.00, at("10:30:10"))
    run(desk, "10:30:11")
    assert held(desk, "XYZ") == 0
    (skip,) = lines_("skipped")
    assert skip["inputs"]["code"] == "LT_OTHER_HOST" and "previous day" in skip["reason"]


def test_a_clock_read_impossibly_never_stops_the_watcher(desk, monkeypatch):
    """09:34:97 in the read log and on the status: the line is dropped, the pass goes on, nothing opens on it."""
    run(desk, "10:30:00")
    desk.feed.log.append({"clock": "10:29:97", "traders": {HOST: {"positions": {}, "unparsed": []}}})
    t = desk.feed.open("XYZ", 100.00, at("10:30:10"))
    run(desk, "10:30:11")
    assert held(desk, "XYZ") == 4
    real_day = desk.feed.day

    def bad_clock(base, date, *, timeout=None):
        got = real_day(base, date, timeout=timeout)
        return {**got, "status": {**got["status"], "clock": None}}

    monkeypatch.setattr(feed, "fetch_day", bad_clock)
    routes._log_cache.clear()
    desk.feed.close(t, at("10:31:00"))
    run(desk, "10:31:01")
    assert held(desk, "XYZ") == 0                                  # a close needs no clock


def test_a_short_covered_in_part_outside_has_its_stop_cancelled_and_the_rest_covered(desk):
    run(desk, "10:30:00")
    desk.feed.open("FADE", 40.00, at("10:30:10"), side="short")
    run(desk, "10:30:11")
    (stop_id,) = lt_book.positions()[f"{HOST}|short|FADE"]["stop_order_ids"]
    desk.broker.place("FADE", "BUY", 5, order_type="MKT", source="manual")      # you covered 5 of the bot's 12
    run(desk, "10:30:20")
    run(desk, "10:30:22")
    assert held(desk, "FADE") == 0
    assert desk.broker.ledger.order_row(stop_id)["status"] == "Cancelled"
    assert lt_book.positions() == {}


def test_a_short_covered_in_full_outside_leaves_no_stop_to_cover_the_next_short(desk):
    run(desk, "10:30:00")
    desk.feed.open("FADE", 40.00, at("10:30:10"), side="short")
    run(desk, "10:30:11")
    (stop_id,) = lt_book.positions()[f"{HOST}|short|FADE"]["stop_order_ids"]
    desk.broker.place("FADE", "BUY", 12, order_type="MKT", source="manual")     # you covered all of it
    run(desk, "10:30:20")
    assert held(desk, "FADE") == 0
    assert desk.broker.ledger.order_row(stop_id)["status"] == "Cancelled"


def test_a_stop_whose_cancel_is_refused_is_cancelled_on_a_later_pass_even_after_a_restart(desk, monkeypatch):
    from bot.live_trader import orders as lt_orders

    run(desk, "10:30:00")
    desk.feed.open("FADE", 40.00, at("10:30:10"), side="short")
    run(desk, "10:30:11")
    (stop_id,) = lt_book.positions()[f"{HOST}|short|FADE"]["stop_order_ids"]
    real_cancel = lt_orders.cancel

    async def refused(order_id, symbol, host):
        return SimpleNamespace(ok=False, error="refused for the test", reason_code="TEST")

    monkeypatch.setattr(lt_orders, "cancel", refused)
    desk.broker.place("FADE", "BUY", 12, order_type="MKT", source="manual")     # you covered all of it
    run(desk, "10:30:20")
    assert desk.broker.ledger.order_row(stop_id)["status"] != "Cancelled"
    assert [r["order_id"] for r in lt_book.retiring()] == [stop_id]
    assert any("still working" in (line["reason"] or "") for line in lines_("error"))
    lt_book.reset_for_tests()                                      # a restart: the list is read back from the file
    monkeypatch.setattr(lt_orders, "cancel", real_cancel)
    run(desk, "10:30:22")
    assert desk.broker.ledger.order_row(stop_id)["status"] == "Cancelled"
    assert lt_book.retiring() == []


def test_a_book_that_cannot_be_written_opens_nothing_until_it_can(desk, monkeypatch, tmp_path):
    good = lt_book._path()
    blocker = tmp_path / "not-a-folder"
    blocker.write_text("x", encoding="utf-8")
    run(desk, "10:30:00")
    monkeypatch.setattr(lt_book, "_path", lambda: blocker / "live-trader-book.json")
    desk.feed.open("XYZ", 100.00, at("10:30:10"))
    run(desk, "10:30:11")
    assert held(desk, "XYZ") == 4                                  # the order went out; its record did not
    assert "could not be written" in (lt_book.error() or "")
    desk.feed.open("ABCD", 50.00, at("10:30:20"))
    run(desk, "10:30:21")
    assert held(desk, "ABCD") == 0
    assert watcher.status()["can_open"]["ok"] is False
    monkeypatch.setattr(lt_book, "_path", lambda: good)
    run(desk, "10:30:30")
    assert lt_book.error() is None
    run(desk, "10:30:32")
    assert held(desk, "ABCD") == 9                                 # taken as already open once the book is sound


# -- the bar's own moves ---------------------------------------------------------------------------
def test_a_whole_bar_blank_for_a_refresh_sells_nothing_and_buys_nothing_again(desk):
    run(desk, "10:30:00")
    a = desk.feed.open("XYZ", 100.00, at("10:30:10"))
    b = desk.feed.open("ABCD", 50.00, at("10:30:20"))
    run(desk, "10:30:21")
    assert held(desk, "XYZ") == 4 and held(desk, "ABCD") == 9
    sent = len(desk.broker.closed_orders())

    desk.feed.close(a, at("10:40:00"))                             # the whole bar blank in one second
    desk.feed.close(b, at("10:40:00"))
    run(desk, "10:40:01")
    run(desk, "10:40:40")
    assert held(desk, "XYZ") == 4 and held(desk, "ABCD") == 9      # the sells wait for the bar
    assert any("went blank" in (r["inputs"].get("why") or "") for r in lines_("note"))

    a2 = desk.feed.open("XYZ", 100.00, at("10:41:00"))             # the same positions, their very averages
    desk.feed.open("ABCD", 50.00, at("10:41:00"))
    run(desk, "10:41:01")
    run(desk, "10:41:06")
    run(desk, "10:41:10")
    assert held(desk, "XYZ") == 4 and held(desk, "ABCD") == 9
    assert len(desk.broker.closed_orders()) == sent                # nothing sold, nothing bought
    assert any("very average" in (r["inputs"].get("why") or "") for r in lines_("note"))
    pos = lt_book.positions()[f"{HOST}|long|XYZ"]
    assert pos["row_id"].endswith(f"{at('10:41:00'):.0f}") and pos["steps"] == 1

    desk.feed.close(a2, at("10:45:00"))                            # and the host's real close still sells
    run(desk, "10:45:01")
    assert held(desk, "XYZ") == 0 and held(desk, "ABCD") == 9
