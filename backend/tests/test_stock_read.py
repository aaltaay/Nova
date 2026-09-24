"""The bot's read on one stock (ADR 035): the plan, the indicators, the day's decisions, the groups
and the routes -- on facts shaped like APUS and PFSA on 2026-09-24."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from stock_read import decisions, history, indicators, plan, read, routes

ET = ZoneInfo("America/New_York")


def ts(hh: int, mm: int, day: str = "2026-09-24") -> float:
    y, mo, d = (int(x) for x in day.split("-"))
    return datetime(y, mo, d, hh, mm, tzinfo=ET).timestamp()


def bar(hh, mm, o, h, lo, c, v=10_000):
    return {"t": ts(hh, mm), "o": o, "h": h, "l": lo, "c": c, "v": v}


PFSA_ARMED = {
    "setup_type": "first_pullback", "state": "near", "reason": "0.03 under the 4.26 trigger -- read the tape",
    "chosen": True, "grade": "B", "kind": "first_pullback", "distance": 0.03,
    "setup": {"trigger": 4.26, "entry": 4.27, "stop": 4.1446, "risk": 0.1254, "target1": 4.5208, "leg_high": 4.44},
    "forming": None, "tape": {"verdict": "wait", "reasons": ["no green on the tape yet"]},
    "window": {"start": "07:00", "end": "11:30", "state": "open"},
    "rules": {"stop_cap": 0.20, "min_stop": 0.03, "target_r": 2.0, "target_mode": "leg_or_r"},
}
APUS_FLAG = {
    "setup_type": "bull_flag", "state": "leg", "chosen": False, "grade": None, "kind": "bull_flag",
    "reason": "pole +7.1% to 5.45; 1 red candle so far -- a flag needs 2 (one is a micro pullback)",
    "setup": None, "tape": None, "window": {"start": "07:00", "end": "11:30", "state": "after"},
    "forming": {"trigger": 5.43, "entry": 5.44, "stop": 5.33, "risk": 0.11, "target1": 5.66, "bars": 1,
                "blocked": None, "waiting": "1 more red or doji candle"},
    "rules": {"stop_cap": 0.20, "min_stop": 0.03, "target_r": 2.0, "target_mode": "leg_or_r"},
    "leg": {"t": ts(15, 1), "high": 5.45, "low": 5.09, "pct": 0.0707},
    "series": {"macd_hist": 0.0179, "macd_line": -0.0149, "macd_signal": -0.0328, "ema": 5.2851, "hod": 8.74},
}


# -- the plan -------------------------------------------------------------------------------------
def test_the_plan_follows_the_most_advanced_lane_and_says_it_is_at_least_two_to_one():
    watching = {"setup_type": "flat_top_breakout", "state": "watching", "forming": None, "setup": None}
    p = plan.build([watching, APUS_FLAG, PFSA_ARMED], {"price": 4.23, "levels": {}}, now=ts(8, 7))
    assert p["setup_type"] == "first_pullback" and p["state"] == "near" and p["provisional"] is False
    assert (p["entry"], p["stop"], p["target"]) == (4.27, 4.1446, 4.5208)
    assert p["risk"] == 0.1254 and p["rr"] == 2.0
    assert p["target_rule"] == "the higher of entry + 2 x risk and the leg high"
    assert {"id": "tape", "state": "warn", "text": "tape WAIT: no green on the tape yet"} in p["checks"]


def test_a_forming_setup_is_provisional_and_says_what_it_waits_for():
    p = plan.build([APUS_FLAG], {"price": 5.37, "levels": {"vwap": 6.09, "round_above": 5.5}}, now=ts(15, 3))
    assert p["state"] == "forming" and p["provisional"] is True
    assert (p["entry"], p["stop"], p["target"], p["risk"]) == (5.44, 5.33, 5.66, 0.11)
    assert "arms after 1 more red or doji candle" in p["reason"]
    texts = {c["id"]: c for c in p["checks"]}
    assert texts["risk"]["state"] == "ok"
    assert texts["vwap"] == {"id": "vwap", "state": "bad", "text": "under VWAP 6.09"}
    assert texts["window"]["text"] == "outside the bot's 07:00-11:30 window: a hand trade"
    assert [m["price"] for m in p["marks"]] == [5.5]            # the half dollar sits before the 5.66 target


def test_a_risk_over_the_cap_and_a_stop_inside_one_candle_are_named():
    lane = {**APUS_FLAG, "forming": {**APUS_FLAG["forming"], "stop": 5.14, "risk": 0.30, "target1": 6.04}}
    p = plan.build([lane], {"price": 5.37, "levels": {}, "median_range": 0.13}, now=ts(15, 3))
    assert {"id": "risk", "state": "bad", "text": "risk 0.30 is over the 0.20 stop cap"} in p["checks"]
    tight = plan.build([APUS_FLAG], {"price": 5.37, "levels": {}, "median_range": 0.13}, now=ts(15, 3))
    assert any(c["id"] == "candle" and c["state"] == "warn" for c in tight["checks"])


def test_a_hand_plan_stops_at_the_last_candles_low_and_aims_for_two_r():
    bars = [bar(15, 44, 4.70, 4.75, 4.61, 4.66), bar(15, 45, 4.66, 4.72, 4.63, 4.70), bar(15, 46, 4.70, 4.74, 4.65, 4.69)]
    p = plan.build([], {"price": 4.67, "levels": {}, "bars": bars}, now=ts(15, 47), entry=4.71)
    assert p["source"] == "manual" and p["stop"] == 4.61 and p["target"] == 4.91 and p["rr"] == 2.0
    own = plan.build([], {"price": 4.67, "levels": {}, "bars": bars}, now=ts(15, 47), entry=4.71, stop=4.66)
    assert own["stop"] == 4.66 and own["stop_rule"] == "your stop" and own["target"] == 4.81


def test_a_hand_plan_with_no_low_under_the_entry_asks_for_a_stop():
    bars = [bar(15, 45, 5.0, 5.1, 4.9, 5.0)]
    p = plan.build([], {"price": 4.8, "levels": {}, "bars": bars}, now=ts(15, 47), entry=4.85)
    assert p["stop"] is None and "name a stop" in p["reason"]
    assert p["checks"][0]["state"] == "unknown"


def test_a_large_seller_between_entry_and_target_is_in_the_way():
    ctx = {"price": 4.23, "levels": {}, "asks": [{"price": 4.30, "size": 30_000}, {"price": 4.45, "size": 120_000}]}
    p = plan.build([PFSA_ARMED], ctx, now=ts(8, 7))
    walls = [c for c in p["checks"] if c["id"] == "in_way_wall"]
    assert [w["state"] for w in walls] == ["warn", "bad"]
    assert "a seller of 30,000 at 4.30" in walls[0]["text"]


def test_nothing_forming_is_no_plan():
    assert plan.build([{"setup_type": "bull_flag", "state": "watching", "setup": None, "forming": None}],
                      {"levels": {}}, now=ts(15, 3)) is None


# -- indicators -----------------------------------------------------------------------------------
def test_levels_read_the_high_the_premarket_high_the_open_and_the_session_vwap():
    bars = [bar(4, 0, 2.3, 2.4, 2.2, 2.3, 1000), bar(8, 35, 3.0, 5.0, 3.0, 4.8, 900_000),
            bar(9, 29, 6.8, 7.31, 6.7, 6.99, 200_000), bar(9, 30, 6.99, 8.48, 6.85, 8.1, 2_000_000),
            bar(9, 32, 8.0, 8.74, 7.65, 8.25, 1_000_000)]
    lv = indicators.levels(bars, price=8.25, prev_close=2.29)
    assert lv["hod"] == {"price": 8.74, "ts": ts(9, 32)} and lv["pmh"] == 7.31 and lv["open"] == 6.99
    assert lv["round_above"] == 8.5 and lv["round_below"] == 8.0
    assert 4.0 < lv["vwap"] < 8.74


def test_the_open_is_unknown_before_the_regular_session():
    lv = indicators.levels([bar(8, 0, 2.0, 2.1, 1.9, 2.0)], price=2.0, prev_close=1.8)
    assert lv["open"] is None and lv["pmh"] == 2.1


def test_backside_names_a_topping_tail_on_the_high_of_day_candle():
    bars = [bar(10, i, 5.0 + i * 0.1, 5.1 + i * 0.1, 4.95 + i * 0.1, 5.08 + i * 0.1) for i in range(5)]
    bars.append(bar(10, 5, 5.5, 6.2, 5.45, 5.55, 90_000))       # a long upper wick at the new high
    warns = indicators.backside(bars)
    assert any("topping tail" in w for w in warns)


def test_volume_on_green_and_red_candles():
    bars = [bar(15, 0, 5.21, 5.45, 5.19, 5.33, 66_681), bar(15, 1, 5.33, 5.43, 5.31, 5.395, 64_683),
            bar(15, 2, 5.37, 5.43, 5.33, 5.36, 44_495)]
    assert indicators.volume_profile(bars, 10) == {"green": 131_364, "red": 44_495, "bars": 3}


# -- the day's decisions --------------------------------------------------------------------------
def jl(hh, mm, event, **kw):
    return {"schema_version": 1, "ts": ts(hh, mm), "event": event, "symbol": "APUS", **kw}


def test_the_journal_folds_repeats_and_keeps_the_reasons():
    lines = [
        jl(9, 3, "state", state="watching", reason="no fresh leg"),
        jl(9, 24, "leg", reason="new high 7.23 on a 25.6% leg -- wait for the pullback", leg={"high": 7.233}),
        jl(9, 26, "state", state="pullback", reason="risk 0.29 (+0.01 slippage) is over 0.20"),
        jl(9, 27, "state", state="pullback", reason="risk 0.29 (+0.01 slippage) is over 0.20"),
        jl(9, 29, "state", state="failed", reason="pullback ran past 3 candles"),
        jl(15, 3, "state", setup_type="bull_flag", state="leg", reason="pole +7.1% to 5.45; 1 red candle so far"),
        jl(15, 4, "state", setup_type="bull_flag", state="watching", reason="no pole"),
        jl(15, 5, "state", setup_type="bull_flag", state="watching", reason="no pole"),
    ]
    events = decisions.fold_journal(lines)
    titles = [e["title"] for e in events]
    assert titles == ["Watching: no fresh leg", "New high 7.23 on a 25.6% leg -- wait for the pullback",
                      "Not armed: risk 0.29 (+0.01 slippage) is over 0.20", "Dropped: pullback ran past 3 candles",
                      "Forming: pole +7.1% to 5.45; 1 red candle so far", "Watching: no pole"]
    assert events[2]["count"] == 2 and events[2]["last_ts"] == ts(9, 27)
    assert events[5]["lane"] == "bull_flag" and events[5]["count"] == 2
    s = decisions.summarize(events)
    assert s["legs"] == 1 and s["armed"] == 0
    assert "armed nothing" in s["text"] and "risk 0.29 (+0.01 slippage) is over 0.20 (x2)" in s["text"]


def test_tape_flips_inside_a_minute_are_one_event():
    lines = [jl(8, 6, "tape", verdict="veto", reasons=["spread 0.06 is wider than 0.05"]),
             {**jl(8, 6, "tape", verdict="wait", reasons=["burst of red on the tape"]), "ts": ts(8, 6) + 1},
             {**jl(8, 6, "tape", verdict="go", reasons=["green on the tape"]), "ts": ts(8, 6) + 29}]
    [e] = decisions.fold_journal(lines)
    assert e["count"] == 3 and e["title"] == "Tape VETO / WAIT / GO" and e["detail"] == "green on the tape"


def test_the_timeline_says_which_source_failed_and_answers_with_the_rest(monkeypatch):
    monkeypatch.setattr(decisions, "_journal", lambda sym, date: [decisions._event(ts(9, 24), "first_pullback", "leg", "Leg")])
    monkeypatch.setattr(decisions, "_hod", lambda sym, date: (_ for _ in ()).throw(RuntimeError("no history")))
    for name in ("_borrow", "_bot", "_market"):
        monkeypatch.setattr(decisions, name, lambda sym, date: [])
    monkeypatch.setattr(decisions, "_news", lambda sym, date, now: [])
    out = decisions.timeline("apus", "2026-09-24", ts(16, 0))
    assert out["symbol"] == "APUS" and [e["title"] for e in out["events"]] == ["Leg"]
    assert out["sources"]["hod_momo"]["ok"] is False and "no history" in out["sources"]["hod_momo"]["error"]
    assert out["sources"]["journal"]["ok"] is True


# -- history --------------------------------------------------------------------------------------
def test_runs_are_forty_percent_highs_newest_first_and_today_is_marked():
    daily = [{"d": "2026-09-17", "o": 1.6, "h": 1.7, "l": 1.5, "c": 1.67, "v": 1},
             {"d": "2026-09-18", "o": 1.72, "h": 2.6771, "l": 1.7, "c": 1.80, "v": 1},
             {"d": "2026-09-23", "o": 1.98, "h": 2.43, "l": 1.74, "c": 2.43, "v": 1},
             {"d": "2026-09-24", "o": 2.40, "h": 8.74, "l": 1.86, "c": 5.18, "v": 1}]
    runs = history.runs(daily, "2026-09-24")
    assert [r["date"] for r in runs] == ["2026-09-24", "2026-09-18"]
    assert runs[0]["today"] is True and runs[1]["run_pct"] == round(2.6771 / 1.67 - 1, 4)


# -- the whole read -------------------------------------------------------------------------------
def facts(**over):
    base = {
        "symbol": "APUS", "now": ts(15, 3), "errors": {},
        "why": {"facts": {"symbol": "APUS", "price": 5.37, "change_pct": 1.345, "volume": 67_683_626,
                          "rel_volume": 769.0, "float_shares": None, "short_interest": 19_919.0,
                          "short_interest_ts": ts(0, 0, "2026-08-31"), "days_to_cover": 0.13,
                          "split": {"factor": "1:10", "ts": ts(0, 0, "2026-07-23"), "reverse": True, "days_ago": 63},
                          "halts": {"news": 0, "luld": 0, "volatility": 0, "other": 0},
                          "borrow": {"listed": False, "fee_rate": None, "available": None, "as_of": ts(15, 0),
                                     "open": {"listed": True, "fee_rate": 37.4, "available": 5000, "as_of": ts(7, 27)}},
                          "catalyst": {"verdict": "catalyst", "category": "contract_partnership", "strength": "strong",
                                       "title": "MindWave Signs 12-Month Contract", "source": "alpaca",
                                       "published_ts": ts(8, 33)}},
                "checks": [], "likely": {"kind": "news", "label": "Company news: contract / partnership (strong)",
                                         "detail": "...", "confidence": "likely"}, "derived": {}},
        "setups": {"followed": True, "followed_note": None, "setups": [APUS_FLAG]},
        "hod_momo": {"count": 330, "by_strategy": {"Running Up Alert": 301, "Squeeze Alert - Up 5% in 5min": 14},
                     "firsts": [{"ts": ts(8, 31), "price": 2.84, "name": "Squeeze Alert - Up 5% in 5min"}],
                     "last_ts": ts(9, 40), "decision": {"ts": ts(15, 2), "gate_blocked": None, "would_fire": False,
                                                        "strategies": [{"name": "Running Up Alert", "passed": False,
                                                                        "blocked_by": "surge:2.7 < 5.0% in 5min"}]},
                     "session_high": 8.74, "new_hod_age_sec": 19_800, "followed": True},
        "bars": [bar(9, 30, 6.99, 8.48, 6.85, 8.1, 2_150_083),
                 bar(15, 0, 5.21, 5.45, 5.19, 5.33, 66_681), bar(15, 1, 5.33, 5.43, 5.31, 5.395, 64_683),
                 bar(15, 2, 5.37, 5.43, 5.33, 5.36, 44_495)],
        "bars5": [],
        "l2": {"spread_dollars": 0.03, "bid_total": 7414, "ask_total": 906,
               "bids": [{"price": 5.36, "size": 2914}], "asks": [{"price": 5.39, "size": 200}, {"price": 5.47, "size": 206}]},
        "flow": {"score": -0.2, "label": "neutral"},
        "pulls": {"watching": True, "pulled_shares": 25_908, "filled_shares": 2196, "pulls": 68, "fills": 9,
                  "large_pulls": 4, "window_sec": 60,
                  "flags": [{"ts": ts(15, 3) - 5, "side": "bid", "why": "3 large bid levels pulled in 60 s"}]},
        "rvol": {"rvol_vs_adv_pace": 769.0, "rvol_5min": 1564.7, "average_volume": 112_084, "day_volume": 67_683_626},
        "prints_per_min": 462, "shortable": None, "halted": False,
        "bot": {"level": 1, "active": False, "chosen": "bull_flag", "allowlisted": True, "depth_line": True,
                "venue": "paper", "breakers": {"soft_usd": -50.0, "hard_usd": -200.0}, "trade": None},
        "board": "gappers",
    }
    base.update(over)
    return base


def test_the_read_answers_every_group_with_a_verdict_and_the_plan(monkeypatch):
    monkeypatch.setattr(history, "summary", lambda sym, now: {"daily": [], "daily_days": 250, "runs": []})
    out = read.build(facts())
    g = {x["id"]: x for x in out["groups"]}
    assert list(g) == ["in_play", "setups", "front", "tape", "short", "float", "halts"]
    assert (g["in_play"]["verdict"], g["in_play"]["value"]) == ("ok", "Yes")
    assert g["setups"]["value"] == "Flag forming" and g["setups"]["verdict"] == "warn"
    assert g["tape"]["value"] == "Pulls" and g["short"]["value"] == "No lend"
    assert g["float"]["value"] == "Unknown" and g["halts"]["value"] == "No halts"
    front = {r["id"]: r for r in g["front"]["rows"]}
    assert front["macd_1m"]["state"] == "ok" and "setup scanner's own" in front["macd_1m"]["source"]
    assert front["vwap"]["state"] == "bad"
    assert out["plan"]["entry"] == 5.44 and out["plan"]["provisional"] is True
    assert out["prev_close"] == round(5.37 / 2.345, 4)
    assert sum(out["counts"].values()) == sum(len(x["rows"]) for x in out["groups"])


def test_a_read_with_nothing_known_states_it_row_by_row(monkeypatch):
    monkeypatch.setattr(history, "summary", lambda sym, now: None)
    empty = {k: None for k in ("why", "setups", "hod_momo", "l2", "flow", "pulls", "rvol", "prints_per_min",
                               "shortable", "halted", "bot", "board")}
    out = read.build({"symbol": "ZZZZ", "now": ts(12, 0), "errors": {}, "bars": [], "bars5": [], **empty})
    assert out["plan"] is None and out["followed"] is False
    for group in out["groups"]:
        for r in group["rows"]:
            assert r["state"] in ("unknown", "info", "warn", "ok", "bad")
            if r["state"] == "unknown":
                assert r["detail"] or r["value"], r            # every unknown says why or what
    halted = {r["id"]: r for r in out["groups"][6]["rows"]}["halted"]
    assert halted["state"] == "unknown" and halted["value"] == "Not known"


def test_the_route_serves_the_read_and_caches_it(monkeypatch):
    calls = []
    monkeypatch.setattr(routes.gather, "gather", lambda sym, now: calls.append(sym) or facts(symbol=sym))
    monkeypatch.setattr(history, "summary", lambda sym, now: None)
    routes._cache.clear()
    app = FastAPI()
    app.include_router(routes.router)
    client = TestClient(app)
    body = client.get("/api/stock-read/apus").json()
    assert body["schema_version"] == 1 and body["symbol"] == "APUS"
    client.get("/api/stock-read/APUS")
    assert calls == ["APUS"]                                   # the second poll inside 2 s is the cached read
    manual = client.get("/api/stock-read/APUS?entry=5.39").json()
    assert manual["plan"]["source"] == "manual"
    assert client.get("/api/stock-read/%20").status_code in (400, 404)
    assert client.get("/api/stock-read/APUS/decisions?date=24-09-2026").status_code == 400


@pytest.mark.parametrize("gate,expected", [("master_liquidity:volume(13000<100000)", "under the tradeable floor's volume"),
                                           ("blocklist", "on the HOD Momo blocklist")])
def test_a_refused_hod_momo_gate_is_said_in_words(gate, expected):
    from stock_read.rows import _hod_now

    r = _hod_now({"decision": {"ts": ts(9, 0), "gate_blocked": gate, "strategies": []}})
    assert r["state"] == "bad" and r["detail"] == expected
