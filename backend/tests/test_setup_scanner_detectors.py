"""The bull flag, the flat-top breakout and red to green on synthetic one-minute bars (ADR 031).

Each detector is fed the day bar by bar (``on_bars``) and live prices in between
(``on_price``), exactly as a lane feeds it."""
from __future__ import annotations

from setup_scanner.bars import Bar
from setup_scanner.bull_flag import BullFlagDetector, BullFlagParams
from setup_scanner.flat_top import FlatTopDetector, FlatTopParams
from setup_scanner.red_to_green import RedToGreenDetector, RedToGreenParams
from tests.setup_scanner_fixtures import add, base_morning, et_ts, leg_up


def feed(det, bars: list[Bar]) -> list[tuple[str, dict]]:
    """Every completed bar in turn; the events of the last one."""
    events: list[tuple[str, dict]] = []
    for n in range(1, len(bars) + 1):
        events = det.on_bars(bars[:n])
    return events


def names(events) -> list[str]:
    return [name for name, _ in events]


# -- bull flag -----------------------------------------------------------------------
def pole(v: float = 80_000) -> list[Bar]:
    """A quiet morning, then three green candles on rising volume: +9% to 4.35."""
    bars = base_morning()
    for close, vol in ((4.10, v), (4.22, v * 1.1), (4.34, v * 1.2)):
        o = bars[-1].c
        add(bars, o, close + 0.01, o - 0.01, close, vol)
    return bars


def flag(bars: list[Bar], candles=((4.34, 4.34, 4.28, 4.29, 30_000), (4.29, 4.30, 4.26, 4.27, 25_000))) -> list[Bar]:
    for o, h, lo, c, v in candles:
        add(bars, o, h, lo, c, v)
    return bars


def test_a_pole_then_a_two_candle_flag_arms_over_the_last_flag_high():
    d = BullFlagDetector("TEST")
    bars = pole()
    feed(d, bars)
    assert d.state == "leg" and "3 green candles" in d.reason
    add(bars, 4.34, 4.34, 4.28, 4.29, 30_000)
    d.on_bars(bars)
    assert d.state == "leg" and "a flag needs 2" in d.reason      # one red candle is a micro pullback
    add(bars, 4.29, 4.30, 4.26, 4.27, 25_000)
    events = d.on_bars(bars)
    assert names(events) == ["armed"] and d.state == "armed"
    a = d.armed
    assert (a["trigger"], a["entry"], a["stop"]) == (4.30, 4.31, 4.26)
    assert a["risk"] == 0.05 and a["target1"] == 4.41               # the pole high 4.35 or 2R: 2R is higher
    assert a["kind"] == "bull_flag" and a["pullback_bars"] == 2 and a["detail"]["pole_bars"] == 3
    assert a["leg_high"] == 4.35


def test_near_then_the_first_candle_to_make_a_new_high_triggers():
    d = BullFlagDetector("TEST")
    bars = flag(pole())
    feed(d, bars)
    t = bars[-1].t + 70
    assert names(d.on_price(4.29, t)) == ["near"] and d.state == "near"
    events = d.on_price(4.31, t + 5, bar_open=4.28)
    assert names(events) == ["triggered"] and d.triggered["entry"] == 4.31 and d.nth == 1


def test_the_trigger_moves_down_with_a_third_flag_candle_and_a_fourth_fails():
    d = BullFlagDetector("TEST")
    bars = flag(pole())
    feed(d, bars)
    add(bars, 4.27, 4.28, 4.24, 4.25, 20_000)
    assert names(d.on_bars(bars)) == ["rearmed"] and d.armed["trigger"] == 4.28
    add(bars, 4.25, 4.26, 4.22, 4.23, 18_000)
    events = d.on_bars(bars)
    assert d.state == "failed" and "ran past 3 candles" in d.reason and names(events) == ["failed"]


def test_a_flag_that_gives_back_more_than_half_the_pole_fails():
    d = BullFlagDetector("TEST")
    bars = flag(pole(), ((4.34, 4.34, 4.20, 4.22, 30_000), (4.22, 4.23, 4.10, 4.12, 25_000)))
    feed(d, bars)
    assert d.state == "failed" and "gave back" in d.reason


