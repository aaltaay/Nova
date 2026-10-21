"""The Forex page (ADR 061): the FX day's clock, each currency's move and strength, the futures' money, the board, the
market's size as the BIS survey states it, and the page's place last in line for IBKR.

The market's size is the survey's, labelled; everything else is IBKR's or arithmetic on it (the operator, 2026-10-20:
"We got to also say the total market"). These pin the arithmetic on hand-made bars and quotes.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import constants_forex_board as cf
from constants_market_board import MARKET_HISTORY_HEADROOM
from forex_board import board, clock, contracts, jobs, keep, money, prices, reads, refresh
from forex_board.state import store
from ibkr.historical_pacing import kind_of

HOUR = 3600.0


def ts(text: str) -> float:
    """``2026-10-20T15:12`` as UTC epoch seconds."""
    return datetime.fromisoformat(text).replace(tzinfo=timezone.utc).timestamp()


NOW = ts("2026-10-20T15:12:30")                 # Tuesday 11:12:30 ET: London and New York open
DAY0 = ts("2026-10-19T21:00")                   # Monday 17:00 ET: the FX day began


@pytest.fixture(autouse=True)
def _clean():
    refresh.reset_for_tests()
    contracts.reset_for_tests()
    yield
    refresh.reset_for_tests()


def cur(code: str):
    return next(c for c in cf.FOREX_CURRENCIES if c["code"] == code)


# -- the FX day's clock ---------------------------------------------------------------------------------------------

def test_the_fx_day_runs_from_five_pm_new_york():
    fx = clock.day(NOW)
    assert (fx["from"], fx["to"], fx["open"], fx["date"]) == (DAY0, DAY0 + 24 * HOUR, True, "2026-10-20")
    assert clock.day(ts("2026-10-19T21:30"))["from"] == DAY0                   # Monday 17:30 ET: Tuesday's day


def test_the_weekend_shows_fridays_day_and_when_the_market_opens():
    fx = clock.day(ts("2026-10-24T16:00"))                                    # Saturday noon ET
    assert fx["open"] is False and fx["date"] == "2026-10-23"
    assert fx["from"] == ts("2026-10-22T21:00") and fx["to"] == ts("2026-10-23T21:00")
    assert fx["next_open_at"] == ts("2026-10-25T21:00")                       # Sunday 17:00 ET
    assert clock.day(ts("2026-10-23T20:59"))["open"] is True                  # Friday 16:59 ET
    assert clock.day(ts("2026-10-23T21:01"))["open"] is False                 # Friday 17:01 ET
    sunday = clock.day(ts("2026-10-25T22:00"))                                # Sunday 18:00 ET: Monday's day
    assert sunday["open"] is True and sunday["date"] == "2026-10-26"
    assert clock.previous_day(sunday)["date"] == "2026-10-23"                 # Monday's day comes after Friday's


def test_each_hour_belongs_to_the_newest_region_open():
    asia, london, new_york = clock.blocks(clock.day(NOW))
    assert (asia["from"], asia["to"]) == (DAY0, ts("2026-10-20T07:00"))       # London's 08:00 BST is 03:00 ET
    assert (london["from"], london["to"]) == (ts("2026-10-20T07:00"), ts("2026-10-20T12:00"))   # to New York's 08:00
    assert (new_york["from"], new_york["to"]) == (ts("2026-10-20T12:00"), DAY0 + 24 * HOUR)


def test_summer_time_moves_the_cities_never_the_rule():
    # 2026-10-27: London is back on GMT, New York still on EDT -- London's 08:00 is 04:00 ET that week.
    _asia, london, _ny = clock.blocks(clock.day(ts("2026-10-27T15:00")))
    assert london["from"] == ts("2026-10-27T08:00")


def test_the_tracks_are_the_cities_own_hours():
    asia, london, new_york = clock.tracks(clock.day(NOW))
    assert asia["from"] == DAY0                                               # Sydney's 08:00 AEDT
    assert asia["to"] == ts("2026-10-20T08:00")                               # Tokyo's 17:00 JST
    assert (london["from"], london["to"]) == (ts("2026-10-20T07:00"), ts("2026-10-20T16:00"))
    assert (new_york["from"], new_york["to"]) == (ts("2026-10-20T12:00"), ts("2026-10-20T21:00"))


def test_a_currencys_home_session_is_eight_to_five_in_its_city():
    fx = clock.day(NOW)
    assert clock.home("Europe/London", NOW, fx)["open"] is True               # 16:12 in London
    tokyo = clock.home("Asia/Tokyo", NOW, fx)                                 # 00:12 Wednesday in Tokyo
    assert tokyo["open"] is False and tokyo["next_open_at"] == ts("2026-10-20T23:00")
    saturday = ts("2026-10-24T09:00")                                         # Saturday 10:00 in London
    assert clock.home("Europe/London", saturday, clock.day(saturday))["open"] is False


# -- a currency's move and strength -------------------------------------------------------------------------------

def test_a_pair_quoted_per_dollar_moves_the_currency_the_other_way():
    assert prices.vs_usd(1.0, per_usd=False) == pytest.approx(1.0)            # EUR/USD up 1%: the euro up 1%
    assert prices.vs_usd(1.0, per_usd=True) == pytest.approx(-0.990099, abs=1e-6)   # USD/JPY up 1%: the yen down


def test_strength_is_against_an_even_mix_of_the_others():
    got = prices.strengths({"USD": 0.0, "EUR": 1.0, "JPY": -1.0})
    assert got["EUR"] == pytest.approx((1.0 + (1.01 / 0.99 - 1) * 100) / 2)
    assert got["USD"] == pytest.approx(((1 / 1.01 - 1) * 100 + (1 / 0.99 - 1) * 100) / 2)
    assert max(got, key=got.get) == "EUR" and min(got, key=got.get) == "JPY"
    assert prices.cross(1.0, -1.0) == pytest.approx((1.01 / 0.99 - 1) * 100)  # EUR/JPY from the dollar moves


def _hourly(start: float, closes: list[float]) -> list[dict]:
    return [{"t": start + i * HOUR, "close": c, "high": c + 0.01, "low": c - 0.01} for i, c in enumerate(closes)]


def test_the_days_open_is_the_close_at_its_start_and_each_hour_its_bars_close():
    bars = _hourly(DAY0 - 2 * HOUR, [1.10, 1.20, 1.21, 1.22])                # 15:00, 16:00, then the day's 17:00, 18:00
    day = prices.day_from_bars(bars, DAY0, DAY0 + 24 * HOUR)
    assert day["open"] == 1.20 and day["closes"][:3] == [1.21, 1.22, None] and day["last"] == 1.22
    levels = prices.hour_levels(day["closes"], 3.5, 1.25, day["open"])       # 3.5 hours in, the quote 1.25
    assert levels == [1.21, 1.22, 1.22, 1.25]                                 # carried, then the forming hour


def test_a_session_change_is_the_strength_over_its_hours():
    path = [{"USD": 0.0, "EUR": 0.1}, {"USD": -0.1, "EUR": 0.3}, {"USD": -0.2, "EUR": 0.5}]
    assert prices.block_change(path, "EUR", 0, 1) == pytest.approx(0.1)
    assert prices.block_change(path, "EUR", 1, 3) == pytest.approx(0.4)
    assert prices.block_change(path, "EUR", 3, 5) is None                     # not begun
    assert prices.changes(path)[1] == {"USD": pytest.approx(-0.1), "EUR": pytest.approx(0.2)}


def test_seven_and_thirty_days_count_completed_fx_days_only():
    rows = [{"date": f"2026-10-{d:02d}", "close": 1.0 + d / 100} for d in range(1, 21)]
    done = prices.completed(rows, "2026-10-20", day_open=True)
    assert done[-1]["date"] == "2026-10-19"                                   # today's row is still forming
    got = prices.period_move(done, 5)
    assert got["to"] == "2026-10-19" and got["from"] == "2026-10-14"
    assert got["pct"] == pytest.approx((1.19 / 1.14 - 1) * 100)
    assert prices.completed(rows, "2026-10-20", day_open=False)[-1]["date"] == "2026-10-20"


def test_a_busy_day_is_its_range_against_a_normal_ones():
    rows = [{"date": f"d{i}", "high": 1.01, "low": 0.99, "close": 1.0} for i in range(20)]   # 2% a day
    assert prices.range_x(1.03, 1.0, 1.0, rows, 20) == pytest.approx(1.5)    # 3% so far
    assert prices.range_x(1.03, 1.0, 1.0, rows[:5], 20) is None               # too few days to call it normal


# -- the futures' money -------------------------------------------------------------------------------------------

BARS = [
    {"t": DAY0 - 60, "close": 1.10, "volume": 5.0, "average": 1.10},          # before the day: sets the first sign
    {"t": DAY0 + HOUR, "close": 1.11, "volume": 2.0, "average": 1.105},
    {"t": DAY0 + HOUR + 60, "close": 1.10, "volume": 4.0, "average": 1.10},
    {"t": DAY0 + 2 * HOUR, "close": 1.10, "volume": 1.0, "average": 1.10},
]


def test_a_future_in_dollars_per_unit_weighs_its_notional_in_dollars():
    got = money.sums(money.classify(BARS, 125_000), DAY0, DAY0 + 24 * HOUR)
    assert got["up"] == pytest.approx(2 * 1.105 * 125_000)
    assert got["down"] == pytest.approx(4 * 1.10 * 125_000)
    assert got["flat"] == pytest.approx(1 * 1.10 * 125_000) and got["contracts"] == 7.0
    assert money.pressure_pct(got["up"], got["down"], got["traded"]) < 0
    hours = money.hours(money.classify(BARS, 125_000), DAY0)
    assert hours[1] == [pytest.approx((2 * 1.105 - 4 * 1.10) * 125_000), pytest.approx(6.6 * 125_000 + 0.01 * 125_000)]


def test_an_inverted_future_is_worth_its_multiplier_and_an_up_bar_sells_the_currency():
    # USD/CNH: priced in yuan per dollar, worth $100,000 -- an up bar is the dollar bought, the yuan sold.
    bars = [{"t": 0.0, "close": 7.10, "volume": 1.0}, {"t": 60.0, "close": 7.12, "volume": 3.0}]
    got = money.sums(money.classify(bars, 100_000, inverted=True), 0.0, 120.0)
    assert got["down"] == pytest.approx(300_000) and got["up"] == 0.0 and got["flat"] == pytest.approx(100_000)


def test_days_count_by_the_currencys_own_move():
    spot = [{"date": "2026-10-15", "close": 150.0}, {"date": "2026-10-16", "close": 151.0},
            {"date": "2026-10-19", "close": 150.5}]
    signs = money.day_signs(spot, per_usd=True)                                # USD/JPY up: the yen down
    assert signs == {"2026-10-16": -1, "2026-10-19": 1}
    rows = [{"date": d, "close": 0.0066, "volume": 10.0, "average": 0.0066} for d in ("2026-10-16", "2026-10-19")]
    got = money.daily_sums(rows, signs, 12_500_000, False)
    assert got["down"] == pytest.approx(10 * 0.0066 * 12_500_000) and got["up"] == got["down"]
    assert money.normal_volume(rows, 2) == 10.0 and money.normal_volume(rows, 20) is None


# -- the board ----------------------------------------------------------------------------------------------------

def _fill(st, moves: dict[str, float], at: float = NOW) -> None:
    """Each currency's spot pair moved ``moves[code]`` percent (pair terms) since 17:00 ET, in hourly bars to now."""
    quotes = {}
    for code, pct in moves.items():
        c = cur(code)
        open_level = 1.0
        last = open_level * (1 + pct / 100)
        bars = _hourly(DAY0 - HOUR, [open_level] + [open_level + (last - open_level) * (h + 1) / 18 for h in range(18)])
        st.put(f"hourly:{code}", {"fx_from": DAY0, "fx_date": "2026-10-20",
                                   "day": prices.day_from_bars(bars, DAY0, DAY0 + 24 * HOUR),
                                   "instrument": contracts.instrument("spot", contracts.spot_spec(c)), "read_at": at},
               at)
        quotes[code] = {"bid": last, "ask": last, "mid": last, "data_type": "live", "at": at, "error": None}
    st.put("quotes", quotes, at)


