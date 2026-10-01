"""The read while you hold the stock (ADR 036 amendment 2026-10-01).

Shaped on the operator's APUS Paper trade of 2026-09-24: bought at 5.30 at 08:44:48, added at 4.85; the
08:56:14 sweep printed 6.02 and was back at 5.30 six seconds later; the 08:56 candle closed 5.59 over $5.50
and the 08:58 candle 6.46 over $6.00; the 08:57 high 6.66 crossed $6.50 with no close over it. Fed the
position, the plan box had read "$5.50 is 42c above" at 6.64.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from stock_read import held, rounds
from stock_read.read import HELD_CHECK_IDS, held_read

ET = ZoneInfo("America/New_York")


def t(hm: str) -> float:
    h, m = map(int, hm.split(":"))
    return datetime(2026, 9, 24, h, m, tzinfo=ET).timestamp()


def bar(hm: str, o: float, h: float, lo: float, c: float, v: float = 10_000) -> dict:
    return {"t": t(hm), "o": o, "h": h, "l": lo, "c": c, "v": v}


# 08:30-08:58, the real candles' shape (closed by 08:59:05)
BARS = [
    bar("08:30", 2.26, 2.35, 2.26, 2.35), bar("08:31", 2.34, 3.18, 2.26, 2.33), bar("08:32", 2.33, 2.37, 1.86, 2.16),
    bar("08:33", 2.15, 3.05, 1.95, 2.93), bar("08:34", 2.89, 3.85, 2.89, 3.39), bar("08:35", 3.38, 5.00, 3.29, 3.77),
    bar("08:36", 3.78, 4.20, 3.74, 4.08), bar("08:37", 4.00, 5.31, 3.95, 4.40), bar("08:38", 4.37, 5.20, 4.20, 5.17),
    bar("08:39", 5.18, 5.50, 4.66, 4.93), bar("08:40", 4.93, 5.09, 4.66, 5.03), bar("08:41", 5.01, 5.28, 4.63, 5.05),
    bar("08:42", 5.07, 5.21, 4.80, 4.99), bar("08:43", 4.96, 5.15, 4.81, 4.97), bar("08:44", 4.95, 5.49, 4.85, 4.94),
    bar("08:45", 4.95, 5.09, 4.90, 4.97), bar("08:46", 4.94, 5.13, 4.90, 5.03), bar("08:47", 5.00, 5.08, 4.55, 4.74),
    bar("08:48", 4.75, 4.79, 4.30, 4.66), bar("08:49", 4.67, 4.98, 4.56, 4.60), bar("08:50", 4.60, 5.00, 4.60, 4.91),
    bar("08:51", 4.89, 4.95, 4.80, 4.80), bar("08:52", 4.80, 5.08, 4.74, 5.00), bar("08:53", 4.98, 5.38, 4.76, 4.85),
    bar("08:54", 4.86, 5.10, 4.85, 5.10), bar("08:55", 5.10, 5.50, 5.06, 5.27), bar("08:56", 5.27, 6.02, 5.10, 5.59),
    bar("08:57", 5.57, 6.66, 5.55, 5.98), bar("08:58", 6.00, 6.97, 5.96, 6.46),
]
SINCE = t("08:44") + 48           # the first buy
NOW = t("08:59") + 5


def zone(lo: float, hi: float, label: str, tag: str | None = None, price: float | None = None) -> dict:
    return {"lo": lo, "hi": hi, "price": price if price is not None else lo, "label": label, "tag": tag or label,
            "members": [], "strength": 3}


MAP = {"price": 6.64, "intraday": [
    zone(8.00, 8.00, "$8.00"), zone(7.50, 7.50, "$7.50"), zone(6.97, 7.00, "HOD 6.97 · $7.00", "HOD 6.97"),
    zone(6.50, 6.50, "$6.50", price=6.50), zone(6.00, 6.00, "$6.00", price=6.00), zone(5.50, 5.50, "$5.50 · double top", "$5.50"),
    zone(4.92, 4.92, "4.92 · VWAP", "VWAP 4.92"),
]}


def build(**over) -> dict:
    args = dict(bars=BARS, price=6.64, level_map=MAP, avg=5.075, qty=100, now=NOW, since=SINCE, stop=5.45,
                risk=0.445)
    args.update(over)
    return held.build(**args)


def test_a_close_breaks_a_round_and_a_sweep_only_trades_through_it():
    out = build()
    assert [b["round"] for b in out["broke"]] == [6.0, 5.5]
    assert out["broke"][0]["at"] == t("08:59") and out["broke"][0]["close"] == 6.46     # the 08:58 candle's close
    assert out["broke"][1]["at"] == t("08:57") and out["broke"][1]["close"] == 5.59
    assert [x["round"] for x in out["through"]] == [6.5]                               # 08:57 high 6.66, no close


def test_the_raise_is_five_cents_under_the_highest_broke_round_up_only_and_under_the_price():
    assert build()["raise"]["to"] == 5.95 and build()["raise"]["round"] == 6.0
    assert "Raise the stop to 5.95, 5c under $6.00" in build()["raise"]["text"]
    assert build(stop=5.95)["raise"] is None                       # never the same, never down
    under = build(price=5.94, stop=5.10)                           # 5.95 would be over the price: $5.50's 5.45
    assert under["raise"]["to"] == 5.45


def test_a_round_broken_before_you_held_offers_no_raise():
    out = build(since=t("08:59"))
    assert out["broke"] == [] and out["raise"] is None


def test_the_spike_alone_breaks_nothing():
    """At 08:56:20 (only the 08:55 candle closed since): 6.02 printed, the price is 5.30 -- no raise."""
    bars = BARS[:26]
    out = held.build(bars=bars, price=5.30, level_map=MAP, avg=5.075, qty=100, now=t("08:56") + 20, since=SINCE,
                     stop=4.63, risk=0.445)
    assert out["broke"] == [] and out["raise"] is None


def test_the_stop_is_novas_then_yours_then_proposed():
    assert build(nova_stop=5.95)["stop"] == {"price": 5.95, "source": "nova", "rule": "Nova's resting stop",
                                             "printed": False}  # the 08:58 low 5.96 stayed over it
    mine = build()["stop"]
    assert mine["source"] == "yours" and mine["price"] == 5.45
    proposed = build(stop=None, risk=None)["stop"]
    assert proposed["source"] == "proposed" and proposed["price"] == 5.10       # the 08:56-08:58 low
    assert "lowest low of the last 3" in proposed["rule"]


def test_a_proposed_stop_falls_back_to_the_zone_under_the_price():
    flat = [bar("08:50", 6.70, 6.75, 6.69, 6.72), bar("08:51", 6.72, 6.76, 6.70, 6.74), bar("08:52", 6.73, 6.75, 6.70, 6.71)]
    out = held.build(bars=flat, price=6.64, level_map=MAP, avg=6.70, qty=100, now=t("08:53"), since=t("08:50"))
    assert out["stop"]["source"] == "proposed" and out["stop"]["price"] == 6.49 and "1c under $6.50" in out["stop"]["rule"]


def test_the_target_is_your_two_to_one_and_says_when_it_traded():
    out = build()
    assert out["target"]["price"] == pytest.approx(5.965)
    assert out["target"]["traded_at"] == t("08:56")               # the sweep reached it
    assert "you are past it" in out["levels"]["target"]["text"]


def test_the_ladder_runs_from_the_levels_ahead_to_your_cost():
    roles = [(r["role"], r["price"]) for r in build()["ladder"]]
    assert roles == [("then", 7.5), ("next", 6.97), ("now", 6.64), ("through", 6.5), ("broke", 6.0), ("broke", 5.5),
                     ("stop", 5.45), ("cost", 5.075)]
    nxt = next(r for r in build()["ladder"] if r["role"] == "next")
    assert nxt["r"] == pytest.approx(4.26, abs=0.01) and nxt["usd"] == pytest.approx(189.5)


def test_the_rows_measure_from_the_price_not_the_entry():
    lv = build()["levels"]
    assert lv["room"]["text"] == "0.7R to HOD 6.97, from the price" and lv["room"]["trial"] is None
    assert lv["next"]["round"] == 7.0 and "$7.00 is 36c above" in lv["next"]["text"]
    assert lv["stop"]["text"] == "5.45 is 5c under $5.50"
    assert lv["recent"]["text"].startswith("Broke $6.00: the 08:58 candle closed 6.46")


def test_r_is_unknown_without_a_risk_and_a_stop_over_the_average():
    out = build(risk=None, stop=5.45)                             # a stop over the average locks in, R unknown
    assert out["risk"] is None and out["r"] is None and out["target"] is None
    assert "R is not known" in out["levels"]["room"]["detail"]


def test_the_stocks_own_rounds_are_used_over_25_dollars():
    rnd = rounds.of(223.0)
    assert rnd.minor == 5.0 and rnd.near == pytest.approx(0.5)
    bars = [bar(f"09:{m:02d}", 218.0, 219.0, 217.5, 218.5) for m in range(30, 46)]
    bars.append(bar("09:46", 218.5, 221.0, 218.4, 220.6))
    out = held.raise_for(held.crosses(bars, rnd, t("09:30"), 220.8)[0], rnd, 214.0, 220.8)
    assert out["to"] == 219.5 and out["round"] == 220.0


def test_the_read_adds_held_with_the_checks_that_hold_for_a_position():
    ctx = {"price": 6.64, "bars": BARS, "level_map": MAP, "levels": {"vwap": 4.92}, "macd_hist": 0.062, "ema9": 5.5,
           "median_range": 0.3, "spread": 0.03, "flow": None, "bid_pulls": 0, "halted": None}
    out = held_read({"nova_exit": None}, ctx, {"qty": 100, "avg": 5.075, "stop": 5.45, "risk": 0.445, "since": SINCE},
                    NOW)
    assert {c["id"] for c in out["checks"]} <= set(HELD_CHECK_IDS)
    assert {c["id"] for c in out["checks"]} >= {"macd", "ema9", "vwap", "spread"}
    nova = held_read({"nova_exit": {"stop": 5.95}}, ctx, {"qty": 100, "avg": 5.075, "since": SINCE}, NOW)
    assert nova["stop"]["source"] == "nova" and nova["stop"]["price"] == 5.95


def test_the_route_adds_held_and_serves_the_flush_reading(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from sensors import rings
    from stock_read import history, routes
    from tests.test_stock_read import facts

    monkeypatch.setattr(routes.gather, "gather", lambda sym, now: facts(symbol=sym))
    monkeypatch.setattr(history, "summary", lambda sym, now: None)
    routes._cache.clear()
    app = FastAPI()
    app.include_router(routes.router)
    client = TestClient(app)
    plain = client.get("/api/stock-read/APUS").json()
    assert plain["held"] is None
    body = client.get("/api/stock-read/APUS?held_qty=100&held_avg=5.075&held_stop=4.63&held_since=1").json()
    assert body["held"]["qty"] == 100 and body["held"]["stop"]["source"] == "yours"
    assert [r["role"] for r in body["held"]["ladder"]][-2:] == ["cost", "stop"]   # highest price first
    monkeypatch.setattr(rings, "recent_prints", lambda sym, limit=None: [])
    monkeypatch.setattr(rings, "recent_books", lambda sym, limit=None: [])
    flush = client.get("/api/stock-read/APUS/flush").json()
    assert flush["schema_version"] == 1 and flush["window_sec"] == 30.0 and flush["label"] in ("blind", "quiet")
