"""The day's support and resistance (ADR 036 amendment 2026-09-30): the level map a read carries and
what the plan says about it -- on bars shaped like LGHL's first pullback at 07:16 on 2026-09-30."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from stock_read import level_map, level_notes

ET = ZoneInfo("America/New_York")
DAY = "2026-09-30"


def ts(hh: int, mm: int) -> float:
    return datetime(2026, 9, 30, hh, mm, tzinfo=ET).timestamp()


def bar(hh, mm, o, h, lo, c, v=10_000):
    return {"t": ts(hh, mm), "o": o, "h": h, "l": lo, "c": c, "v": v}


def day(d, h, lo, c=None, o=None):
    return {"d": d, "o": o if o is not None else lo, "h": h, "l": lo, "c": c if c is not None else h, "v": 1_000}


def flat(start_hh, start_mm, n, price, spread=0.02):
    """``n`` quiet one-minute candles around ``price``."""
    out = []
    for i in range(n):
        m = start_hh * 60 + start_mm + i
        out.append(bar(m // 60, m % 60, price, price + spread / 2, price - spread / 2, price))
    return out


# -- finding the levels ---------------------------------------------------------------------------------
def test_a_swing_high_is_over_the_candles_before_it_and_a_run_of_equal_highs_counts_once():
    bars = [bar(7, 0, 5.0, 5.00, 4.9, 5.0), bar(7, 1, 5.0, 5.05, 4.9, 5.0), bar(7, 2, 5.0, 5.20, 4.9, 5.1),
            bar(7, 3, 5.1, 5.20, 5.0, 5.1), bar(7, 4, 5.1, 5.10, 5.0, 5.0), bar(7, 5, 5.0, 5.05, 4.9, 5.0)]
    assert level_map.swings(bars, "h", 1) == [(5.20, ts(7, 2))]
    assert level_map.swings(bars[:4], "h", 1) == []            # the last two candles cannot be one yet


def test_tops_within_a_third_of_a_percent_are_one_level_tested_twice_or_more():
    groups = level_map.clusters([(7.48, 1.0), (7.47, 2.0), (7.10, 3.0), (7.49, 4.0)], 0.003, 0.01)
    assert [len(g) for g in groups] == [1, 3]


def test_today_names_the_high_and_low_of_day_a_double_top_the_rounds_and_yesterday():
    bars = (flat(7, 0, 3, 8.20) + [bar(7, 3, 8.2, 8.77, 8.2, 8.6)] + flat(7, 4, 3, 8.40)
            + [bar(7, 7, 8.4, 8.76, 8.4, 8.5)] + flat(7, 8, 3, 8.40))
    members = level_map.intraday_members(bars, price=8.62, vwap=8.35, yday={"d": "2026-09-29", "h": 5.95, "l": 4.5},
                                         prior_close=4.51)
    kinds = {m["kind"]: m for m in members}
    assert kinds["hod"]["price"] == 8.77 and kinds["lod"]["price"] == 8.19
    assert kinds["top"]["touches"] == 2 and kinds["top"]["price"] == 8.77 and kinds["top"]["label"] == "double top"
    assert "pmh" not in kinds and "open" not in kinds          # before 09:30 the high of day is the premarket's
    assert {m["price"] for m in members if m["kind"] in ("whole", "half")} >= {8.0, 8.5, 9.0, 9.5}
    assert kinds["yday_high"]["price"] == 5.95 and kinds["prior_close"]["price"] == 4.51 and kinds["vwap"]["price"] == 8.35


def test_levels_close_together_are_one_zone_that_lists_every_reason_strongest_first():
    members = [level_map.member("half", 7.50), level_map.member("vwap", 7.44),
               level_map.member("top", 7.48, touches=5), level_map.member("top", 7.47, touches=3),
               level_map.member("whole", 7.00), level_map.member("bottom", 7.01, touches=7)]
    zs = level_map.zones(members, price=6.99, home="intraday", merge_pct=0.006)
    ceiling, floor = zs
    assert (ceiling["lo"], ceiling["hi"], ceiling["side"], ceiling["price"]) == (7.44, 7.5, "above", 7.44)
    assert ceiling["label"] == "$7.50 · top ×8 · VWAP" and ceiling["tag"] == "$7.50"
    assert len(ceiling["members"]) == 4                         # the hover keeps each cluster
    assert floor["side"] == "at" and floor["label"] == "$7.00 · bottom ×7"
    lone = level_map.zones([level_map.member("top", 7.30, touches=2)], price=6.99, home="intraday", merge_pct=0.006)[0]
    assert lone["label"] == "7.30 · double top" and lone["tag"] == "double top 7.30"


def test_a_gap_no_later_session_traded_is_a_daily_level_and_a_filled_one_is_not():
    daily = [day("2026-09-01", 5.0, 4.8), day("2026-09-02", 7.0, 6.0),     # gap up 5.00 -> 6.00
             day("2026-09-03", 6.5, 5.6),                                    # fills 5.60 -> 6.00
             day("2026-09-04", 6.4, 6.1)]
    assert level_map.unfilled_gaps(daily) == [{"lo": 5.0, "hi": 5.6, "since": "2026-09-02"}]
    assert level_map.unfilled_gaps(daily + [day("2026-09-08", 6.2, 4.9)]) == []


def test_the_daily_map_is_highs_and_lows_touched_twice_the_older_highs_above_the_200_day_and_yesterday():
    daily = ([day(f"2026-08-{d:02d}", 9.0 + d * 0.001, 8.0) for d in range(3, 6)]      # three highs near 9.00
             + [day("2026-08-10", 12.0, 10.5), day("2026-08-11", 10.4, 9.6)]
             + [day(f"2026-09-{d:02d}", 7.7, 7.0) for d in (15, 16)]                  # highs 7.70 twice
             + [day("2026-09-29", 5.95, 4.50, c=4.66)])
    members = level_map.daily_members(daily, price=7.02, today=DAY, sma200=169.4)
    highs = [m for m in members if m["kind"] == "daily_highs"]
    assert {(round(m["price"], 3), m["touches"]) for m in highs} == {(9.005, 3), (7.7, 2)}
    assert [m["price"] for m in members if m["kind"] == "daily_high"] == [10.4, 12.0]   # look left and up
    assert any(m["kind"] == "sma200" and m["price"] == 169.4 for m in members)
    assert {m["kind"] for m in members} >= {"yday_high", "yday_low"}


def test_the_map_leaves_today_out_of_the_daily_levels_and_says_when_the_history_is_missing():
    bars = flat(7, 0, 10, 7.0)
    lm = level_map.build(bars, None, price=7.0, prior_close=4.51, vwap=7.0, now=ts(7, 11),
                         daily_error="the daily history could not be read")
    assert lm["daily"] == [] and lm["daily_error"] == "the daily history could not be read"
    assert lm["study"]["round_turn"] == [24, 16] and lm["schema_version"] == 1
    today = [day("2026-09-29", 5.95, 4.5), day(DAY, 99.0, 1.0)]
    lm = level_map.build(bars, today, price=7.0, prior_close=4.51, vwap=7.0, now=ts(7, 11))
    assert all(99.0 not in (z["lo"], z["hi"]) for z in lm["daily"]) and lm["daily_error"] is None



# -- each chart reads its own candles (operator report 2026-09-30) -----------------------------------------
def _spiky(spikes: dict[tuple[int, int], float], start=(17, 20), n=70, base=20.0):
    """``n`` quiet one-minute candles from ``start`` with a high of ``spikes[(hh, mm)]`` at those minutes."""
    out = []
    for i in range(n):
        m = start[0] * 60 + start[1] + i
        hh, mm = m // 60, m % 60
        hi = spikes.get((hh, mm), base + 0.05)
        out.append(bar(hh, mm, base, hi, base - 0.05, base))
    return out


def test_five_minute_candles_are_made_on_the_clock_and_only_once_their_five_minutes_are_over():
    bars = flat(9, 28, 9, 7.0)                       # 09:28 .. 09:36
    five = level_map.five_minute_bars(bars, now=ts(9, 37))
    assert [c["t"] for c in five] == [ts(9, 25), ts(9, 30)]          # 09:35 is still forming
    assert five[1]["v"] == 50_000 and five[1]["o"] == 7.0
    assert len(level_map.five_minute_bars(bars, now=ts(9, 40))) == 3


def test_two_tops_inside_one_five_minute_candle_are_a_double_top_on_the_one_minute_map_only():
    # XRPN 2026-09-30: tops at 17:41 and 17:44 -- one 5-minute candle (17:40) on the 5-minute chart.
    bars = _spiky({(17, 41): 23.52, (17, 44): 23.50})
    lm = level_map.build(bars, None, price=20.0, prior_close=12.9, vwap=19.0, now=ts(18, 31))
    one = next(z for z in lm["intraday"] if any(m["kind"] == "hod" for m in z["members"]))
    assert any(m["kind"] == "top" and m["label"] == "double top" for m in one["members"])
    five = next(z for z in lm["five_minute"] if any(m["kind"] == "hod" for m in z["members"]))
    assert not any(m["kind"] == "top" for m in five["members"]) and "top" not in five["label"]
    assert five["id"].startswith("five_minute:")


def test_two_five_minute_tops_are_a_double_top_on_the_five_minute_map():
    bars = _spiky({(17, 41): 21.00, (18, 6): 20.99})
    lm = level_map.build(bars, None, price=20.0, prior_close=12.9, vwap=19.0, now=ts(18, 31))
    tops = [m for z in lm["five_minute"] for m in z["members"] if m["kind"] == "top"]
    assert [(t["label"], t["touches"]) for t in tops] == [("double top", 2)]
    assert [round(t, 0) for t in tops[0]["times"]] == [ts(17, 40), ts(18, 5)]


def test_the_five_minute_map_leaves_vwap_and_yesterday_to_their_own_charts_and_names_a_round_only_where_tested():
    bars = _spiky({(17, 41): 21.00, (18, 6): 20.99})
    past = [day("2026-09-29", 20.20, 19.10, c=19.40)]
    lm = level_map.build(bars, past, price=20.0, prior_close=19.4, vwap=19.95, now=ts(18, 31))
    kinds = {m["kind"] for z in lm["five_minute"] for m in z["members"]}
    assert not kinds & {"vwap", "yday_high", "yday_low", "prior_close"}
    rounds = [z for z in lm["five_minute"] if any(m["kind"] in ("whole", "half") for m in z["members"])]
    # $21.00 is a double top and $20.00 the low of day; $20.50, $19.50 ... alone are not 5-minute levels.
    assert sorted(z["lo"] for z in rounds) == [19.95, 21.0]
    assert all(any(m["kind"] not in ("whole", "half") for m in z["members"]) for z in rounds)
    assert any(m["kind"] == "vwap" for z in lm["intraday"] for m in z["members"])   # the plan's map keeps it

# -- what the plan says ---------------------------------------------------------------------------------
PLAN = {"entry": 8.62, "stop": 8.45, "target": 8.96, "risk": 0.17}


def _zone(price, *members, side="above"):
    zs = level_map.zones(list(members), price=8.62, home="intraday", merge_pct=0.006)
    return next(z for z in zs if z["lo"] <= price <= z["hi"])


def test_room_is_the_first_level_of_today_over_the_entry_in_r_and_reads_amber_under_two_r():
    intra = [_zone(8.77, level_map.member("hod", 8.77)), _zone(9.0, level_map.member("whole", 9.0)),
             _zone(8.5, level_map.member("half", 8.5))]
    daily = level_map.zones([level_map.member("daily_highs", 8.84, touches=5)], price=8.62, home="daily",
                            merge_pct=0.015)
    room = level_notes.room(PLAN, intra, daily)
    assert (room["state"], room["text"], room["r"], room["trial"]) == ("warn", "0.9R to HOD 8.77", 0.88, "T7")
    assert room["detail"].startswith("Then $9.00 at 2.2R. Under 2R it is a warning while trial T7 runs")
    assert "8.84 · daily highs ×5" in room["detail"] and "never count here" in room["detail"]


def test_room_is_fine_with_nothing_over_the_entry_and_unknown_without_a_stop():
    assert level_notes.room(PLAN, [], [])["state"] == "ok"
    assert level_notes.room({**PLAN, "risk": None}, [], [])["state"] == "unknown"


def test_a_target_just_under_a_round_sells_before_it_and_one_just_over_needs_the_break():
    under = level_notes.target_note(8.96)
    assert (under["state"], under["text"], under["round"]) == ("ok", "8.96 is 4c under $9.00", 9.0)
    over = level_notes.target_note(9.02)
    assert (over["state"], over["text"]) == ("warn", "9.02 is 2c over $9.00")
    assert level_notes.target_note(9.00)["text"] == "9.00 is on $9.00"
    assert level_notes.target_note(9.20) is None


def test_a_stop_under_a_round_survives_its_test_and_one_just_over_it_does_not():
    under = level_notes.stop_note(8.45, 8.62)
    assert (under["state"], under["text"]) == ("ok", "8.45 is 5c under $8.50")
    assert "the drop usually keeps going" in under["detail"]
    over = level_notes.stop_note(8.52, 8.70)
    assert (over["state"], over["text"]) == ("warn", "8.52 is 2c over $8.50")
    assert level_notes.stop_note(8.30, 8.62) is None
    assert level_notes.stop_note(8.45, 8.49) is None           # the round is over the entry: not the stop's


def test_the_next_round_is_resistance_until_it_breaks_and_an_entry_just_under_one_is_amber():
    nxt, _ = level_notes.round_notes([], price=8.66, entry=8.62, now=ts(7, 16))
    assert (nxt["state"], nxt["text"]) == ("info", "$9.00 is 38c above: resistance until it prints through, a trigger after")
    near, _ = level_notes.round_notes([], price=4.95, entry=4.97, now=ts(7, 16))
    assert near["state"] == "warn" and near["text"].startswith("Entry 3c under $5.00")


def test_a_fresh_break_of_a_round_is_said_while_the_price_holds_over_it_and_a_loss_under_it():
    quiet = flat(7, 0, 15, 8.40)
    bars = quiet + [bar(7, 15, 8.45, 8.56, 8.44, 8.55)]
    _, recent = level_notes.round_notes(bars, price=8.55, entry=None, now=ts(7, 17))
    assert (recent["state"], recent["text"]) == ("ok", "Broke $8.50 at 07:15")
    _, gone = level_notes.round_notes(bars, price=8.46, entry=None, now=ts(7, 17))
    assert gone is None                                          # back under it: nothing broke
    _, stale = level_notes.round_notes(bars, price=8.55, entry=None, now=ts(7, 40))
    assert stale is None                                         # ten minutes on, it is not news
    down = flat(7, 0, 15, 8.60) + [bar(7, 15, 8.55, 8.56, 8.44, 8.45)]
    _, lost = level_notes.round_notes(down, price=8.45, entry=None, now=ts(7, 17))
    assert lost["state"] == "bad" and lost["text"].startswith("Lost $8.50 at 07:15")


def test_the_levels_between_the_stop_and_the_target_are_the_one_minute_charts():
    intra = level_map.zones([level_map.member("hod", 8.77), level_map.member("half", 8.5),
                             level_map.member("whole", 9.0), level_map.member("whole", 8.0)],
                            price=8.62, home="intraday", merge_pct=0.006)
    between = level_notes.between(PLAN, intra)
    assert [(b["tag"], b["round"], b["hod"]) for b in between] == [("$8.50", True, False), ("HOD 8.77", False, True)]


def test_the_plan_carries_its_level_notes_when_the_read_has_a_map():
    intra = level_map.zones([level_map.member("hod", 8.77)], price=8.62, home="intraday", merge_pct=0.006)
    out = level_notes.notes(PLAN, {"intraday": intra, "daily": []}, [], price=8.66, now=ts(7, 16))
    assert set(out) == {"room", "target", "stop", "next", "recent", "between"}
    assert level_notes.notes(PLAN, None, [], price=8.66, now=ts(7, 16)) is None