def _flow(code: str, up: float, down: float, at: float = NOW) -> dict:
    spec = contracts.future_spec(cur(code))
    return {"fx_from": DAY0, "fx_date": "2026-10-20",
            "sums": {"up": up, "down": down, "flat": 0.0, "traded": up + down, "contracts": 100.0, "bars": 10,
                     "last_bar_at": at - 30},
            "hours": [[3, up - down, up + down]], "levels": {"open": None, "last": None, "high": None, "low": None,
                                                           "closes": [None] * 24},
            "instrument": contracts.instrument("future", spec), "inverted": spec["inverted"], "read_at": at}


RISK_OFF = {"EUR": -0.18, "JPY": -0.42, "GBP": -0.31, "CHF": -0.14, "AUD": -0.58, "CAD": 0.22, "NZD": -0.49,
            "MXN": 0.66, "ZAR": 0.83, "SEK": 0.35, "NOK": 0.44, "SGD": 0.12, "HKD": 0.01, "CNY": 0.04}


def compose(period: str = "1D", now: float = NOW) -> dict:
    return board.compose(store(), now, enabled=True, replay_desk=False, period=period)


def test_the_whole_market_comes_from_the_bis_survey_labelled():
    got = compose()["market"]
    assert got["total_usd"] == pytest.approx(9.51024e12) and got["as_of"] == "2025-04"
    assert got["source"].startswith("BIS") and got["url"].startswith("https://www.bis.org/")
    assert got["covered_pct"] == pytest.approx(95.3, abs=0.1)                # the 19 currencies, two to a trade
    assert [d["name"] for d in got["desks"][:4]] == ["UK", "US", "Singapore", "Hong Kong"]
    assert got["desks"][0]["share_pct"] == pytest.approx(37.8, abs=0.1)
    assert got["exchange_traded_usd"] == pytest.approx(2.01e11)


