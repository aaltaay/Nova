"""The target menu (#845, operator decisions 2026-10-09 and 2026-10-12): the material's four targets, sold in
two halves, and the stop choice beside the pattern's -- one module every scanner, the plan and the held card
take their targets from."""
from __future__ import annotations

import pytest

from setup_scanner import targets
from setup_scanner.targets import TargetSpec, plan, stop_for

MAP = [{"lo": 5.62, "hi": 5.63, "tag": "VWAP 5.62"}, {"lo": 6.0, "hi": 6.0, "tag": "$6.00"},
       {"lo": 4.9, "hi": 4.95, "tag": "double bottom"}]


def legs(got):
    return (got.target1, got.target2, got.fraction)


# -- the defaults ---------------------------------------------------------------------------------------------
def test_the_default_first_target_is_20c_or_1c_under_a_closer_half_dollar():
    far = plan(None, side="long", entry=5.21)                    # $5.50 is 29c over: +20c
    assert far.target1 == 5.41 and far.first.why == "+20c" and far.first.kind == "fixed"
    near = plan(None, side="long", entry=5.38)                   # $5.50 is 12c over: 1c under it
    assert near.target1 == 5.49 and near.first.why == "1c under $5.50" and near.first.kind == "round"


def test_a_half_dollar_too_near_the_entry_does_not_count():
    got = plan(None, side="long", entry=5.47)                    # 1c under $5.50 is 2c over the entry: no target
    assert got.target1 == 5.67 and got.first.why == "+20c"


def test_the_second_target_is_1c_under_the_high_of_day_past_target_1():
    got = plan(None, side="long", entry=5.21, levels=MAP, hod=6.12)
    assert legs(got) == (5.41, 6.11, 0.5) and got.second.why == "1c under HOD 6.12" and got.second.kind == "hod"


def test_without_a_high_of_day_past_target_1_target_2_is_the_next_level_past_it():
    got = plan(None, side="long", entry=5.21, levels=MAP, hod=5.43)   # HOD 2c past target 1: too near
    assert legs(got) == (5.41, 5.61, 0.5) and got.second.why == "1c under VWAP 5.62"


def test_with_nothing_past_target_1_everything_sells_at_target_1():
    got = plan(None, side="long", entry=5.21, levels=[], hod=5.30)
    assert legs(got) == (5.41, None, 1.0) and got.second is None
    wire = got.wire()
    assert (wire["target1"], wire["target2"], wire["target1_fraction"]) == (5.41, None, 1.0)
    assert wire["targets"]["first"] == {"kind": "fixed", "price": 5.41, "why": "+20c"}


# -- each kind, and its fall-back -------------------------------------------------------------------------------
@pytest.mark.parametrize("kind, want, why", [
    ("fixed", 5.31, "+10c"),
    ("next_level", 5.61, "1c under VWAP 5.62"),
    ("pullback_high", 5.80, "the pullback high 5.80"),
    ("hod", 6.11, "1c under HOD 6.12"),
])
def test_each_kind_for_target_1(kind, want, why):
    got = plan(TargetSpec(first=kind, second="none", fixed=0.10), side="long", entry=5.21, levels=MAP, hod=6.12,
               pullback_high=5.80)
    assert (got.target1, got.first.why, got.target2, got.fraction) == (want, why, None, 1.0)


@pytest.mark.parametrize("kind, words", [
    ("next_level", "no level of today's map 5c+ over the entry"),
    ("pullback_high", "no pullback high 5c+ over the entry"),
    ("hod", "the high of day is not 5c+ over the entry"),
])
def test_a_kind_without_a_price_falls_back_to_the_fixed_amount_and_says_so(kind, words):
    got = plan(TargetSpec(first=kind, second="none"), side="long", entry=5.21, levels=[], hod=5.22, pullback_high=None)
    assert got.target1 == 5.41 and got.first.kind == "fixed" and got.first.why == f"+20c ({words})"


def test_a_level_too_near_is_skipped_for_the_next():
    got = plan(TargetSpec(first="next_level", second="none"), side="long", entry=5.60, levels=MAP)
    assert got.target1 == 5.99 and got.first.why == "1c under $6.00"   # VWAP 5.62 is 2c over the entry