def test_a_flag_on_heavier_volume_than_the_pole_fails():
    d = BullFlagDetector("TEST")
    bars = flag(pole(v=20_000), ((4.34, 4.34, 4.28, 4.29, 90_000), (4.29, 4.30, 4.26, 4.27, 90_000)))
    feed(d, bars)
    assert d.state == "failed" and "not lighter" in d.reason


def test_the_days_biggest_volume_candle_being_red_is_skipped():
    d = BullFlagDetector("TEST")
    bars = flag(pole(), ((4.34, 4.34, 4.28, 4.29, 30_000), (4.29, 4.30, 4.26, 4.27, 500_000)))
    feed(d, bars)
    assert d.state == "failed" and ("highest-volume candle is red" in d.reason or "not lighter" in d.reason)
    d2 = BullFlagDetector("TEST", BullFlagParams(flag_volume_lighter=False))
    feed(d2, bars)
    assert d2.state == "failed" and "highest-volume candle is red" in d2.reason
    d3 = BullFlagDetector("TEST", BullFlagParams(flag_volume_lighter=False, reject_red_volume_high=False))
    feed(d3, bars)
    assert d3.state == "armed"


def test_a_flag_candle_with_a_higher_high_is_not_a_flag():
    d = BullFlagDetector("TEST")
    bars = flag(pole(), ((4.34, 4.34, 4.28, 4.29, 30_000), (4.29, 4.345, 4.26, 4.27, 25_000)))
    feed(d, bars)
    assert d.state == "failed" and "higher high" in d.reason


def test_a_big_topping_tail_on_the_pole_top_is_skipped():
    bars = base_morning()
    for close in (4.10, 4.22):
        o = bars[-1].c
        add(bars, o, close + 0.01, o - 0.01, close, 80_000)
    add(bars, 4.22, 4.60, 4.21, 4.34, 90_000)             # a wick of 0.26 on a 0.39 range: 67%
    flag(bars)
    d = BullFlagDetector("TEST")
    feed(d, bars)
    assert d.state == "failed" and "topping tail" in d.reason
    loose = BullFlagDetector("TEST", BullFlagParams(max_pole_wick=None, max_retrace=0.9))
    feed(loose, bars)
    assert loose.state != "failed" or "topping tail" not in loose.reason


def test_macd_under_zero_blocks_the_flag():
    bars = flag(pole())
    d = BullFlagDetector("TEST")
    feed(d, bars)
    assert d.state == "armed" and d.series.hist[-1] > 0
    d.series.hist[-1] = -0.01                              # the same bars with the front side gone
    events = d.on_bars(bars)
    assert d.state == "pullback" and "MACD" in d.reason and d.armed is None and names(events) == ["disarmed"]
    free = BullFlagDetector("TEST", BullFlagParams(macd_positive=False))
    feed(free, bars)
    free.series.hist[-1] = -0.01
    free.on_bars(bars)
    assert free.state == "armed"


def test_a_second_flag_after_a_trigger_needs_a_new_pole_and_is_the_second_kind():
    d = BullFlagDetector("TEST")
    bars = flag(pole())
    feed(d, bars)
    d.on_price(4.31, bars[-1].t + 65, bar_open=4.28)
    assert d.state == "triggered"
    add(bars, 4.28, 4.33, 4.27, 4.32, 60_000)
    assert d.on_bars(bars) == [] and d.state == "triggered"          # the trade is on
    for close, vol in ((4.40, 90_000), (4.50, 95_000), (4.60, 100_000)):
        o = bars[-1].c
        add(bars, o, close + 0.01, o - 0.01, close, vol)
    feed(d, bars)
    flag(bars, ((4.60, 4.60, 4.55, 4.56, 30_000), (4.56, 4.57, 4.53, 4.54, 25_000)))
    d.on_bars(bars)
    assert d.state == "armed" and d.armed["kind"] == "second_bull_flag"


# -- flat-top breakout -----------------------------------------------------------------
def base_under_high(hold_low: float = 4.17) -> list[Bar]:
    """A quiet morning, a 5% impulse to a 4.21 high of day, then two tight candles under it."""
    bars = leg_up(base_morning(), [4.05, 4.10, 4.15, 4.20])
    add(bars, 4.20, 4.21, hold_low, 4.19, 30_000)
    add(bars, 4.19, 4.20, hold_low, 4.18, 25_000)
    return bars