def test_every_currency_carries_its_bis_size_biggest_first():
    rows = compose()["currencies"]
    assert [r["code"] for r in rows][:5] == ["USD", "EUR", "JPY", "GBP", "CNY"] and len(rows) == 19
    usd = rows[0]["size"]
    assert usd["share_pct"] == pytest.approx(89.08, abs=0.01) and usd["rank"] == 1 and usd["pair"] == "EUR/USD"


def test_safe_havens_bought_when_the_yen_and_franc_rise_and_the_riskier_fall():
    _fill(store(), RISK_OFF)
    got = compose()
    by = {r["code"]: r for r in got["currencies"]}
    assert by["EUR"]["price"]["vs_usd_pct"] == pytest.approx(-0.18, abs=1e-4)   # EUR/USD: the pair's own move
    assert by["JPY"]["price"]["pair"] == "USD/JPY" and by["JPY"]["price"]["vs_usd_pct"] > 0.4
    assert got["read"]["verdict"] == "safe_havens" and got["read"]["headline"] == "Safe havens bought"
    assert got["read"]["rose"][0] == "JPY" and got["read"]["fell"][0] == "ZAR"
    assert "the yen" in got["read"]["detail"]
    assert "HKD" not in got["read"]["rose"] + got["read"]["fell"]             # pegged: never named
    assert got["dollar"]["priced"] == 14 and got["dollar"]["up_against"] + got["dollar"]["down_against"] == 14


