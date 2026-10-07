"""The read while you hold a stock short (ADR 048 step 3: "the This trade card, mirrored").

Shaped on the approved mockup's RDYN: 416 short at 5.77 at 09:42 with a buy stop at 5.89 (0.12 risk), the
cover target 5.53 (2R) traded at 09:45, the 09:46 candle closed 5.47 under $5.50, and the price stands at
5.45 with the premarket bottom at 5.35 and $5.00 under it. A short's ladder runs downward and its stop
only ever moves down ("Lower stop to 5.55, 5c over $5.50").
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from stock_read import held_short, plan as plan_mod
from stock_read.read import held_read

ET = ZoneInfo("America/New_York")


def t(hm: str) -> float:
    h, m = map(int, hm.split(":"))
    return datetime(2026, 10, 7, h, m, tzinfo=ET).timestamp()


def bar(hm: str, o: float, h: float, lo: float, c: float, v: float = 20_000) -> dict:
    return {"t": t(hm), "o": o, "h": h, "l": lo, "c": c, "v": v}


# 09:25-09:41 all close over $5.50 (a fresh break needs 15), then the fade after the 09:42 short.
BARS = [bar(f"09:{m:02d}", 5.90, 6.20, 5.80, 5.95 + (m % 3) * 0.05) for m in range(25, 42)] + [
    bar("09:42", 5.79, 5.80, 5.70, 5.72), bar("09:43", 5.72, 5.74, 5.63, 5.66), bar("09:44", 5.66, 5.68, 5.58, 5.60),
    bar("09:45", 5.60, 5.61, 5.52, 5.55), bar("09:46", 5.55, 5.56, 5.44, 5.47), bar("09:47", 5.47, 5.49, 5.43, 5.45),
]
SINCE = t("09:42") + 7
NOW = t("09:48") + 5


def zone(lo: float, hi: float, label: str, tag: str | None = None) -> dict:
    return {"lo": lo, "hi": hi, "price": hi, "label": label, "tag": tag or label, "members": [], "strength": 3}


MAP = {"price": 5.45, "intraday": [
    zone(6.48, 6.48, "6.48 · lower high"), zone(5.62, 5.62, "5.62 · the 09:36 low", "5.62"),
    zone(5.35, 5.35, "5.35 · the premarket bottom ×3", "5.35"), zone(5.00, 5.00, "$5.00"),
]}


def build(**over) -> dict:
    args = dict(bars=BARS, price=5.45, level_map=MAP, avg=5.77, qty=416, now=NOW, since=SINCE, stop=5.89)
    args.update(over)
    return held_short.build(**args)


def test_a_close_under_a_round_breaks_it_and_the_stop_may_come_down_to_5c_over_it():
    out = build()
    assert out["side"] == "short" and out["raise"] is None
    assert [b["round"] for b in out["broke"]] == [5.5]
    assert out["broke"][0]["at"] == t("09:47") and out["broke"][0]["close"] == 5.47     # the 09:46 candle
    assert out["lower"]["to"] == 5.55 and "Lower the stop to 5.55, 5c over $5.50" in out["lower"]["text"]
    assert build(stop=5.55)["lower"] is None                    # never the same, never up
    assert build(price=5.56, stop=5.89)["lower"] is None        # 5.55 would be under the price


def test_the_cover_target_is_2r_under_the_average_and_says_when_it_traded():
    out = build()
    assert out["risk"] == pytest.approx(0.12) and out["target"]["price"] == pytest.approx(5.53)
    assert out["target"]["traded_at"] == t("09:45")             # the 09:45 low 5.52
    assert out["levels"]["target"]["text"].endswith("you are past it")
    assert out["open_usd"] == pytest.approx((5.77 - 5.45) * 416) and out["r"] == pytest.approx(2.67, abs=0.01)


def test_the_ladder_runs_down_from_the_stop_through_the_price_to_the_next_levels():
    rows = [(r["role"], r["price"]) for r in build()["ladder"]]
    assert rows == [("stop", 5.89), ("cost", 5.77), ("broke", 5.5), ("now", 5.45), ("next", 5.35), ("then", 5.0)]
    stop_row = build()["ladder"][0]
    assert stop_row["usd"] == pytest.approx(-0.12 * 416) and stop_row["r"] == pytest.approx(-1.0)


def test_the_rows_measure_room_down_and_name_the_round_just_lost():
    levels = build()["levels"]
    assert levels["room"]["text"] == "0.8R to 5.35, from the price"
    assert levels["recent"]["text"] == "Lost $5.50: the 09:46 candle closed 5.47"
    assert levels["next"]["text"] == "$5.00 next: support until it prints through, a trigger after"


def test_a_buy_stop_is_proposed_over_the_price_and_printed_when_a_price_reaches_it():
    out = build(stop=None)
    assert out["stop"]["source"] == "proposed" and out["stop"]["price"] == 5.61      # 09:45-09:47's high
    assert build(price=5.90)["stop"]["printed"] is True
    assert build()["stop"]["printed"] is False


def test_the_read_measures_a_short_downward_and_names_the_day_cover():
    f = {"nova_exit": None}
    ctx = {"price": 5.45, "bars": BARS, "level_map": MAP, "macd_hist": -0.05, "ema9": 5.60,
           "levels": {"vwap": 5.92}, "spread": 0.01}
    out = held_read(f, ctx, {"qty": 416, "avg": 5.77, "stop": 5.89, "since": SINCE, "side": "short"}, NOW)
    checks = {c["id"]: c for c in out["checks"]}
    assert out["side"] == "short"
    assert checks["macd"]["state"] == "ok" and checks["ema9"]["text"] == "under the 9 EMA 5.60"
    assert checks["ema9"]["state"] == "ok"
    assert checks["day_cover"]["text"] == "day only: Nova covers what is left at 15:55"


# -- the plan box: your own short ---------------------------------------------------------------

CTX = {"price": 5.79, "levels": {"vwap": 5.93}, "macd_hist": -0.026, "ema9": 5.86, "spread": 0.01,
       "bars": BARS[:17] + [bar("09:42", 5.79, 5.88, 5.76, 5.79)],
       "level_map": {"price": 5.79, "intraday": [zone(5.62, 5.62, "5.62 · the 09:36 low", "5.62")]},
       "bids": [{"price": 5.79, "size": 2100}, {"price": 5.60, "size": 30_000}], "asks": []}


def test_your_short_plan_covers_at_entry_less_2r_and_its_checks_read_its_way():
    plan = plan_mod.build([], CTX, now=t("09:42") + 30, entry=5.77, stop=5.89, side="short")
    assert (plan["side"], plan["stop"], plan["target"], plan["risk"], plan["rr"]) == ("short", 5.89, 5.53, 0.12, 2.0)
    assert plan["target_rule"] == "entry - 2 x risk" and plan["stop_rule"] == "your buy stop"
    checks = {c["id"]: c for c in plan["checks"]}
    assert checks["macd"]["state"] == "ok" and checks["vwap"]["text"] == "under VWAP 5.93"
    assert checks["in_way_wall"]["text"] == "a buyer of 30,000 at 5.60 before the target"
    assert [m["kind"] for m in plan["marks"]] == ["wall"]
    assert plan["levels"]["room"]["text"] == "1.2R to 5.62" and plan["levels"]["room"]["trial"] is None
    assert plan["levels"]["target"]["text"] == "5.53 covers 3c over $5.50"


def test_your_short_plan_takes_the_last_candles_high_when_your_stop_is_not_over_the_entry():
    plan = plan_mod.build([], CTX, now=t("09:42") + 30, entry=5.77, stop=5.70, side="short")
    assert plan["stop"] == 6.20 and plan["stop_rule"] == "the highest high of the last 3 closed 1-min candles"
    long_plan = plan_mod.build([], CTX, now=t("09:42") + 30, entry=5.77, stop=5.70)
    assert long_plan["side"] == "long" and long_plan["target"] == pytest.approx(5.91)


def test_a_short_plan_walks_the_bids_for_its_size():
    ctx = {**CTX, "risk_usd": 50, "volume": 9_000_000, "bids": [{"price": 5.79, "size": 100}, {"price": 5.70, "size": 900}]}
    plan = plan_mod.build([], ctx, now=t("09:42") + 30, entry=5.77, stop=5.89, side="short")
    walk = plan["liquidity"]["walk"]
    assert walk["best_bid"] == 5.79 and walk["qty"] == 416 and walk["under_bid"] > 0