def test_a_tight_base_under_the_high_of_day_arms_at_the_high():
    d = FlatTopDetector("TEST")
    bars = base_under_high()
    events = feed(d, bars)
    assert d.state == "armed" and names(events) == ["armed"]
    a = d.armed
    assert a["trigger"] == 4.21 and a["kind"] == "flat_top_breakout" and a["pullback_bars"] == 2
    assert a["detail"]["entry_mode"] == "hold" and a["leg_pct"] > 0.03


def test_hold_entry_breaks_then_the_first_green_candle_holding_the_level_triggers_at_its_close():
    d = FlatTopDetector("TEST")
    bars = base_under_high()
    feed(d, bars)
    brk = bars[-1].t + 60 + 20                             # inside the next minute
    assert names(d.on_price(4.22, brk)) == ["near"] and d.state == "near" and d.broke is not None
    assert d.on_price(4.30, brk + 5) == []                 # no trigger on a price: the hold is a close
    add(bars, 4.19, 4.24, 4.18, 4.22, 60_000)               # the break's own candle
    assert d.on_bars(bars) == [] and d.state == "near"
    add(bars, 4.22, 4.27, 4.21, 4.26, 50_000)               # low 4.21 holds the 4.21 high, closes green
    events = d.on_bars(bars)
    assert names(events) == ["triggered"]
    t = d.triggered
    assert (t["entry"], t["stop"], t["risk"]) == (4.27, 4.21, 0.06)
    assert t["target1"] == 4.39 and t["triggered_at"] == bars[-1].t + 60
    assert t["score_bar_t"] == bars[-1].t and t["half_on_entry_bar"] is False


def test_hold_entry_fails_on_a_close_back_under_the_high():
    d = FlatTopDetector("TEST")
    bars = base_under_high()
    feed(d, bars)
    d.on_price(4.22, bars[-1].t + 80)
    add(bars, 4.19, 4.23, 4.18, 4.22, 60_000)
    d.on_bars(bars)
    add(bars, 4.22, 4.22, 4.15, 4.16, 40_000)
    events = d.on_bars(bars)
    assert d.state == "failed" and names(events) == ["failed"] and "closed back under" in d.reason


def test_hold_entry_disarms_after_three_candles_without_a_hold():
    d = FlatTopDetector("TEST")
    bars = base_under_high()
    feed(d, bars)
    d.on_price(4.22, bars[-1].t + 80)
    add(bars, 4.19, 4.23, 4.18, 4.22, 60_000)
    d.on_bars(bars)
    for _ in range(3):                                      # hold the level but close red each time
        add(bars, 4.23, 4.24, 4.21, 4.22, 30_000)
        events = d.on_bars(bars)
    assert names(events) == ["disarmed"] and "no candle held" in d.reason


def test_break_entry_triggers_on_the_price_with_the_base_low_as_the_stop():
    d = FlatTopDetector("TEST", FlatTopParams(entry_mode="break"))
    bars = base_under_high()
    feed(d, bars)
    a = d.armed
    assert (a["entry"], a["stop"]) == (4.22, 4.17) and a["target1"] == 4.32
    events = d.on_price(4.22, bars[-1].t + 70, bar_open=4.19)
    assert names(events) == ["triggered"] and d.triggered["entry"] == 4.22


def test_a_base_close_far_under_the_high_fails_and_a_small_impulse_is_no_flat_top():
    bars = leg_up(base_morning(), [4.05, 4.10, 4.15, 4.20])
    add(bars, 4.20, 4.21, 4.05, 4.08, 30_000)               # closes 3% under the high
    add(bars, 4.08, 4.12, 4.06, 4.10, 25_000)
    d = FlatTopDetector("TEST")
    feed(d, bars)
    assert d.state in ("failed", "watching") and d.armed is None
    flat = leg_up(base_morning(), [4.01, 4.02])            # a 1% move is no impulse
    add(flat, 4.02, 4.03, 4.01, 4.02, 5_000)
    add(flat, 4.02, 4.03, 4.01, 4.02, 5_000)
    d2 = FlatTopDetector("TEST")
    feed(d2, flat)
    assert d2.state != "armed"


# -- red to green ---------------------------------------------------------------------
def morning_to_open(price: float = 4.00, slope: float = 0.002) -> list[Bar]:
    """08:20-09:29, drifting up a little so the MACD is above zero at the open."""
    bars = []
    t0 = et_ts(8, 20)
    px = price
    for i in range(70):
        o = px
        px = round(px + slope, 4)
        bars.append(Bar(t0 + 60 * i, o, px + 0.01, o - 0.01, px, 20_000))
    return bars