def test_a_currency_ibkr_does_not_price_says_why_and_takes_no_part():
    st = store()
    _fill(st, RISK_OFF)
    jobs.remember_refusal(st, "spot", contracts.spot_spec(cur("INR")), "200: No security definition has been found", NOW)
    by = {r["code"]: r for r in compose()["currencies"]}
    assert by["INR"]["price"]["vs_usd_pct"] is None and by["INR"]["strength_pct"] is None
    assert by["INR"]["price"]["error"].startswith("200")
    assert by["KRW"]["price"]["error"] == "waiting for IBKR"


def test_the_real_moves_by_its_future_when_its_spot_is_refused():
    st = store()
    _fill(st, RISK_OFF)
    jobs.remember_refusal(st, "spot", contracts.spot_spec(cur("BRL")), "200: No security definition", NOW)
    flow = _flow("BRL", 1e6, 3e6)
    flow["levels"] = {"open": 0.2000, "last": 0.1980, "last_t": NOW - 60, "high": 0.2001, "low": 0.1979,
                      "closes": [0.1990] * 18 + [None] * 6}
    st.put("flow:BRL", flow, NOW)
    brl = {r["code"]: r for r in compose()["currencies"]}["BRL"]
    assert brl["price"]["basis"] == "future" and brl["price"]["pair"] == "USD/BRL"
    assert brl["price"]["vs_usd_pct"] == pytest.approx(-1.0)                  # 6L in dollars per real fell 1%
    assert brl["price"]["rate"] == pytest.approx(1 / 0.198, rel=1e-6)          # shown as the market quotes it
    assert brl["futures"]["pressure_pct"] == pytest.approx(-50.0)


