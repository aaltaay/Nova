"""The Global page (ADR 060): each market's clock, money from real trades, the board, and its place last in line.

Every number on the page is IBKR's or a sum of IBKR's (the operator, 2026-10-20: "we shouldn't have estimate unless
we must"); these pin the arithmetic on hand-made bars, the fall back to a market's ETF when IBKR refuses its future,
and that the reader never spends the last of IBKR's historical budget.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import constants_global_board as cg
from constants_market_board import MARKET_HISTORY_HEADROOM
from followed_traders.constants_followed import FOLLOWED_EXIT_HEADROOM
from global_board import board, contracts, flows, jobs, keep, markets, reads, refresh
from global_board.state import store
from ibkr.historical_pacing import kind_of


def ts(text: str) -> float:
    """``2026-10-20T03:00`` as UTC epoch seconds."""
    return datetime.fromisoformat(text).replace(tzinfo=timezone.utc).timestamp()


@pytest.fixture(autouse=True)
def _clean():
    refresh.reset_for_tests()
    contracts.reset_for_tests()
    yield
    refresh.reset_for_tests()


def m(market_id: str):
    got = markets.by_id(market_id)
    assert got is not None
    return got


# -- each market's clock ------------------------------------------------------------------------------------------

def test_tokyo_lunch_is_a_break_between_two_segments():
    now = ts("2026-10-20T03:00")                     # 12:00 in Tokyo
    assert markets.state(m("jp"), now) == "break"
    day, segs = markets.shown(m("jp"), now)
    assert day.isoformat() == "2026-10-20" and len(segs) == 2
    assert markets.state(m("jp"), ts("2026-10-20T01:00")) == "open"     # 10:00
    assert markets.state(m("jp"), ts("2026-10-20T07:00")) == "closed"   # 16:00


def test_tadawul_trades_on_sunday_and_not_on_friday():
    assert markets.state(m("sa"), ts("2026-10-18T08:00")) == "open"     # Sunday 11:00 Riyadh
    assert markets.state(m("sa"), ts("2026-10-23T08:00")) == "closed"   # Friday


def test_london_hours_follow_its_own_summer_time():
    assert markets.state(m("uk"), ts("2026-10-20T07:30")) == "open"     # 08:30 BST
    assert markets.state(m("uk"), ts("2026-10-27T07:30")) == "closed"   # 07:30 GMT: before the open


def test_before_the_open_the_last_session_is_shown():
    now = ts("2026-10-20T12:00")                     # 08:00 in New York
    day, _segs = markets.shown(m("us"), now)
    assert day.isoformat() == "2026-10-19"
    assert markets.next_open_at(m("us"), now) == ts("2026-10-20T13:30")


def test_the_us_row_reads_the_nyse_calendar():
    assert markets.state(m("us"), ts("2026-12-25T15:00")) == "holiday"
    view = markets.session_view(m("us"), ts("2026-12-25T15:00"))
    assert view["date"] == "2026-12-24" and view["calendar"] == "nyse"


# -- money from bars ----------------------------------------------------------------------------------------------

BARS = [
    {"t": 0.0, "close": 10.0, "volume": 1.0, "average": 10.0},
    {"t": 60.0, "close": 11.0, "volume": 2.0, "average": 10.5},
    {"t": 120.0, "close": 10.5, "volume": 3.0, "average": 10.7},
    {"t": 180.0, "close": 10.5, "volume": 1.0, "average": 10.5},
]


def test_a_bar_is_up_or_down_by_its_close_and_weighs_its_notional():
    got = flows.sums(flows.classify(BARS, 2.0), [(0.0, 240.0)])
    assert got["up"] == pytest.approx(42.0)          # 2 x 10.5 x 2
    assert got["down"] == pytest.approx(64.2)        # 3 x 10.7 x 2
    assert got["flat"] == pytest.approx(41.0)        # the first bar, and an unchanged close
    assert got["traded"] == pytest.approx(147.2)
    assert flows.pressure_pct(got["up"], got["down"], got["traded"]) == pytest.approx(-15.08, abs=0.01)


def test_only_bars_inside_the_session_count():
    got = flows.sums(flows.classify(BARS, 1.0), [(60.0, 120.0)])
    assert got["bars"] == 1 and got["up"] == pytest.approx(21.0) and got["down"] == 0.0


def test_hours_bucket_the_net_money_by_the_hour_a_bar_started():
    bars = [{"t": 3600.0 * 5 + 60 * i, "close": 10.0 + (i % 2), "volume": 1.0, "average": 10.0} for i in range(4)]
    got = flows.hours(flows.classify(bars, 1.0), [(0.0, 3600.0 * 6)])
    assert got == [[3600.0 * 5, 10.0, 40.0]]         # a flat first bar, then up, down, up: +10 -10 +10


def test_the_move_is_the_session_close_against_the_last_session_close():
    bars = [{"t": 100.0, "close": 50.0}, {"t": 200.0, "close": 49.0}, {"t": 1000.0, "close": 51.0},
            {"t": 1100.0, "close": 52.0}, {"t": 5000.0, "close": 60.0}]
    got = flows.move_from_bars(bars, [(900.0, 1200.0)], [(0.0, 300.0)])
    assert got == {"pct": pytest.approx(6.122, abs=0.001), "last": 52.0, "prev_close": 49.0}


def test_seven_days_count_each_session_by_the_index_close():
    sign = [{"date": f"2026-10-{d:02d}", "close": c} for d, c in ((12, 100), (13, 101), (14, 100), (15, 100))]
    notional = [{"date": f"2026-10-{d:02d}", "close": 1.0, "volume": 10.0, "average": 2.0} for d in (13, 14, 15)]
    got = flows.daily_sums(notional, sign, 5, 3.0)
    assert (got["up"], got["down"], got["flat"], got["sessions"]) == (60.0, 60.0, 60.0, 3)
    assert flows.daily_move(sign, 3) == {"pct": 0.0, "last": 100, "prev_close": 100, "from": "2026-10-12",
                                         "to": "2026-10-15"}


# -- the fall back to an ETF ----------------------------------------------------------------------------------------

def test_a_refused_future_is_remembered_and_the_etf_is_read(monkeypatch):
    now = ts("2026-10-20T01:00")
    asked: list[str] = []

    def fake_bars(kind, spec, trading_date, **kw):
        asked.append(f"{kind}:{spec['symbol']}")
        if kind == "future":
            raise reads.Refused("10089: Requested market data requires additional subscription for API")
        return {"bars": BARS, "instrument": contracts.instrument("etf", spec)}

    monkeypatch.setattr(reads, "bars", fake_bars)
    monkeypatch.setattr(reads, "history_ok", lambda: True)
    got = jobs.read_flow(store(), m("jp"), now)
    assert asked == ["future:N225", "etf:EWJ"]
    assert got["basis"] == "etf" and got["instrument"]["symbol"] == "EWJ"
    assert jobs.refused(store(), "future:N225:OSE.JPN", now)["error"].startswith("10089")
    asked.clear()
    jobs.read_flow(store(), m("jp"), now + 60)
    assert asked == ["etf:EWJ"]                       # not asked again for hours


def test_a_refused_index_quote_is_not_asked_again(monkeypatch):
    now = ts("2026-10-20T01:00")
    asked: list[list[str]] = []

    def fake_quotes(markets_, trading_date):
        asked.append([m_["id"] for m_ in markets_])
        return {m_["id"]: ({"error": "354: Requested market data is not subscribed", "pct": None}
                           if m_["id"] == "jp" else {"error": None, "pct": 0.1}) for m_ in markets_}

    monkeypatch.setattr(reads, "index_quotes", fake_quotes)
    jobs.read_quotes(store(), now)
    assert "jp" in asked[0]
    assert jobs.refused(store(), "index:N225:OSE.JPN", now)["error"].startswith("354")
    jobs.read_quotes(store(), now + 60)
    assert "jp" not in asked[1] and "de" in asked[1]


def test_an_open_market_is_read_on_its_cadence_and_a_closed_one_once_after_its_close():
    st = store()
    jp = m("jp")
    open_now = ts("2026-10-20T01:00")                # Tokyo open
    st.put("flow:jp", {**_flow("future", "JPY", 1.0, 1.0), "session_date": "2026-10-20", "read_at": open_now},
           open_now)
    assert not jobs.flow_due(st, jp, open_now + 60, wanted=True)
    assert jobs.flow_due(st, jp, open_now + cg.GLOBAL_FLOW_TTL_SEC, wanted=True)
    after_close = ts("2026-10-20T06:40")             # 15:40 in Tokyo, ten minutes after the close
    assert jobs.flow_due(st, jp, after_close, wanted=False)
    st.put("flow:jp", {**_flow("future", "JPY", 1.0, 1.0), "session_date": "2026-10-20", "read_at": after_close},
           after_close)
    assert not jobs.flow_due(st, jp, after_close + 3600, wanted=True)


# -- the board ----------------------------------------------------------------------------------------------------

def _flow(basis: str, currency: str, up: float, down: float, flat: float = 0.0, hours=None) -> dict:
    return {"basis": basis, "currency": currency, "instrument": {"kind": basis, "symbol": "X", "label": "X",
            "exchange": "X", "currency": currency, "contract": None, "multiplier": 1.0},
            "session_date": "2026-10-20", "from": 0.0, "to": 1.0,
            "sums": {"up": up, "down": down, "flat": flat, "traded": up + down + flat, "bars": 10,
                     "last_bar_at": 1.0},
            "hours": hours or [], "move": {"pct": 0.5, "last": 1.0, "prev_close": 1.0}, "read_at": 1.0}


def test_dollars_come_from_ibkr_exchange_rates_and_regions_add_up():
    now = ts("2026-10-20T15:00")
    st = store()
    st.put("flow:us", _flow("future", "USD", 300.0, 100.0), now)
    st.put("flow:jp", _flow("future", "JPY", 10_000.0, 30_000.0), now)
    st.put("fx:JPY", {"currency": "JPY", "usd_per_unit": 0.0066, "date": "2026-10-19", "read_for": "2026-10-20"}, now)
    st.put("flow:de", _flow("future", "EUR", 100.0, 50.0), now)            # no EUR rate yet
    got = board.compose(st, now, enabled=True, replay_desk=False, period="1D")
    rows = {r["id"]: r for r in got["markets"]}
    assert rows["us"]["flow"]["pressure_usd"] == 200.0
    assert rows["jp"]["flow"]["pressure_usd"] == pytest.approx(-132.0)
    assert rows["jp"]["flow"]["fx"]["usd_per_unit"] == 0.0066
    assert rows["de"]["flow"]["pressure_usd"] is None and "EUR" in rows["de"]["flow"]["error"]
    assert rows["de"]["flow"]["pressure_pct"] == pytest.approx(33.33, abs=0.01)   # unit-free, still measured
    asia = next(r for r in got["regions"] if r["id"] == "asia_pacific")
    assert asia["pressure_usd"] == pytest.approx(-132.0) and asia["flows"] == 1
    assert got["world"]["flows"] == 2
    assert rows["sa"]["flow"]["error"] == board.WAITING and rows["sa"]["flow"]["pressure_usd"] is None


def test_rotation_when_regions_pull_opposite_ways():
    world = {"flows": 6, "markets": 16, "pressure_pct": 1.0}
    regions = [{"label": "Americas", "flows": 3, "pressure_pct": 12.0, "pressure_usd": 900.0},
               {"label": "Asia-Pacific", "flows": 3, "pressure_pct": -9.0, "pressure_usd": -700.0}]
    got = board.read(world, regions)
    assert got["verdict"] == "rotation" and got["detail"] == "Asia-Pacific sold, Americas bought"
    assert board.read({**world, "pressure_pct": 7.0}, regions)["verdict"] == "money_in"
    assert board.read({**world, "flows": 2}, regions)["verdict"] is None


def test_a_market_whose_buyers_were_eager_while_its_index_fell_is_mixed():
    assert board._mixed({"pressure_pct": 12.0}, {"pct": -0.4})
    assert not board._mixed({"pressure_pct": 3.0}, {"pct": -0.4})       # too little pressure to call
    assert not board._mixed({"pressure_pct": 12.0}, {"pct": 0.4})


def test_the_sun_sums_the_last_24_hours_in_dollars_by_region():
    now = ts("2026-10-20T15:30")
    hour = ts("2026-10-20T14:00")
    st = store()
    st.put("flow:us", _flow("future", "USD", 1.0, 1.0, hours=[[hour, 50.0, 400.0], [hour - 30 * 3600, 9.0, 9.0]]),
           now)
    got = board.compose(st, now, enabled=True, replay_desk=False, period="1D")["sun"]
    assert len(got["hours"]) == 24 and got["to"] == ts("2026-10-20T16:00")
    row = next(h for h in got["hours"] if h["t"] == hour)
    assert row["net_usd"] == 50.0 and row["by_region"] == {"americas": 50.0} and row["markets"] == 1
    assert sum(h["traded_usd"] for h in got["hours"]) == 400.0             # 30 hours ago is outside the window
    assert any(s["market"] == "jp" for s in got["sessions"])


def test_a_closed_market_reads_its_index_close_and_an_open_one_its_live_quote():
    st = store()
    closed = ts("2026-10-20T08:00")                  # Tokyo closed for the day
    st.put("index_daily:jp", {"instrument": contracts.instrument("index", m("jp")["index"]),
                              "rows": [{"date": "2026-10-19", "close": 100.0}, {"date": "2026-10-20", "close": 98.0}],
                              "read_at": closed}, closed)
    st.put("flow:jp", _flow("future", "JPY", 1.0, 1.0), closed)
    row = board.market_row(st, m("jp"), closed, "1D", {}, None)
    assert row["move"]["basis"] == "index" and row["move"]["pct"] == -2.0
    now = ts("2026-10-20T01:00")                     # Tokyo open
    quotes = {"jp": {"pct": 0.8, "last": 1.0, "prev_close": 1.0, "at": now, "data_type": "live"}}
    row = board.market_row(st, m("jp"), now, "1D", quotes, now)
    assert row["move"]["basis"] == "index" and row["move"]["pct"] == 0.8 and row["move"]["data_type"] == "live"


def test_seven_and_thirty_days_count_completed_sessions_only():
    jp = m("jp")
    days = [f"2026-10-{d:02d}" for d in (9, 12, 13, 14, 15, 16, 19, 20)]
    rows = [{"date": d, "close": 100.0 + i} for i, d in enumerate(days)]
    open_now = ts("2026-10-20T01:00")                # Tokyo trading: the 20th's bar is still forming
    assert [r["date"] for r in board.completed(rows, jp, open_now)][-1] == "2026-10-19"
    closed = ts("2026-10-20T08:00")                  # after the close the 20th counts
    assert [r["date"] for r in board.completed(rows, jp, closed)][-1] == "2026-10-20"
    us_premarket = ts("2026-10-20T12:00")            # 08:00 ET: a future's 20th began overnight, not a session yet
    assert [r["date"] for r in board.completed(rows, m("us"), us_premarket)][-1] == "2026-10-19"
    st = store()
    st.put("index_daily:jp", {"instrument": contracts.instrument("index", jp["index"]), "rows": rows,
                              "read_at": open_now}, open_now)
    move = board.market_row(st, jp, open_now, "7D", {}, None)["move"]
    assert move["basis"] == "index" and move["last"] == 106.0 and move["prev_close"] == 101.0


def test_a_daily_read_taken_while_a_market_traded_is_read_again_after_its_close():
    st = store()
    jp = m("jp")
    open_now = ts("2026-10-20T01:00")
    st.put("daily_flow:jp", {"basis": "future", "rows": [], "read_at": open_now}, open_now)
    assert not jobs.daily_flow_due(st, jp, open_now + 600)
    assert jobs.daily_flow_due(st, jp, ts("2026-10-20T07:00"))   # 16:00 in Tokyo, after the close


def test_a_refused_etf_is_listed_with_ibkrs_words():
    now = ts("2026-10-20T15:00")
    st = store()
    jobs.remember_refusal(st, "etf", contracts.etf_spec("EWZ"), "200: No security definition has been found", now)
    row = board.market_row(st, m("br"), now, "1D", {}, None)
    assert row["flow"]["refused"] == [{"instrument": "EWZ (US-listed ETF)",
                                       "error": "200: No security definition has been found"}]


# -- last in line ---------------------------------------------------------------------------------------------------

def test_history_reads_wait_while_the_page_headroom_is_not_there(monkeypatch):
    now = ts("2026-10-20T01:00")
    monkeypatch.setattr(reads, "ready", lambda: True)
    monkeypatch.setattr(reads, "history_ok", lambda: False)
    monkeypatch.setattr(reads, "lines_ok", lambda: False)
    monkeypatch.setattr(reads, "bars", lambda *a, **k: pytest.fail("a history read ran without headroom"))
    store().want(now)
    assert not refresh.run_once(now)
    assert store().waiting_for() == "history"


def test_nobody_looking_never_reads_in_the_desks_own_hours(monkeypatch):
    monkeypatch.setattr(reads, "ready", lambda: True)
    monkeypatch.setattr(reads, "history_ok", lambda: True)
    monkeypatch.setattr(reads, "bars", lambda *a, **k: pytest.fail("read in the US session with nobody looking"))
    assert refresh.quiet_hours(ts("2026-10-20T15:00"))
    assert not refresh.run_once(ts("2026-10-20T15:00"))


def test_the_page_spends_the_history_budget_under_its_own_name():
    assert kind_of("global:1 min:TRADES:all") == "global"
    assert kind_of("ref:5 mins:TRADES:all") == "market"
    assert cg.GLOBAL_HISTORY_HEADROOM > FOLLOWED_EXIT_HEADROOM          # after the TraderTV exits and LULD
    assert cg.GLOBAL_HISTORY_HEADROOM == MARKET_HISTORY_HEADROOM       # and in turn with the Market page


def _market_page_shows(monkeypatch, shows: bool) -> None:
    from market_board import state as market_state

    monkeypatch.setattr(market_state.store(), "wanted", lambda now: shows)


def test_the_page_reads_while_more_than_its_headroom_is_left(monkeypatch):
    from ibkr import historical_service

    _market_page_shows(monkeypatch, False)
    for used, ok in ((60 - cg.GLOBAL_HISTORY_HEADROOM - 1, True), (60 - cg.GLOBAL_HISTORY_HEADROOM, False)):
        monkeypatch.setattr(historical_service, "pacing_snapshot", lambda u=used: {"window_max": 60, "window_used": u})
        assert reads.history_ok() is ok


def test_the_page_on_screen_goes_first(monkeypatch):
    now = ts("2026-10-20T01:00")
    _market_page_shows(monkeypatch, True)
    assert reads.headroom(now) == cg.GLOBAL_YIELD_HEADROOM          # the Market page shows, Global does not
    store().want(now)
    assert reads.headroom(now) == cg.GLOBAL_HISTORY_HEADROOM        # Global shows
    _market_page_shows(monkeypatch, False)
    assert reads.headroom(now + 3600) == cg.GLOBAL_HISTORY_HEADROOM  # neither: the two take turns


def test_history_reads_keep_the_market_pages_pace(monkeypatch):
    now = ts("2026-10-20T01:00")
    ran: list[str] = []
    monkeypatch.setattr(reads, "ready", lambda: True)
    monkeypatch.setattr(reads, "history_ok", lambda: True)
    monkeypatch.setattr(reads, "lines_ok", lambda: False)
    monkeypatch.setattr(refresh, "_run", lambda job, at: ran.append(job.key))
    store().want(now)
    assert refresh.run_once(now)
    assert not refresh.run_once(now + cg.GLOBAL_HISTORY_GAP_SEC / 2)  # its own pace: no second request yet
    assert store().waiting_for() != "history"                         # and not a wait on IBKR
    assert refresh.run_once(now + cg.GLOBAL_HISTORY_GAP_SEC)
    assert len(ran) == 2


# -- contracts ------------------------------------------------------------------------------------------------------

def test_a_future_ibkr_does_not_know_by_its_first_name_is_asked_by_the_next():
    import asyncio

    asked: list[tuple[str, str]] = []

    class FakeIb:
        async def qualifyContractsAsync(self, contract):
            asked.append((contract.symbol, contract.multiplier))
            if contract.symbol == "TSE60":
                return [None]                                     # IBKR: 200, no security definition
            contract.conId = 7
            return [contract]

    spec = markets.by_id("ca")["future"]
    assert spec["symbol"] == "TSE60" and spec["also"] == ("SXF",) and spec["multiplier"] == "200"
    got = asyncio.run(contracts.resolve(FakeIb(), "future", spec, "2026-10-20"))
    assert asked == [("TSE60", "200"), ("SXF", "200")] and got.symbol == "SXF"
    asked.clear()
    assert asyncio.run(contracts.resolve(FakeIb(), "future", spec, "2026-10-20")) is got   # kept for the day
    assert asked == []


# -- each market's size ----------------------------------------------------------------------------------------------

def test_every_market_carries_its_published_size_with_its_month_and_source():
    now = ts("2026-10-20T01:00")
    for mk in cg.GLOBAL_MARKETS:
        got = board.market_row(store(), mk, now, "1D", {}, None)["size"]
        assert got["usd"] > 1e11 and got["as_of"][:4] == "2026" and got["source"] and got["url"].startswith("https://")
    us = board.size("us")
    assert [p["name"] for p in us["parts"]] == ["NYSE", "Nasdaq"]
    assert us["usd"] == pytest.approx(sum(p["usd"] for p in us["parts"]))
    assert board.size("nowhere") is None


# -- kept across restarts -------------------------------------------------------------------------------------------

def test_answers_are_kept_and_another_schema_version_reads_as_absent():
    now = ts("2026-10-20T08:00")
    st = store()
    st.put("flow:jp", _flow("future", "JPY", 1.0, 2.0), now)
    assert keep.save(st, now) == 1
    st.reset()
    assert keep.load(st, now + 60) == 1 and st.get("flow:jp", now + 60)["basis"] == "future"
    data = json.loads(keep.path().read_text(encoding="utf-8"))
    keep.path().write_text(json.dumps({**data, "schema_version": 99}), encoding="utf-8")
    st.reset()
    assert keep.load(st, now + 60) == 0


# -- the route ------------------------------------------------------------------------------------------------------

def test_the_route_answers_from_memory_and_refuses_an_unknown_period(monkeypatch):
    from fastapi.testclient import TestClient

    from global_board.routes import router
    from fastapi import FastAPI

    monkeypatch.setattr(refresh, "start", lambda: None)
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    got = client.get("/api/global/board?period=1D")
    assert got.status_code == 200
    body = got.json()
    assert body["schema_version"] == 1 and len(body["markets"]) == len(cg.GLOBAL_MARKETS)
    assert body["markets"][0]["id"] == "us" and body["budget"]["history_headroom"] == cg.GLOBAL_HISTORY_HEADROOM
    bad = client.get("/api/global/board?period=2D")
    assert bad.status_code == 400 and bad.json()["detail"]["reason"] == "GLOBAL_BAD_PARAM"
