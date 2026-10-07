"""The flat top counts its touches (ADR 031 amendment 2026-10-06; operator: "I doubt real life is going to be
perfect as this, so we may need a drift or a ratio to still consider flat top").

The default flat top is the one the operator's material draws: the high of day tapped again and again, each high
within the tolerance under it (0.5% of the level or a cent, whichever is more), drawn forming from its second touch
and armed at its third. The research's P2 rule stays one setting away (``P2_RULE``), and a template saved before
these parameters existed keeps running it (``catalogue.LEGACY``)."""
from __future__ import annotations

import json

from setup_scanner.bars import Bar
from setup_scanner.five_minute_lane import five_minute_params
from setup_scanner.flat_top import FlatTopDetector, FlatTopParams
from setup_scanner.flat_top_shape import P2_RULE, find, tolerance
from setup_scanner.lane_params import flat_top_params
from setup_templates import catalogue
from setup_templates.store import TemplateStore, default_template
from tests.setup_scanner_fixtures import add, base_morning, leg_up


def feed(det, bars: list[Bar]) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    for n in range(1, len(bars) + 1):
        events = det.on_bars(bars[:n])
    return events


def names(events) -> list[str]:
    return [name for name, _ in events]


def run_up() -> list[Bar]:
    """A quiet morning, then a 5% impulse whose last candle sets the 4.21 high of day (the first touch)."""
    return leg_up(base_morning(), [4.05, 4.10, 4.15, 4.20])


def test_the_tolerance_is_half_a_percent_or_a_cent_whichever_is_more():
    p = FlatTopParams()
    assert abs(tolerance(p, 4.21) - 0.02105) < 1e-9           # 0.5% of 4.21
    assert tolerance(p, 0.62) == 0.01                         # one tick on a cheap stock, never under it
    assert tolerance(FlatTopParams(**P2_RULE), 4.21) == 0.0   # the research's rule: the high itself


def test_a_flat_top_forms_at_its_second_touch_and_arms_at_its_third():
    d = FlatTopDetector("TEST")
    bars = run_up()
    add(bars, 4.20, 4.18, 4.16, 4.17, 30_000)       # 3 cents under the high: past the tolerance, no touch
    feed(d, bars)
    assert d.state == "leg" and "touched once" in d.reason and d.forming is None
    add(bars, 4.17, 4.20, 4.16, 4.19, 25_000)       # a cent under: the second touch
    events = d.on_bars(bars)
    assert d.state == "leg" and events == [] and "2 of 3 touches" in d.reason
    assert d.forming["waiting"] == "1 more touch" and d.forming["bars"] == 2 and d.forming["trigger"] == 4.21
    leg = d.leg
    assert leg["t"] == bars[-3].t and leg["high"] == 4.21 and len(leg["touches"]) == 2
    assert leg["touches"] == [[bars[-3].t, 4.21], [bars[-1].t, 4.20]] and leg["bars"] == 2
    add(bars, 4.19, 4.21, 4.17, 4.20, 20_000)       # the third tap, at the high itself
    events = d.on_bars(bars)
    assert names(events) == ["armed"] and d.state == "armed" and "3 touches" in d.reason
    a = d.armed
    assert a["trigger"] == 4.21 and a["leg_t"] == leg["t"] and a["pullback_bars"] == 3
    assert [t for t, _ in a["detail"]["touches"]] == [bars[-4].t, bars[-2].t, bars[-1].t]
    assert a["detail"]["zone"] == round(4.21 - 0.02105, 6) and a["detail"]["min_touches"] == 3
    assert a["stop"] == 4.16                          # break mode's stop: the base's low (the first touch's own low
                                                      # is the impulse's, not the base's)