def test_the_dollars_futures_are_the_other_side_of_every_future():
    st = store()
    _fill(st, RISK_OFF)
    st.put("flow:EUR", _flow("EUR", 4e9, 6e9), NOW)                           # the euro sold $2B
    st.put("flow:JPY", _flow("JPY", 5e9, 2e9), NOW)                           # the yen bought $3B
    got = compose()
    usd = got["currencies"][0]["futures"]
    assert usd["basis"] == "sum" and usd["traded_usd"] == pytest.approx(17e9)
    assert usd["pressure_usd"] == pytest.approx(-1e9)                         # +2B from the euro, -3B from the yen
    assert got["dollar"]["pressure_usd"] == pytest.approx(-1e9)
    hour = got["sun"]["hours"][3]["futures"]
    assert hour["EUR"] == pytest.approx(-20.0) and hour["USD"] == pytest.approx(-100 * 1e9 / 17e9, abs=0.01)


def test_buyers_eager_while_the_currency_fell_is_mixed():
    st = store()
    _fill(st, RISK_OFF)
    st.put("flow:MXN", _flow("MXN", 6e8, 4e8), NOW)                           # +20%: bought, while the peso fell
    by = {r["code"]: r for r in compose()["currencies"]}
    assert by["MXN"]["strength_pct"] < -0.15 and by["MXN"]["mixed"] is True
    assert by["EUR"]["mixed"] is False


def test_the_sessions_name_what_rose_and_fell_in_their_hours():
    _fill(store(), RISK_OFF)
    got = compose()
    asia, london, new_york = got["sessions"]
    assert (asia["state"], london["state"], new_york["state"]) == ("done", "done", "now")
    assert asia["rose"]["code"] == "JPY" and asia["desks"]["share_pct"] == pytest.approx(28.1, abs=0.1)
    assert london["desks"]["label"] == "UK desks" and new_york["desks"]["share_pct"] == pytest.approx(18.6, abs=0.1)
    jpy = {r["code"]: r for r in got["currencies"]}["JPY"]
    assert sum(v for v in jpy["by_session"].values() if v is not None) == pytest.approx(jpy["strength_pct"], abs=0.02)


def test_follow_the_sun_holds_the_hours_begun():
    _fill(store(), RISK_OFF)
    sun = compose()["sun"]
    assert len(sun["hours"]) == 19 and sun["hours"][0]["t"] == DAY0           # 17:00 to the 11:00 hour forming
    assert {t["id"] for t in sun["tracks"]} == {"asia", "london", "new_york"}
    assert sun["tracks"][1]["share_pct"] == pytest.approx(37.8, abs=0.1)


# -- the reads, last in line --------------------------------------------------------------------------------------

def test_a_refused_pair_is_remembered_and_not_asked_again(monkeypatch):
    asked: list[list[str]] = []

    def fake_quotes(currencies, trading_date):
        asked.append([c["code"] for c in currencies])
        return {c["code"]: {"mid": None, "error": "200: No security definition"} if c["code"] == "INR"
                else {"mid": 1.0, "error": None} for c in currencies}

    monkeypatch.setattr(reads, "spot_quotes", fake_quotes)
    jobs.read_quotes(store(), NOW)
    assert "INR" in asked[0]
    jobs.read_quotes(store(), NOW + 60)
    assert "INR" not in asked[1] and "EUR" in asked[1]


def test_each_pairs_hours_are_read_once_per_completed_hour():
    fx = clock.day(NOW)
    value = {"fx_from": DAY0, "read_at": ts("2026-10-20T15:02:30")}           # read at 11:02:30 ET
    assert jobs.hourly_due(value, fx, NOW) is False                           # the 11:00 hour still forming
    assert jobs.hourly_due(value, fx, ts("2026-10-20T16:02:30")) is True      # 12:02:30: the 11:00 hour is done
    assert jobs.hourly_due({**value, "fx_from": DAY0 - 24 * HOUR}, fx, NOW) is True   # a new FX day


