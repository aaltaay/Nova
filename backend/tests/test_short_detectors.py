"""The five short setups' detectors (ADR 049): each arms, triggers downward and fails by its pre-registered rules."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest

from constants_setups import (
    SETUP_STATE_ARMED,
    SETUP_STATE_FAILED,
    SETUP_STATE_LEG,
    SETUP_STATE_NEAR,
    SETUP_STATE_TRIGGERED,
    SETUP_STATE_WATCHING,
)
from setup_scanner.backside import BacksideDetector
from setup_scanner.bars import Bar
from setup_scanner.bear_flag import BearFlagDetector
from setup_scanner.detector_short import ssr_today
from setup_scanner.failed_breakout import FailedBreakoutDetector
from setup_scanner.lost_vwap import LostVwapDetector
from setup_scanner.series import Series
from setup_scanner.ssr_bounce import SsrBounceDetector, next_round
from setup_scanner_fixtures import et_ts

DAY = "2026-10-07"


def flat(hh: int, mm: int, n: int, price: float, v: float = 5_000) -> list[Bar]:
    """``n`` quiet candles a cent around ``price`` from ``hh:mm``."""
    t0 = et_ts(hh, mm, DAY)
    out = []
    for i in range(n):
        w = 0.01 if i % 2 else 0.0
        o, c = price + w, price + 0.01 - w
        out.append(Bar(t0 + 60 * i, o, max(o, c) + 0.01, min(o, c) - 0.01, c, v))
    return out


def add(bars: list[Bar], o: float, h: float, lo: float, c: float, v: float = 20_000) -> list[Bar]:
    bars.append(Bar(bars[-1].t + 60, o, h, lo, c, v))
    return bars


def run_up(bars: list[Bar], closes: list[float], v: float = 30_000) -> list[Bar]:
    for c in closes:
        o = bars[-1].c
        add(bars, o, c + 0.01, o - 0.01, c, v)
    return bars


def fade(bars: list[Bar], closes: list[float], v: float = 40_000) -> list[Bar]:
    for c in closes:
        o = bars[-1].c
        add(bars, o, o + 0.01, c - 0.01, c, v)
    return bars


def feed(det, bars: list[Bar]) -> list[tuple[str, dict]]:
    """Every bar close in turn, as the engine does; the events of the last one."""
    events: list[tuple[str, dict]] = []
    for i in range(1, len(bars) + 1):
        events = det.on_bars(bars[:i])
    return events


# -- backside lower high ------------------------------------------------------------------
def _backside_day() -> list[Bar]:
    bars = flat(9, 0, 40, 5.00)                                     # 09:00-09:39
    run_up(bars, [5.10, 5.20, 5.30, 5.40, 5.50, 5.60, 5.70, 5.80, 5.90, 6.00])  # 09:40-09:49, HOD 6.01
    for _ in range(25):                                              # 09:50-10:14 near the high
        add(bars, 5.95, 5.97, 5.93, 5.95, 10_000)
    fade(bars, [5.85, 5.75, 5.65, 5.55, 5.47, 5.41])                 # 10:15-10:20, low 5.40
    add(bars, 5.42, 5.50, 5.42, 5.49, 15_000)                        # bounce 1 (10:21)
    add(bars, 5.49, 5.55, 5.47, 5.48, 12_000)                        # bounce 2 (10:22): low 5.47
    return bars


def test_backside_arms_under_the_last_bounce_low_with_its_buy_stop_over_the_bounce():
    det = BacksideDetector("FADE")
    feed(det, _backside_day())
    assert det.state == SETUP_STATE_ARMED, det.reason
    a = det.armed
    assert a["trigger"] == 5.47 and a["entry"] == 5.46
    assert a["stop"] == 5.56                       # one cent over the bounce's 5.55 high
    assert a["risk"] == pytest.approx(0.10)
    assert a["target1"] == pytest.approx(5.46 - 2 * 0.10)
    assert a["leg_high"] == 6.01 and a["leg_low"] == 5.40
    assert a["kind"] == "backside_lower_high"


def test_backside_triggers_on_a_price_at_its_entry_and_reads_near_over_the_trigger():
    det = BacksideDetector("FADE")
    feed(det, _backside_day())
    t = et_ts(10, 23, DAY)
    assert det.on_price(5.52, t) == []                         # 5c over the trigger: armed, not near
    near = det.on_price(5.49, t + 1)
    assert near and near[0][0] == "near" and det.state == SETUP_STATE_NEAR
    assert det.on_price(5.47, t + 2) == []                     # at the trigger: not yet the entry
    fired = det.on_price(5.46, t + 3, bar_open=5.50)
    assert fired[0][0] == "triggered" and det.state == SETUP_STATE_TRIGGERED
    assert det.triggered["entry"] == 5.46 and det.nth == 1


def test_a_print_under_the_trigger_but_over_the_entry_does_not_trigger():
    # PR #789 review: a sub-penny print between the 5.47 trigger and the 5.46 entry never traded the sell entry.
    det = BacksideDetector("FADE")
    feed(det, _backside_day())
    t = et_ts(10, 23, DAY)
    assert det.armed["trigger"] == 5.47 and det.armed["entry"] == 5.46
    near = det.on_price(5.465, t)
    assert near and near[0][0] == "near" and det.state == SETUP_STATE_NEAR
    assert det.on_price(5.4651, t + 1) == []
    fired = det.on_price(5.46, t + 2)
    assert fired[0][0] == "triggered" and det.triggered["entry"] == 5.46


def test_ssr_at_the_trigger_counts_the_trade_that_triggered_it():
    # PR #789 review: the triggering trade can be the day's first at 90% of the prior close.
    det = BacksideDetector("FADE")
    bars = _backside_day()
    feed(det, bars)
    prior = min(b.lo for b in bars) / 0.95            # every bar's low over 90% of the prior close
    det.context = {"prior_close": prior, "ssr_yesterday": False}
    assert det.ssr() == "off"
    det.on_price(prior * 0.899, et_ts(10, 23, DAY))  # the live price reaches the SSR trigger
    assert det.ssr() == "on"


def test_backside_gap_under_enters_at_the_open_and_skips_when_the_risk_goes_over_the_cap():
    det = BacksideDetector("FADE")
    feed(det, _backside_day())
    t = et_ts(10, 23, DAY)
    fired = det.on_price(5.40, t, bar_open=5.40)
    assert fired[0][0] == "triggered" and det.triggered["entry"] == 5.40   # 5.56 - 5.40 + 0.01 = 0.17 <= 0.20

    det = BacksideDetector("FADE")
    feed(det, _backside_day())
    gone = det.on_price(5.30, t, bar_open=5.30)                           # 0.26 + 0.01 over the cap
    assert gone[0][0] == "disarmed" and "risk over 0.20" in det.reason


def test_backside_bounce_over_the_ema_or_past_three_candles_never_arms():
    bars = _backside_day()[:-2]
    add(bars, 5.42, 5.50, 5.42, 5.49, 15_000)
    add(bars, 5.49, 5.70, 5.47, 5.69, 12_000)                  # closes over the 9 EMA and takes back half
    det = BacksideDetector("FADE")
    feed(det, bars)
    assert det.armed is None and det.state == SETUP_STATE_FAILED

    bars = _backside_day()
    for _ in range(3):
        add(bars, 5.49, 5.52, 5.48, 5.50, 10_000)              # the bounce drags on with no new low
    det = BacksideDetector("FADE")
    feed(det, bars)
    assert det.armed is None
    assert det.state == SETUP_STATE_FAILED and "ran past 3 candles" in det.reason


def test_backside_needs_the_window_and_a_negative_macd():
    det = BacksideDetector("FADE")
    bars = _backside_day()
    shifted = [Bar(b.t - 90 * 60, b.o, b.h, b.lo, b.c, b.v) for b in bars]    # the bounce at 08:52: before 09:35
    feed(det, shifted)
    assert det.armed is None and "outside the entry window" in det.reason
    assert det.forming and det.forming["entry"] == 5.46


def test_backside_new_low_is_the_next_fade():
    bars = _backside_day()
    add(bars, 5.47, 5.48, 5.30, 5.31, 30_000)                  # a new low under the fade's: the next fade
    det = BacksideDetector("FADE")
    feed(det, bars)
    assert det.state == SETUP_STATE_LEG and det.leg["low"] == 5.30


# -- bear flag ------------------------------------------------------------------------------
def _bear_flag_day() -> list[Bar]:
    bars = flat(9, 0, 30, 5.80, v=10_000)                       # 09:00-09:29
    run_up(bars, [5.85, 5.90, 5.95, 6.00], v=20_000)            # 09:30-09:33
    for _ in range(10):                                          # 09:34-09:43 at the high
        add(bars, 5.98, 6.00, 5.96, 5.98, 15_000)
    add(bars, 5.98, 6.00, 5.88, 5.89, 50_000)                    # pole 1 (red)
    add(bars, 5.89, 5.90, 5.79, 5.80, 60_000)                    # pole 2
    add(bars, 5.80, 5.81, 5.69, 5.70, 70_000)                    # pole 3: bottom 5.69, wick 0.01 of 0.12
    add(bars, 5.70, 5.78, 5.70, 5.77, 20_000)                    # flag 1 (green)
    add(bars, 5.77, 5.80, 5.72, 5.79, 18_000)                    # flag 2 (green), low 5.72
    return bars


def test_bear_flag_arms_under_the_last_flag_low():
    det = BearFlagDetector("FLAG")
    feed(det, _bear_flag_day())
    assert det.state == SETUP_STATE_ARMED, det.reason
    a = det.armed
    assert a["trigger"] == 5.72 and a["entry"] == 5.71
    assert a["stop"] == 5.81 and a["risk"] == pytest.approx(0.10)
    assert a["leg_high"] == 6.00 and a["leg_low"] == 5.69
    assert a["detail"]["pole_bars"] == 3 and a["detail"]["flag_bars"] == 2


def test_bear_flag_rejects_a_lower_low_in_the_flag_and_a_green_volume_high():
    bars = _bear_flag_day()[:-1]
    add(bars, 5.74, 5.79, 5.66, 5.78, 18_000)                    # flag 2 (green) makes a lower low
    det = BearFlagDetector("FLAG")
    feed(det, bars)
    assert det.armed is None and "lower low" in det.reason

    bars = _bear_flag_day()
    bars[31] = Bar(bars[31].t, bars[31].o, bars[31].h, bars[31].lo, bars[31].c, 500_000)   # a green run candle
    det = BearFlagDetector("FLAG")
    feed(det, bars)
    assert det.armed is None and "green" in det.reason


def test_bear_flag_with_one_flag_candle_is_still_forming():
    bars = _bear_flag_day()[:-1]
    det = BearFlagDetector("FLAG")
    feed(det, bars)
    assert det.state == SETUP_STATE_LEG and det.forming and det.forming["waiting"] == "1 more green or doji candle"


# -- failed breakout -----------------------------------------------------------------------------
def _failed_breakout_day() -> list[Bar]:
    bars = flat(9, 0, 30, 5.50, v=10_000)                       # 09:00-09:29
    run_up(bars, [5.70, 5.85, 5.99], v=20_000)                  # 09:30-09:32: HOD 6.00
    for _ in range(6):                                           # 09:33-09:38 under it
        add(bars, 5.90, 5.93, 5.88, 5.91, 10_000)
    add(bars, 5.91, 5.98, 5.90, 5.95, 12_000)                    # 09:39 a touch (5.98 >= 5.97)
    add(bars, 5.95, 6.05, 5.95, 6.02, 40_000)                    # 09:40 the poke: closes over
    add(bars, 6.02, 6.03, 5.93, 5.95, 35_000)                    # 09:41 closes back under: the failure
    return bars


def test_failed_breakout_arms_under_the_failure_candle():
    det = FailedBreakoutDetector("POKE")
    feed(det, _failed_breakout_day())
    assert det.state == SETUP_STATE_ARMED, det.reason
    a = det.armed
    assert a["trigger"] == 5.93 and a["entry"] == 5.92
    assert a["stop"] == 6.06 and a["risk"] == pytest.approx(0.14)
    assert a["detail"]["level"] == 6.00 and len(a["detail"]["touches"]) >= 2


def test_failed_breakout_is_a_leg_until_it_fails_and_held_when_two_more_close_over():
    bars = _failed_breakout_day()[:-1]
    det = FailedBreakoutDetector("POKE")
    feed(det, bars)
    assert det.state == SETUP_STATE_LEG and "poked over the 6.00 flat top" in det.reason
    add(bars, 6.02, 6.06, 6.01, 6.04, 20_000)
    add(bars, 6.04, 6.08, 6.03, 6.07, 20_000)
    det = FailedBreakoutDetector("POKE")
    feed(det, bars)
    assert det.armed is None and det.state == SETUP_STATE_FAILED and "held" in det.reason


def test_failed_breakout_expires_three_candles_after_the_failure():
    bars = _failed_breakout_day()
    for _ in range(4):
        add(bars, 5.95, 5.97, 5.94, 5.96, 10_000)                # no breakdown under 5.93
    det = FailedBreakoutDetector("POKE")
    feed(det, bars)
    assert det.armed is None and "no breakdown within 3 candles" in det.reason


def test_failed_breakout_one_touch_is_no_flat_top():
    bars = flat(9, 0, 30, 5.50, v=10_000)
    run_up(bars, [5.70, 5.85, 5.99], v=20_000)
    for _ in range(6):
        add(bars, 5.80, 5.85, 5.78, 5.82, 10_000)                 # never back near 6.00
    add(bars, 5.82, 6.05, 5.82, 6.02, 40_000)
    add(bars, 6.02, 6.03, 5.93, 5.95, 35_000)
    det = FailedBreakoutDetector("POKE")
    feed(det, bars)
    assert det.armed is None


# -- lost VWAP --------------------------------------------------------------------------------
def _lost_vwap_day() -> tuple[list[Bar], float]:
    bars = flat(9, 0, 30, 5.00, v=20_000)                       # 09:00-09:29: VWAP near 5.00
    run_up(bars, [5.20, 5.30], v=30_000)                        # 09:30-09:31 over VWAP
    for _ in range(4):                                           # 09:32-09:35 holding over
        add(bars, 5.25, 5.28, 5.22, 5.24, 20_000)
    s = Series()
    s.update(bars)
    vw = s.vw[-1]
    add(bars, 5.20, 5.21, vw - 0.06, vw - 0.05, 40_000)          # 09:36 the loss: a close under VWAP
    s.update(bars)
    vw = s.vw[-1]
    add(bars, vw - 0.05, vw - 0.03, vw - 0.08, vw - 0.06, 20_000)  # 09:37 under, short of the band
    s.update(bars)
    vw = s.vw[-1]
    add(bars, vw - 0.06, vw - 0.005, vw - 0.09, vw - 0.03, 20_000)  # 09:38 the retest: high in the band, under
    return bars, vw


def test_lost_vwap_arms_under_the_retest():
    bars, _ = _lost_vwap_day()
    det = LostVwapDetector("VWAP")
    feed(det, bars)
    assert det.state == SETUP_STATE_ARMED, det.reason
    a = det.armed
    s = Series()
    s.update(bars)
    vw = s.vw[-1]                                                 # VWAP through the retest candle
    assert a["trigger"] == round(bars[-1].lo, 4) and a["entry"] == round(bars[-1].lo - 0.01, 4)
    assert a["stop"] == round(max(vw, bars[-1].h) + 0.01, 4)
    assert a["detail"]["vwap"] == round(vw, 4)
    assert a["kind"] == "lost_vwap"


def test_lost_vwap_close_back_over_vwap_ends_the_day():
    bars, vw = _lost_vwap_day()
    add(bars, vw, vw + 0.10, vw - 0.01, vw + 0.08, 50_000)      # back over VWAP
    det = LostVwapDetector("VWAP")
    feed(det, bars)
    assert det.armed is None and det.state == SETUP_STATE_FAILED and "back over VWAP" in det.reason
    add(bars, vw, vw + 0.01, vw - 0.20, vw - 0.15, 50_000)      # lost again: the day's try is spent
    feed(det, bars)
    assert det.armed is None and det.done


def test_lost_vwap_ends_at_its_window_close_armed_or_not():
    # PR #789 review: an armed retest re-armed on every bar past 12:00, so it could go near and propose late.
    bars, vw = _lost_vwap_day()
    det = LostVwapDetector("VWAP")
    feed(det, bars)
    assert det.state == SETUP_STATE_ARMED
    trig = det.armed["trigger"]
    while bars[-1].t + 60 < et_ts(11, 59, DAY):            # quiet under VWAP, never under the trigger, to 11:58
        add(bars, trig + 0.03, trig + 0.04, trig + 0.02, trig + 0.03, 10_000)
    assert det.on_bars(bars) == [] and det.state == SETUP_STATE_ARMED
    add(bars, trig + 0.03, trig + 0.04, trig + 0.02, trig + 0.03, 10_000)   # the 11:59 candle ends at 12:00
    ended = det.on_bars(bars)
    assert ended and ended[0][0] == "disarmed" and det.armed is None
    assert det.state == SETUP_STATE_WATCHING and "window closed at 12:00" in det.reason
    assert det.on_price(trig - 0.05, bars[-1].t + 70) == []                  # nothing triggers after it


def test_lost_vwap_opening_under_vwap_is_out():
    bars = flat(9, 0, 30, 5.00, v=20_000)
    add(bars, 4.95, 4.96, 4.80, 4.82, 50_000)                    # 09:30 opens and closes under VWAP
    det = LostVwapDetector("VWAP")
    feed(det, bars)
    assert det.state == SETUP_STATE_WATCHING and "opening candle" in det.reason


# -- SSR bounce ----------------------------------------------------------------------------------
def _ssr_day() -> list[Bar]:
    bars = flat(9, 0, 35, 5.60, v=60_000)                       # 09:00-09:34 heavy at 5.60: VWAP high
    for c in (5.50, 5.40, 5.30, 5.20, 5.10, 5.01):               # 09:35-09:40 the drop: SSR (5.40) and a new low
        o = bars[-1].c
        add(bars, o, o + 0.01, c - 0.01, c, 20_000)
    add(bars, 5.01, 5.16, 5.01, 5.15, 15_000)                    # green
    add(bars, 5.15, 5.31, 5.14, 5.30, 15_000)                    # green: 5.30 is within 2% under 5.40
    return bars


def test_ssr_bounce_rests_under_the_ssr_trigger_level():
    det = SsrBounceDetector("SSRB", context={"prior_close": 6.00, "ssr_yesterday": False})
    feed(det, _ssr_day())
    assert det.state == SETUP_STATE_ARMED, det.reason
    a = det.armed
    assert a["detail"]["level"] == pytest.approx(5.40) and a["detail"]["level_kind"] == "ssr_trigger"
    assert a["entry"] == 5.39 and a["trigger"] == 5.39
    assert a["stop"] == pytest.approx(round(5.39 + 0.02 * 5.39, 4))
    assert a["target1"] == pytest.approx(round(5.39 - 2 * a["risk"], 4))


def test_ssr_bounce_fills_when_a_buyer_lifts_its_entry_and_cancels_on_its_rules():
    det = SsrBounceDetector("SSRB", context={"prior_close": 6.00, "ssr_yesterday": False})
    bars = _ssr_day()
    feed(det, bars)
    t = bars[-1].t + 60
    assert det.on_price(5.36, t) and det.state == SETUP_STATE_NEAR
    fired = det.on_price(5.40, t + 5)
    assert fired[0][0] == "triggered" and det.triggered["entry"] == 5.39

    det = SsrBounceDetector("SSRB", context={"prior_close": 6.00, "ssr_yesterday": False})
    feed(det, bars)
    gone = det.on_price(5.30, t + 10 * 60)
    assert gone[0][0] == "failed" and "10 minutes" in det.reason

    det = SsrBounceDetector("SSRB", context={"prior_close": 6.00, "ssr_yesterday": False})
    feed(det, bars)
    bars2 = add(list(bars), 5.30, 5.45, 5.29, 5.42, 30_000)      # a close over the level
    det.on_bars(bars2)
    assert det.state == SETUP_STATE_FAILED and "closed over the level" in det.reason


def test_ssr_bounce_needs_ssr_known_on():
    det = SsrBounceDetector("SSRB", context={"prior_close": 4.00, "ssr_yesterday": False})   # never 10% under
    feed(det, _ssr_day())
    assert det.armed is None and "SSR is off" in det.reason
    det = SsrBounceDetector("SSRB", context=None)
    feed(det, _ssr_day())
    assert det.armed is None and "not known" in det.reason
    det = SsrBounceDetector("SSRB", context={"prior_close": None, "ssr_yesterday": True})   # carried from yesterday
    feed(det, _ssr_day())
    # SSR on from yesterday: it reads the bounce. With no prior close there is no 5.40 trigger level; the next
    # level over 5.30 is the 5.50 round, 3.6% away -- it waits.
    assert det.armed is None and det.state == SETUP_STATE_LEG and "under the 5.50 level" in det.reason


def test_ssr_today_and_the_next_round():
    assert ssr_today([5.5, 5.39], {"prior_close": 6.0}) == "on"
    assert ssr_today([5.5], {"prior_close": 6.0, "ssr_yesterday": False}) == "off"
    assert ssr_today([5.5], {"prior_close": 6.0}) == "unknown"
    assert ssr_today([5.5], {"ssr_yesterday": True}) == "on"
    assert next_round(4.70, 0.5) == 5.0 and next_round(5.0, 0.5) == 5.5 and next_round(4.99, 0.5) == 5.0