def test_a_candle_a_little_over_the_earlier_touches_is_a_touch_and_the_level_drifts_up_to_it():
    d = FlatTopDetector("TEST")
    bars = run_up()
    add(bars, 4.20, 4.20, 4.16, 4.18, 30_000)       # taps 4.21 from a cent under: the second touch
    feed(d, bars)
    assert d.state == "leg" and "flat top 4.21: 2 of 3" in d.reason
    first = d.leg["t"]
    add(bars, 4.18, 4.22, 4.17, 4.19, 25_000)       # a cent over the 4.21 high: inside the tolerance, a touch
    events = d.on_bars(bars)
    assert names(events) == ["armed"] and d.armed["trigger"] == 4.22 and d.armed["leg_t"] == first
    assert len(d.armed["detail"]["touches"]) == 3


def test_highs_rising_a_cent_at_a_time_are_a_move_not_a_flat_top():
    d = FlatTopDetector("TEST")
    bars = leg_up(base_morning(), [4.05, 4.10, 4.15, 4.18])
    add(bars, 4.18, 4.20, 4.17, 4.19, 30_000)       # 4.19, 4.20, 4.21: every one a new high, inside the tolerance
    add(bars, 4.19, 4.21, 4.18, 4.20, 30_000)
    feed(d, bars)
    assert d.state == "leg" and d.reason.startswith("new high of day 4.21") and d.armed is None


def test_a_poke_past_the_tolerance_is_a_new_high_of_day_not_a_touch():
    d = FlatTopDetector("TEST")
    bars = run_up()
    add(bars, 4.20, 4.18, 4.16, 4.17, 30_000)
    add(bars, 4.17, 4.20, 4.16, 4.19, 25_000)
    feed(d, bars)
    assert "2 of 3" in d.reason
    add(bars, 4.19, 4.30, 4.18, 4.26, 60_000)       # 9 cents over: the old touches are out of the new zone
    d.on_bars(bars)
    assert d.state == "leg" and d.reason.startswith("new high of day 4.30") and "touches" not in (d.leg or {})


def test_a_tap_of_the_high_keeps_the_setup_where_the_research_rule_started_it_over():
    def day() -> list[Bar]:
        bars = run_up()
        add(bars, 4.20, 4.21, 4.17, 4.19, 30_000)   # ties the 4.21 high
        add(bars, 4.19, 4.20, 4.17, 4.18, 25_000)
        add(bars, 4.18, 4.19, 4.16, 4.18, 25_000)
        return bars

    flat = FlatTopDetector("TEST")
    p2 = FlatTopDetector("TEST", FlatTopParams(**P2_RULE))
    feed(flat, day())
    feed(p2, day())
    bars = day()
    first = bars[-4].t                               # the impulse's last candle: the first touch of 4.21
    assert flat.armed["leg_t"] == first
    assert p2.armed["leg_t"] == bars[-3].t           # P2 moves to the latest candle at the high, a new row


def test_the_hold_may_retest_inside_the_zone_and_only_a_close_under_it_fails():
    d = FlatTopDetector("TEST")
    bars = run_up()
    add(bars, 4.20, 4.21, 4.17, 4.19, 30_000)
    add(bars, 4.19, 4.20, 4.17, 4.18, 25_000)
    feed(d, bars)
    assert d.state == "armed"
    brk = bars[-1].t + 60 + 20
    assert names(d.on_price(4.22, brk)) == ["near"]
    assert d.armed["detail"]["broke_bar_t"] == bars[-1].t + 60 and d.armed["detail"]["broke_at"] == brk
    add(bars, 4.18, 4.24, 4.18, 4.22, 60_000)        # the break's own candle
    d.on_bars(bars)
    add(bars, 4.22, 4.23, 4.19, 4.20, 40_000)        # back inside the zone, closed under the high: keep waiting
    assert d.on_bars(bars) == [] and d.state == "near" and "1 of 3 candles" in d.reason
    add(bars, 4.20, 4.27, 4.195, 4.26, 50_000)       # dips into the zone (4.195 > 4.189) and closes green over 4.21
    events = d.on_bars(bars)
    assert names(events) == ["triggered"]
    t = d.triggered
    assert (t["entry"], t["stop"]) == (4.27, 4.195) and t["detail"]["hold_bar_t"] == bars[-1].t
    assert t["detail"]["hold_high"] == 4.27