def test_before_the_open_it_waits_and_a_red_close_under_the_open_arms_at_the_open():
    d = RedToGreenDetector("TEST")
    bars = morning_to_open()
    feed(d, bars)
    assert d.state == "watching" and "waits for the 09:30 open" in d.reason
    open_px = bars[-1].c + 0.02
    add(bars, open_px, open_px + 0.01, open_px - 0.06, open_px - 0.04, 60_000)   # 09:30: opens, closes red
    d.on_bars(bars)
    d.series.hist[-1] = 0.004                              # the front side (the rule is read below)
    d.state = "watching"
    events = d.on_bars(bars)
    assert names(events) == ["armed"] and d.state == "armed"
    a = d.armed
    assert a["trigger"] == round(open_px, 4) and a["entry"] == round(open_px + 0.01, 4)
    assert a["stop"] == round(open_px - 0.06, 4) and a["kind"] == "red_to_green" and a["risk"] == 0.07
    assert a["detail"]["red_bars"] == 1 and a["target1"] >= a["entry"] + 2 * a["risk"] - 1e-9


def test_a_red_close_with_the_macd_under_zero_is_not_a_try():
    d = RedToGreenDetector("TEST")
    bars = morning_to_open()
    open_px = bars[-1].c + 0.02
    add(bars, open_px, open_px + 0.01, open_px - 0.06, open_px - 0.04, 60_000)
    feed(d, bars)
    assert d.series.hist[-1] < 0                           # a red opening candle after a slow drift
    assert d.state == "pullback" and "not a try" in d.reason and d.armed is None
    assert d.on_price(open_px + 0.02, bars[-1].t + 70) == [] and not d.spent


def test_the_reclaim_triggers_once_and_the_day_is_done():
    d = RedToGreenDetector("TEST", RedToGreenParams(macd_positive=False))
    bars = morning_to_open()
    open_px = bars[-1].c + 0.02
    add(bars, open_px, open_px + 0.01, open_px - 0.06, open_px - 0.04, 60_000)
    feed(d, bars)
    assert d.state == "armed"
    t = bars[-1].t + 70
    assert names(d.on_price(open_px - 0.01, t)) == ["near"]
    events = d.on_price(open_px + 0.02, t + 5, bar_open=open_px - 0.03)
    assert names(events) == ["triggered"] and d.nth == 1
    add(bars, open_px - 0.03, open_px + 0.05, open_px - 0.08, open_px - 0.07, 60_000)
    assert d.on_bars(bars) == [] and d.state == "triggered"     # one a day


def test_a_reclaim_with_the_risk_out_of_the_band_spends_the_days_try():
    d = RedToGreenDetector("TEST", RedToGreenParams(macd_positive=False))
    bars = morning_to_open()
    open_px = bars[-1].c + 0.02
    add(bars, open_px, open_px + 0.01, open_px - 0.40, open_px - 0.30, 60_000)   # the stop is 41c away
    feed(d, bars)
    assert d.state == "pullback" and "spends the day's one try" in d.reason and d.armed is None
    assert d.on_price(open_px + 0.02, bars[-1].t + 70) == []
    assert d.spent and d.state == "watching" and "spent" in d.reason
    add(bars, open_px - 0.30, open_px - 0.25, open_px - 0.35, open_px - 0.32, 60_000)
    assert d.on_bars(bars) == [] and d.armed is None


def test_nothing_arms_at_or_after_the_reclaim_cutoff():
    d = RedToGreenDetector("TEST", RedToGreenParams(macd_positive=False))
    bars = morning_to_open()
    open_px = bars[-1].c + 0.02
    add(bars, open_px, open_px + 0.01, open_px - 0.03, open_px + 0.01, 60_000)   # 09:30 closes green
    while bars[-1].t < et_ts(10, 29):
        add(bars, bars[-1].c, bars[-1].c + 0.01, bars[-1].c - 0.01, bars[-1].c + 0.001, 10_000)
    add(bars, open_px, open_px + 0.01, open_px - 0.05, open_px - 0.04, 10_000)   # 10:30: red, too late
    feed(d, bars)
    assert d.state == "watching" and "reclaim window closed" in d.reason and d.spent