def test_a_futures_flow_keeps_its_cadence_and_reads_once_more_after_the_close():
    fx = clock.day(NOW)
    value = {"fx_from": DAY0, "read_at": NOW - 300}
    assert jobs.flow_due(value, fx, NOW, wanted=True) is False
    assert jobs.flow_due(value, fx, NOW + 300, wanted=True) is True
    saturday = ts("2026-10-24T16:00")
    closed = clock.day(saturday)
    friday = {"fx_from": closed["from"], "read_at": closed["to"] - 600}
    assert jobs.flow_due(friday, closed, saturday, wanted=True) is True       # once after the close
    assert jobs.flow_due({**friday, "read_at": closed["to"] + 600}, closed, saturday, wanted=True) is False


def test_nobody_looking_reads_no_daily_bars_and_never_in_the_desks_hours(monkeypatch):
    names = [j.key for j in jobs.due(store(), NOW, wanted=False, period="1D")]
    assert names and not any(n.startswith(("daily:", "flow_daily:")) for n in names)
    monkeypatch.setattr(reads, "ready", lambda: True)
    monkeypatch.setattr(reads, "history_ok", lambda: True)
    monkeypatch.setattr(reads, "bars", lambda *a, **k: pytest.fail("read in the US session with nobody looking"))
    assert refresh.run_once(NOW) is False                                     # 11:12 ET on a Tuesday


def test_history_reads_wait_while_the_headroom_is_not_there(monkeypatch):
    monkeypatch.setattr(reads, "ready", lambda: True)
    monkeypatch.setattr(reads, "history_ok", lambda: False)
    monkeypatch.setattr(reads, "lines_ok", lambda: False)
    monkeypatch.setattr(reads, "bars", lambda *a, **k: pytest.fail("a history read ran without headroom"))
    store().want(NOW)
    assert refresh.run_once(NOW) is False and store().waiting_for() in ("lines", "history")


def test_the_page_spends_the_history_budget_under_its_own_name():
    assert kind_of("forex:1 hour:MIDPOINT:all") == "forex"
    assert cf.FOREX_HISTORY_HEADROOM == MARKET_HISTORY_HEADROOM               # in turn with the Market page


def _shows(monkeypatch, *, market: bool = False, global_page: bool = False) -> None:
    from global_board import state as global_state
    from market_board import state as market_state

    monkeypatch.setattr(market_state.store(), "wanted", lambda now: market)
    monkeypatch.setattr(global_state.store(), "wanted", lambda now: global_page)


def test_the_page_on_screen_goes_first(monkeypatch):
    from constants_global_board import GLOBAL_YIELD_HEADROOM
    from global_board import reads as global_reads

    _shows(monkeypatch, global_page=True)
    assert reads.headroom(NOW) == cf.FOREX_YIELD_HEADROOM                     # Global shows, Forex does not
    store().want(NOW)
    assert reads.headroom(NOW) == cf.FOREX_HISTORY_HEADROOM                   # Forex shows
    _shows(monkeypatch)
    assert global_reads.headroom(NOW) == GLOBAL_YIELD_HEADROOM                # and Global yields while Forex shows


# -- kept across restarts, and the route ----------------------------------------------------------------------------

def test_answers_are_kept_and_another_schema_version_reads_as_absent():
    st = store()
    st.put("flow:JPY", _flow("JPY", 1.0, 2.0), NOW)
    st.put("refused:spot:USDINR:IDEALPRO", {"error": "200"}, NOW)
    assert keep.save(st, NOW) == 2
    st.reset()
    assert keep.load(st, NOW + 60) == 2 and st.get("flow:JPY", NOW + 60)["sums"]["up"] == 1.0
    data = json.loads(keep.path().read_text(encoding="utf-8"))
    keep.path().write_text(json.dumps({**data, "schema_version": 99}), encoding="utf-8")
    st.reset()
    assert keep.load(st, NOW + 60) == 0


def test_the_route_answers_from_memory_and_refuses_an_unknown_period(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from forex_board.routes import router

    monkeypatch.setattr(refresh, "start", lambda: None)
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    bad = client.get("/api/forex/board", params={"period": "2D"})
    assert bad.status_code == 400 and bad.json()["detail"]["reason"] == "FOREX_BAD_PARAM"
    got = client.get("/api/forex/board", params={"period": "7D"}).json()
    assert got["schema_version"] == 1 and got["period"] == "7D" and len(got["currencies"]) == 19
    assert got["budget"]["history_headroom"] in (cf.FOREX_HISTORY_HEADROOM, cf.FOREX_YIELD_HEADROOM)
