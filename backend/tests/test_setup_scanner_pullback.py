"""The first-pullback state machine (ADR 022): leg, armed, near, triggered, failed."""
from __future__ import annotations

from setup_scanner.bars import Bar, MinuteBars, bar_from
from setup_scanner.pullback import PullbackDetector, PullbackParams
from tests.setup_scanner_fixtures import add, base_morning, et_ts, leg_up


def _feed(d: PullbackDetector, bars: list[Bar]) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    for k in range(1, len(bars) + 1):
        events += d.on_bars(bars[:k])
    return events


def _leg() -> list[Bar]:
    bars = base_morning()
    return leg_up(bars, [4.08, 4.18, 4.28, 4.38])


def test_warming_up_until_enough_bars():
    d = PullbackDetector("TEST")
    _feed(d, base_morning(n=10))
    assert d.state == "watching"
    assert "warming up" in d.reason


def test_leg_then_armed_on_one_red_candle():
    d = PullbackDetector("TEST")
    events = _feed(d, _leg())
    assert d.state == "leg" and events[-1][0] == "leg"
    bars = add(_leg(), 4.38, 4.37, 4.30, 4.32, 30_000)
    d = PullbackDetector("TEST")
    events = _feed(d, bars)
    assert d.state == "armed" and events[-1][0] == "armed"
    s = d.armed
    assert s["trigger"] == 4.37 and s["entry"] == 4.38 and s["stop"] == 4.30
    assert s["risk"] == 0.08
    assert s["target1"] == 4.54            # max(leg high 4.39, 4.38 + 2 x 0.08)
    assert s["kind"] == "first_pullback"


def test_near_then_triggered_by_live_price():
    bars = add(_leg(), 4.38, 4.37, 4.30, 4.32, 30_000)
    d = PullbackDetector("TEST")
    _feed(d, bars)
    t = bars[-1].t + 70
    assert d.on_price(4.31, t, bar_open=4.32) == []
    assert d.state == "armed"
    ev = d.on_price(4.35, t + 1, bar_open=4.32)
    assert ev[0][0] == "near" and d.state == "near"
    ev = d.on_price(4.38, t + 2, bar_open=4.32)
    assert ev[0][0] == "triggered" and d.state == "triggered"
    assert d.triggered["entry"] == 4.38 and d.nth == 1


def test_gap_over_the_trigger_fills_at_the_open():
    bars = add(_leg(), 4.38, 4.37, 4.30, 4.32, 30_000)
    d = PullbackDetector("TEST")
    _feed(d, bars)
    d.on_price(4.45, bars[-1].t + 60, bar_open=4.45)
    assert d.triggered["entry"] == 4.45


def test_trigger_moves_down_candle_by_candle():
    bars = add(_leg(), 4.38, 4.37, 4.30, 4.32, 30_000)
    d = PullbackDetector("TEST")
    _feed(d, bars)
    assert d.armed["trigger"] == 4.37
    events = d.on_bars(add(bars, 4.32, 4.34, 4.27, 4.30, 20_000))
    assert events and events[-1][0] == "rearmed"
    assert d.armed["trigger"] == 4.34 and d.armed["stop"] == 4.27
    assert d.armed["pullback_bars"] == 2


def test_giving_back_half_the_leg_fails_and_sticks():
    bars = add(_leg(), 4.38, 4.37, 4.05, 4.06, 60_000)
    d = PullbackDetector("TEST")
    _feed(d, bars)
    assert d.state == "failed" and "half the leg" in d.reason
    d.on_bars(add(bars, 4.06, 4.10, 4.04, 4.08))
    assert d.state == "failed"


def test_a_close_under_the_9_ema_fails():
    # A slow ten-bar climb keeps the 9 EMA close behind price, so a shallow
    # pullback (43% of the leg) can still close under it.
    bars = leg_up(base_morning(), [round(4.00 + 0.05 * i, 2) for i in range(1, 11)])
    add(bars, 4.50, 4.49, 4.30, 4.30, 20_000)
    d = PullbackDetector("TEST")
    _feed(d, bars)
    assert d.state == "failed" and "9 EMA" in d.reason