def test_target_2_of_each_kind_must_be_5c_past_target_1():
    spec = TargetSpec(first="fixed", second="fixed", fixed=0.20)
    assert plan(spec, side="long", entry=5.21).target2 is None         # the same price: everything at target 1
    spec = TargetSpec(first="fixed", second="pullback_high", split=0.25)
    got = plan(spec, side="long", entry=5.21, pullback_high=5.45)
    assert legs(got) == (5.41, None, 1.0)                               # 4c past target 1: not a target
    got = plan(spec, side="long", entry=5.21, pullback_high=5.46)
    assert legs(got) == (5.41, 5.46, 0.25)


def test_the_menu_reads_the_stocks_own_round_scale():
    got = plan(None, side="long", entry=223.89)                         # $225 is $1.11 over: +20c
    assert got.target1 == 224.09
    got = plan(None, side="long", entry=224.88)
    assert got.target1 == 224.99 and got.first.why == "1c under $225.00 ($5 round number)"


# -- shorts mirror it -------------------------------------------------------------------------------------------
def test_a_short_covers_under_its_entry_by_the_same_rules():
    got = plan(None, side="short", entry=5.62, levels=MAP, hod=4.88)    # hod is the low of day for a short
    assert got.target1 == 5.51 and got.first.why == "1c over $5.50"     # 12c under: closer than 20c
    assert got.target2 == 4.89 and got.second.why == "1c over LOD 4.88"
    far = plan(None, side="short", entry=5.79, levels=MAP, hod=5.70)
    assert far.target1 == 5.59 and far.first.why == "-20c"
    assert far.target2 == 4.96 and far.second.why == "1c over double bottom"   # the LOD is not past target 1
    pb = plan(TargetSpec(first="pullback_high", second="none"), side="short", entry=5.79, pullback_high=5.40)
    assert pb.target1 == 5.40 and pb.first.why == "the bounce low 5.40"


# -- the stop choice -------------------------------------------------------------------------------------------------
def test_the_pattern_stop_stands_by_default():
    stop, why = stop_for(None, side="long", entry=5.62, pattern_stop=5.48, cap=0.20)
    assert stop == 5.48 and why["kind"] == "pattern"


def test_the_round_stop_sits_3c_under_the_half_dollar_under_the_entry_inside_the_cap():
    spec = TargetSpec(stop="round")
    stop, why = stop_for(spec, side="long", entry=5.62, pattern_stop=5.48, cap=0.20, min_stop=0.03, slippage=0.01)
    assert stop == 5.47 and why == {"kind": "round", "why": "3c under $5.50", "round": 5.5}
    stop, why = stop_for(spec, side="long", entry=5.80, pattern_stop=5.70, cap=0.20, min_stop=0.03, slippage=0.01)
    assert stop == 5.70 and why["kind"] == "pattern" and "over the 0.20 cap" in why["why"]   # 5.47 would risk 0.33
    stop, why = stop_for(spec, side="short", entry=5.38, pattern_stop=5.55, cap=0.20)
    assert stop == 5.53 and why["why"] == "3c over $5.50"


def test_a_template_reads_its_menu_in_the_operators_units():
    spec = targets.spec_of({"target1_kind": "next_level", "target2_kind": "none", "target_fixed": 0.25,
                            "target_split_pct": 60, "stop_kind": "round"})
    assert spec == TargetSpec(first="next_level", second="none", fixed=0.25, split=0.6, stop="round")
    assert targets.spec_of({}) == targets.DEFAULT


def test_a_scanner_arms_on_the_templates_round_stop_and_the_plan_names_it():
    from setup_scanner.pullback import PullbackDetector, PullbackParams
    from stock_read import plan as plan_mod
    from tests.test_setup_scanner_lanes import armed_bars

    det = PullbackDetector("ABCD", p=PullbackParams(stop_cap=0.50, targets=TargetSpec(stop="round")))
    det.on_bars(armed_bars())
    a = det.armed
    assert (a["entry"], a["stop"], a["risk"]) == (4.38, 3.97, 0.41)       # 3c under $4.00, inside the 0.50 cap
    assert a["targets"]["stop"] == {"kind": "round", "why": "3c under $4.00", "round": 4.0}
    lane = {"setup_type": "first_pullback", "state": "armed", "setup": a, "forming": None, "rules": {}}
    assert plan_mod.from_setup(lane)["stop_rule"] == "3c under $4.00"
    tight = PullbackDetector("ABCD", p=PullbackParams(targets=TargetSpec(stop="round")))   # the 0.20 cap
    tight.on_bars(armed_bars())
    assert tight.armed["stop"] == 4.30 and tight.armed["targets"]["stop"]["kind"] == "pattern"
