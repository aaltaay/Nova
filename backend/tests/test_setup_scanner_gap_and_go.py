"""Gap and Go on the setup scanner (ADR 031 amendment 2026-10-02): the pre-market high, broken after the open."""
from __future__ import annotations

from setup_scanner.bars import Bar
from setup_scanner.detectors import make_detector, window
from setup_scanner.gap_and_go import GapAndGoDetector, GapAndGoParams
from setup_templates import catalogue
from setup_scanner.lane_params import PATTERNS
from tests.setup_scanner_fixtures import add, et_ts

PMH = 4.50


def premarket(pmh: float = PMH) -> list[Bar]:
    """08:20-09:29: a spike to ``pmh`` at 08:45, then a drift around 4.20 into the open."""
    bars = []
    t0 = et_ts(8, 20)
    for i in range(70):
        px = 4.20 + (0.01 if i % 2 else 0.0)
        hi = pmh if i == 25 else px + 0.02
        bars.append(Bar(t0 + 60 * i, px, hi, px - 0.02, px + 0.01, 20_000))
    return bars


def feed(det, bars: list[Bar]) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    for n in range(1, len(bars) + 1):
        events = det.on_bars(bars[:n])
    return events


def names(events) -> list[str]:
    return [name for name, _ in events]


def test_before_the_open_it_draws_the_levels_it_would_arm_with():
    d = GapAndGoDetector("TEST")
    feed(d, premarket())
    assert d.state == "watching" and "pre-market high 4.50" in d.reason and d.armed is None
    f = d.forming
    assert (f["trigger"], f["entry"], f["stop"], f["risk"]) == (4.50, 4.51, 4.3296, 0.1804)   # 4% of 4.51 < 20c
    assert f["target1"] == round(4.51 + 2 * 0.1804, 4) and f["waiting"] == "waits for the 09:30 open"
    assert d.on_price(4.60, et_ts(9, 29) + 30, bar_open=4.20) == []                      # no break before the open


def test_an_open_under_the_pre_market_high_arms_then_the_break_triggers_once():
    d = GapAndGoDetector("TEST")
    bars = premarket()
    feed(d, bars)
    t = et_ts(9, 30)
    events = d.on_price(4.30, t + 1, bar_open=4.30)
    assert names(events) == ["armed"] and d.state == "armed"
    a = d.armed
    assert a["kind"] == "gap_and_go" and a["detail"]["open"] == 4.30 and a["detail"]["pm_high"] == PMH
    assert names(d.on_price(4.48, t + 20, bar_open=4.30)) == ["near"]
    events = d.on_price(4.52, t + 40, bar_open=4.30)
    assert names(events) == ["triggered"] and d.nth == 1
    s = d.triggered
    assert (s["entry"], s["stop"], s["risk"]) == (4.51, 4.3296, 0.1804) and s["trigger_price"] == 4.52
    add(bars, 4.30, 4.60, 4.28, 4.58, 90_000)
    assert d.on_bars(bars) == [] and d.state == "triggered"
    assert d.on_price(4.70, t + 90, bar_open=4.58) == []                                  # one a day


def test_a_gap_through_the_pre_market_high_at_the_open_skips_the_day():
    d = GapAndGoDetector("TEST")
    feed(d, premarket())
    assert d.on_price(4.55, et_ts(9, 30) + 1, bar_open=4.55) == []
    assert d.spent and d.state == "watching" and "skips a gap through it" in d.reason
    assert d.on_price(4.80, et_ts(9, 35), bar_open=4.70) == []


def test_a_gap_over_the_trigger_inside_a_minute_enters_at_its_open_and_the_stop_moves_with_it():
    d = GapAndGoDetector("TEST")
    feed(d, premarket())
    t = et_ts(9, 30)
    d.on_price(4.30, t + 1, bar_open=4.30)
    events = d.on_price(4.70, et_ts(9, 41) + 1, bar_open=4.68)
    assert names(events) == ["triggered"]
    s = d.triggered
    assert s["entry"] == 4.68 and s["risk"] == 0.1872 and s["stop"] == round(4.68 - 0.1872, 4)


def test_twenty_cents_caps_the_stop_on_a_dearer_stock():
    p = GapAndGoParams()
    assert p.stop_distance(10.01) == 0.20 and p.stop_distance(3.01) == 0.1204


def test_no_break_by_the_cutoff_ends_the_day():
    d = GapAndGoDetector("TEST")
    bars = premarket()
    feed(d, bars)
    d.on_price(4.30, et_ts(9, 30) + 1, bar_open=4.30)
    while bars[-1].t < et_ts(9, 59):
        add(bars, 4.30, 4.35, 4.28, 4.31, 30_000)
    events = d.on_bars(bars)
    assert names(events) == ["disarmed"] and d.spent and "no break" in d.reason and "10:00" in d.reason
    assert d.on_price(4.60, et_ts(10, 0) + 5, bar_open=4.55) == []


def test_a_seed_after_the_open_arms_from_the_opening_candle_and_a_break_it_missed_spends_the_try():
    quiet = GapAndGoDetector("TEST")
    bars = premarket()
    add(bars, 4.30, 4.40, 4.28, 4.35, 50_000)            # 09:30 under the high
    add(bars, 4.35, 4.42, 4.33, 4.40, 50_000)
    feed(quiet, bars)
    assert quiet.state == "armed" and quiet.armed["detail"]["open"] == 4.30
    missed = GapAndGoDetector("TEST")
    add(bars, 4.40, 4.62, 4.39, 4.60, 90_000)             # 09:32 went through 4.50 before the scanner saw it
    feed(missed, bars)
    assert missed.spent and missed.armed is None and "broke at 09:32" in missed.reason
    assert missed.on_price(4.65, et_ts(9, 33) + 5, bar_open=4.60) == []


def test_the_macd_rule_when_a_template_turns_it_on_waits_for_the_histogram():
    d = GapAndGoDetector("TEST", GapAndGoParams(macd_positive=True))
    bars = premarket()
    feed(d, bars)
    d.series.hist[-1] = -0.01
    assert d.on_price(4.30, et_ts(9, 30) + 1, bar_open=4.30) == []
    assert d.state == "pullback" and "MACD below zero" in d.reason and d.armed is None
    add(bars, 4.30, 4.36, 4.29, 4.35, 60_000)
    d.on_bars(bars)
    d.series.hist[-1] = 0.01
    d.armed = None
    assert names(d._try_arm(et_ts(9, 31) + 60)) == ["armed"]


def test_no_pre_market_trade_means_no_level():
    d = GapAndGoDetector("TEST")
    bars = [Bar(et_ts(9, 30), 4.0, 4.1, 3.9, 4.05, 10_000)]
    assert d.on_bars(bars) == [] and "no pre-market" in d.reason


def test_registry_window_catalogue_and_params():
    p = PATTERNS["gap_and_go"](catalogue.defaults("gap_and_go"))
    assert isinstance(make_detector("gap_and_go", "TEST", p), GapAndGoDetector)
    assert window("gap_and_go", p) == ("09:30", "10:00")
    assert catalogue.has_scanner("gap_and_go") and catalogue.wire("gap_and_go")["scanner"] is True
    d = catalogue.defaults("gap_and_go")
    assert (d["bot_window_start"], d["bot_window_end"]) == ("09:30", "10:00") and d["macd_positive"] is False
