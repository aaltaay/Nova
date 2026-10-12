"""The obvious trend lines on the 1- and 5-minute charts (ADR 036 amendment 2026-10-12): which swing points a line
joins, the band a touch may miss it by, a break, and what a long's and a short's plan say about them."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from stock_read import level_map, level_notes, line_notes, trend_lines

ET = ZoneInfo("America/New_York")
T0 = datetime(2026, 10, 12, 7, 0, tzinfo=ET).timestamp()


def line_at(i: int, base: float = 5.0, slope: float = 0.02) -> float:
    return base + slope * i


def rising(n: int, touches: list[int], *, slope: float = 0.02, base: float = 5.0) -> list[dict]:
    """``n`` one-minute candles whose lows dip to the line ``base + slope x i`` at ``touches`` and stand off it
    3c a candle in between: a swing low at each touch, every close over the line."""
    out = []
    for i in range(n):
        d = min(abs(i - k) for k in touches)
        low = line_at(i, base, slope) + 0.03 * d
        out.append({"t": T0 + 60 * i, "o": low + 0.05, "h": low + 0.10, "l": low, "c": low + 0.06, "v": 1_000})
    return out


def mirrored(bars: list[dict], k: float = 20.0) -> list[dict]:
    """The same candles upside down: a rising support becomes a falling resistance."""
    return [{"t": b["t"], "o": k - b["o"], "h": k - b["l"], "l": k - b["h"], "c": k - b["c"], "v": b["v"]} for b in bars]


def found(bars, price=None):
    return trend_lines.find(bars, home="one_minute", price=bars[-1]["c"] if price is None else price)


# -- the lines -------------------------------------------------------------------------------------------
def test_an_ascending_support_joins_the_swing_lows_it_touches_three_times_or_more():
    bars = rising(40, [5, 15, 25, 35])
    [ln] = found(bars)
    assert (ln["kind"], ln["dir"], ln["state"], ln["home"]) == ("support", "up", "holding", "one_minute")
    assert [t["t"] for t in ln["touches"]] == [T0 + 60 * i for i in (5, 15, 25, 35)]
    assert ln["p1"] == 5.1 and ln["p2"] == 5.7 and ln["slope"] == 0.02
    assert ln["now_p"] == round(line_at(39), 4) and ln["side"] == "below"
    assert ln["label"] == "ascending support · 4 touches" and ln["tag"] == "↗ support"
    assert ln["note"] == "4 touches: 07:05, 07:15, 07:25, 07:35"


def test_two_touches_make_any_line_so_they_are_not_one():
    assert found(rising(30, [5, 20])) == []


def test_a_swing_low_inside_the_band_touches_and_one_off_it_does_not():
    bars = rising(40, [5, 15, 25, 35])
    bars[25] = {**bars[25], "l": bars[25]["l"] + 0.02}        # 2c over the line: inside 0.5% of $5.50
    assert len(found(bars)[0]["touches"]) == 4
    bars[25] = {**bars[25], "l": bars[25]["l"] + 0.04}        # 6c over it: off it (and still a swing low)
    for k in (23, 24, 26, 27):
        bars[k] = {**bars[k], "l": bars[k]["l"] + 0.10}
    assert len(found(bars)[0]["touches"]) == 3


def test_a_wick_through_the_line_still_touches_when_the_body_holds():
    bars = rising(40, [5, 15, 25, 35])
    bars[25] = {**bars[25], "l": bars[25]["l"] - 0.08}
    assert len(found(bars)[0]["touches"]) == 4


def test_a_candle_closing_through_between_the_touches_leaves_no_line():
    bars = rising(40, [5, 15, 25, 35])
    bars[20] = {**bars[20], "c": line_at(20) - 0.05, "l": line_at(20) - 0.06}
    assert found(bars) == []


def test_a_line_too_flat_is_a_level_and_too_short_is_noise():
    assert found(rising(40, [5, 15, 25, 35], slope=0.001)) == []
    assert found(rising(14, [3, 6, 9])) == []                  # three touches over six candles


def test_a_close_under_the_line_after_its_last_touch_breaks_it_and_it_is_said_ten_candles():
    bars = rising(40, [5, 15, 25, 35])
    bars[38] = {**bars[38], "o": line_at(38) + 0.01, "c": line_at(38) - 0.05, "l": line_at(38) - 0.06}
    bars[39] = {**bars[39], "o": line_at(39) - 0.05, "h": line_at(39) + 0.01, "l": line_at(39) - 0.08,
                "c": line_at(39) - 0.04}
    [ln] = found(bars)
    assert ln["state"] == "broken" and ln["broke"]["t"] == T0 + 60 * 38
    assert ln["retest_t"] == T0 + 60 * 39                     # it reached the line from under and closed under
    assert "a candle closed under it at 07:38" in ln["note"]
    later = bars + [{"t": T0 + 60 * (40 + k), "o": 5.7 - 0.05 * k, "h": 5.72 - 0.05 * k, "l": 5.6 - 0.05 * k,
                     "c": 5.62 - 0.05 * k, "v": 1_000} for k in range(9)]     # on down: no new swing low
    assert [x["state"] for x in found(later)] == []


def test_a_descending_resistance_is_the_mirror():
    [ln] = found(mirrored(rising(40, [5, 15, 25, 35])))
    assert (ln["kind"], ln["dir"], ln["state"]) == ("resistance", "down", "holding")
    assert len(ln["touches"]) == 4 and ln["side"] == "above"
    assert ln["tag"] == "↘ resistance"


def test_a_holding_line_far_from_the_price_is_not_in_play():
    bars = rising(40, [5, 15, 25, 35])
    assert found(bars, price=line_at(39) * 1.3) == []


def test_each_chart_reads_its_own_candles():
    now = T0 + 60 * 200
    bars = rising(200, list(range(5, 200, 10)))
    lines = trend_lines.build(bars, level_map.five_minute_bars(bars, now), price=bars[-1]["c"])
    assert set(lines) == {"one_minute", "five_minute"}
    assert all(ln["home"] == "one_minute" for ln in lines["one_minute"])
    assert all(ln["home"] == "five_minute" for ln in lines["five_minute"])


# -- what the plan says ----------------------------------------------------------------------------------
def line(kind, now_p, *, home="one_minute", state="holding", slope=None, broke=None, retest=None):
    up = kind == "support"
    return {"id": f"{home}:{kind}:1", "home": home, "kind": kind, "dir": "up" if up else "down", "state": state,
            "now_p": now_p, "band": round(max(0.005 * now_p, 0.01), 4), "slope": slope if slope is not None else (0.02 if up else -0.02),
            "touches": [{}, {}, {}], "broke": broke, "retest_t": retest,
            "note": "3 touches: 09:40, 09:50, 10:00", "label": f"{'ascending' if up else 'descending'} {kind} · 3 touches"}


LONG = {"side": "long", "entry": 5.00, "stop": 4.80, "target": 5.40, "risk": 0.20}
SHORT = {"side": "short", "entry": 5.00, "stop": 5.20, "target": 4.60, "risk": 0.20}


def lines_of(*ls):
    return {"one_minute": [x for x in ls if x["home"] == "one_minute"],
            "five_minute": [x for x in ls if x["home"] == "five_minute"]}


def test_a_descending_line_between_a_longs_entry_and_target_is_in_the_way():
    [n] = line_notes.notes(LONG, lines_of(line("resistance", 5.24, home="five_minute")), price=4.98)
    assert (n["role"], n["state"], n["r"]) == ("way", "warn", 1.2)
    assert n["text"] == "↘ resistance (5-min) at 5.24 (1.2R) before target 1"
    assert "falls 2c a 5-minute candle" in n["detail"] and "It blocks nothing." in n["detail"]


def test_a_line_past_the_target_is_not_in_the_way_and_one_under_the_entry_is_its_break():
    assert line_notes.notes(LONG, lines_of(line("resistance", 5.50)), price=4.98) == []
    [n] = line_notes.notes(LONG, lines_of(line("resistance", 4.99)), price=4.95)
    assert (n["role"], n["state"]) == ("way", "info")
    assert n["text"] == "The entry is over the ↘ resistance (1-min) at 4.99: it trades the break"


def test_a_longs_stop_under_the_ascending_support_survives_a_test_and_one_over_it_does_not():
    [ok] = line_notes.notes(LONG, lines_of(line("support", 4.90)), price=5.0)
    assert (ok["role"], ok["state"], ok["text"]) == ("stop", "ok", "Stop 4.80 is under the ↗ support (1-min) at 4.90")
    [on] = line_notes.notes(LONG, lines_of(line("support", 4.81)), price=5.0)
    assert on["state"] == "warn" and on["text"].startswith("Stop 4.80 is on the ↗ support (1-min) at 4.81")
    [over] = line_notes.notes(LONG, lines_of(line("support", 4.70)), price=5.0)
    assert over["state"] == "warn" and over["text"].startswith("Stop 4.80 is over the ↗ support (1-min) at 4.70")
    assert line_notes.notes(LONG, lines_of(line("support", 4.50)), price=5.0) == []   # more than 1R past the stop


def test_a_broken_support_is_against_a_long_and_a_broken_resistance_with_it():
    broke = {"t": datetime(2026, 10, 12, 9, 52, tzinfo=ET).timestamp(), "p": 5.02, "close": 4.98}
    retest = datetime(2026, 10, 12, 9, 55, tzinfo=ET).timestamp()
    [bad] = line_notes.notes(LONG, lines_of(line("support", 5.05, state="broken", broke=broke, retest=retest)), price=4.97)
    assert (bad["role"], bad["state"], bad["text"]) == ("broke", "bad", "↗ support (1-min) broke at 09:52")
    assert "bearish sign" in bad["detail"] and "the support became resistance" in bad["detail"]
    [good] = line_notes.notes(LONG, lines_of(line("resistance", 4.95, state="broken", broke=broke)), price=4.97)
    assert (good["state"], good["text"]) == ("info", "Broke the ↘ resistance (1-min) at 09:52")
    # Back on the line's side, the break is not said.
    assert line_notes.notes(LONG, lines_of(line("support", 4.95, state="broken", broke=broke)), price=4.97) == []


def test_a_shorts_notes_are_the_mirror():
    found_ = line_notes.notes(SHORT, lines_of(line("support", 4.76), line("resistance", 5.30)), price=5.02)
    way, stop = found_
    assert (way["role"], way["state"], way["text"]) == ("way", "warn", "↗ support (1-min) at 4.76 (1.2R) before target 1")
    assert (stop["role"], stop["state"], stop["text"]) == (
        "stop", "warn", "Stop 5.20 is under the ↘ resistance (1-min) at 5.30: a test of the line can take it")
    broke = {"t": datetime(2026, 10, 12, 9, 52, tzinfo=ET).timestamp(), "p": 5.0, "close": 5.05}
    [bad] = line_notes.notes(SHORT, lines_of(line("resistance", 4.98, state="broken", broke=broke)), price=5.03)
    assert (bad["state"], bad["text"]) == ("bad", "↘ resistance (1-min) broke at 09:52")
    assert "bullish sign" in bad["detail"]


def test_the_plan_carries_its_line_notes_beside_the_level_notes():
    lm = {"price": 4.98, "intraday": [], "daily": [], "lines": lines_of(line("resistance", 5.24))}
    out = level_notes.notes(LONG, lm, [], price=4.98, now=T0)
    assert [n["role"] for n in out["lines"]] == ["way"]
    assert level_notes.notes(LONG, {"price": 4.98, "intraday": [], "daily": []}, [], price=4.98, now=T0)["lines"] == []