def test_a_close_under_the_zone_after_the_break_fails_it():
    d = FlatTopDetector("TEST")
    bars = run_up()
    add(bars, 4.20, 4.21, 4.17, 4.19, 30_000)
    add(bars, 4.19, 4.20, 4.17, 4.18, 25_000)
    feed(d, bars)
    d.on_price(4.22, bars[-1].t + 80)
    add(bars, 4.18, 4.23, 4.17, 4.22, 60_000)
    d.on_bars(bars)
    add(bars, 4.22, 4.22, 4.15, 4.18, 40_000)        # 4.18 is under the 4.189 floor
    events = d.on_bars(bars)
    assert names(events) == ["failed"] and "closed back under" in d.reason


def test_a_flat_top_that_began_longer_ago_than_the_base_allows_is_stale():
    d = FlatTopDetector("TEST", FlatTopParams(max_consol=4))
    bars = run_up()
    for _ in range(5):                               # five taps of 4.21, each closing a little under
        add(bars, 4.19, 4.21, 4.17, 4.19, 20_000)
    feed(d, bars)
    assert d.state == "failed" and "ran past 4 candles" in d.reason


def test_find_reads_the_shape_from_the_lanes_series():
    d = FlatTopDetector("TEST")
    bars = run_up()
    add(bars, 4.20, 4.21, 4.17, 4.19, 30_000)
    add(bars, 4.19, 4.20, 4.17, 4.18, 25_000)
    d.series.update(bars)
    shape, miss = find(d.series, len(bars) - 1, d.p)
    assert miss is None and shape.first == len(bars) - 3 and shape.bars == 2
    assert len(shape.touches) == 3 and shape.base_low == 4.17 and shape.level == 4.21


def test_the_default_runs_the_material_and_a_template_saved_before_keeps_the_research_rule(tmp_path):
    p = flat_top_params(catalogue.defaults("flat_top_breakout"))
    assert (p.base_start, p.min_touches, p.touch_pct, p.touch_dollars, p.max_consol) == ("first_touch", 3, 0.005,
                                                                                       0.01, 20)
    # A flat-top template saved before 2026-10-06: every value it had then, none of the new ones.
    saved = {k: v for k, v in catalogue.defaults("flat_top_breakout").items() if not k.startswith(("ft_min_t", "ft_t",
                                                                                                    "ft_base"))}
    saved["ft_max_consol"] = 6
    path = tmp_path / "setup-templates.json"
    path.write_text(json.dumps({"schema_version": 1, "setups": {"flat_top_breakout": {"in_play": None, "templates": [
        {"id": "t-old", "name": "Old", "note": "", "rev": 4, "values": saved}]}}}), encoding="utf-8")
    old = next(t for t in TemplateStore(path).templates("flat_top_breakout") if t.id == "t-old")
    q = flat_top_params(old.values)
    assert (q.base_start, q.min_touches, q.touch_pct, q.touch_dollars, q.max_consol) == ("last_high", 1, 0.0, 0.0, 6)
    assert old.rev == 4 and old.error is None


def test_the_flat_tops_default_rules_are_a_new_revision_and_no_other_setups_are():
    assert default_template("flat_top_breakout").rev == 2
    assert {default_template(s).rev for s in ("first_pullback", "bull_flag", "red_to_green", "gap_and_go")} == {1}
    assert five_minute_params("flat_top_breakout").template_rev == 2
    assert five_minute_params("first_pullback").template_rev == 1


def test_a_template_of_two_touches_waits_for_its_base_not_for_a_touch():
    d = FlatTopDetector("TEST", FlatTopParams(min_touches=2))
    bars = run_up()
    add(bars, 4.20, 4.21, 4.17, 4.19, 30_000)       # the second touch, one candle after the first
    feed(d, bars)
    assert d.state == "leg" and d.forming["waiting"] == "1 more candle" and "the base needs 2 candles" in d.reason
    add(bars, 4.19, 4.18, 4.17, 4.18, 25_000)
    assert names(d.on_bars(bars)) == ["armed"]