def test_an_armed_setup_that_fails_says_so():
    bars = add(_leg(), 4.38, 4.37, 4.30, 4.32, 30_000)
    d = PullbackDetector("TEST")
    _feed(d, bars)
    assert d.state == "armed"
    events = d.on_bars(add(bars, 4.32, 4.33, 4.05, 4.06, 60_000))
    assert d.state == "failed" and events[-1][0] == "failed"
    assert events[-1][1]["setup_key"] == int(bars[-3].t)      # the leg bar the setup was keyed on


def test_a_bar_that_ties_the_high_can_start_the_next_reading():
    # The research tries the tie bar both ways: as a pullback of the older high,
    # and (one bar later) as the leg high itself.
    bars = _leg()
    add(bars, 4.38, 4.39, 4.20, 4.25, 40_000)       # ties 4.39 and dips deep
    add(bars, 4.26, 4.33, 4.31, 4.32, 20_000)       # shallow pullback off the tie
    d = PullbackDetector("TEST")
    _feed(d, bars)
    assert d.state == "armed" and d.armed["leg_t"] == bars[-2].t and d.armed["stop"] == 4.31


def test_fourth_pullback_candle_fails():
    bars = _leg()
    for o, h, l, c in [(4.38, 4.37, 4.32, 4.34), (4.34, 4.36, 4.31, 4.33),
                       (4.33, 4.35, 4.30, 4.32), (4.32, 4.34, 4.29, 4.31)]:
        add(bars, o, h, l, c, 20_000)
    d = PullbackDetector("TEST")
    _feed(d, bars)
    assert d.state == "failed" and "3 candles" in d.reason


def test_risk_over_the_cap_is_not_armed():
    bars = leg_up(base_morning(), [4.25, 4.50, 4.75, 4.99])
    add(bars, 4.99, 4.98, 4.70, 4.80, 30_000)      # 30% retrace, but 29 cents of risk
    d = PullbackDetector("TEST")
    _feed(d, bars)
    assert d.state == "pullback" and "over 0.20" in d.reason
    assert d.armed is None


def test_outside_the_entry_window_is_not_armed():
    bars = base_morning(start_hh=11, start_mm=0)
    leg_up(bars, [4.08, 4.18, 4.28, 4.38])
    add(bars, 4.38, 4.37, 4.30, 4.32, 30_000)
    d = PullbackDetector("TEST")
    _feed(d, bars)
    assert d.state == "pullback" and "entry window" in d.reason


def test_second_pullback_after_a_trigger_and_a_new_leg():
    bars = add(_leg(), 4.38, 4.37, 4.30, 4.32, 30_000)
    d = PullbackDetector("TEST")
    _feed(d, bars)
    d.on_price(4.38, bars[-1].t + 61, bar_open=4.33)
    assert d.nth == 1
    add(bars, 4.33, 4.60, 4.33, 4.58, 120_000)        # the trigger bar runs to a new high
    d.on_bars(bars)
    assert d.state == "leg"
    add(bars, 4.58, 4.57, 4.49, 4.52, 40_000)
    d.on_bars(bars)
    assert d.state == "armed" and d.armed["kind"] == "second_pullback"


def test_macd_gate_can_be_turned_off_for_the_neighbourhood():
    d = PullbackDetector("TEST", PullbackParams(macd_positive=False))
    _feed(d, add(_leg(), 4.38, 4.37, 4.30, 4.32, 30_000))
    assert d.state == "armed"


def test_minute_bars_append_ignores_overlap_and_seed_keeps_older():
    t = et_ts(9, 31)
    mb = MinuteBars("TEST")
    assert mb.append(Bar(t, 4, 4.1, 3.9, 4.05)) is True
    assert mb.append(Bar(t, 4, 4.2, 3.9, 4.10)) is False          # same minute again
    kept = mb.seed([Bar(t - 120, 3.9, 4.0, 3.8, 3.95), Bar(t - 60, 3.95, 4.0, 3.9, 4.0), Bar(t, 1, 1, 1, 1)])
    assert kept == 2 and [b.t for b in mb.completed] == [t - 120, t - 60, t]


def test_bar_from_store_row_and_payload():
    row = bar_from({"t": "2026-09-21T13:31:00+00:00", "o": 4, "h": 4.1, "l": 3.9, "c": 4.05, "v": 900})
    assert row is not None and row.v == 900
    assert bar_from({"t": 1.0, "o": 1, "h": 0.5, "l": 1, "c": 1}) is None     # high under low
