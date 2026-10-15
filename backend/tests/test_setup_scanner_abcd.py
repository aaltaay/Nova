"""The ABCD (operator ask 2026-10-15): a squeeze to the high of day, a pullback (A), a push that fails to clear the
high (B), a higher low (C), bought one cent over B (D). The tolerances read the flat top's way: a percentage or a
cent, whichever is more.

Watch only: the eyes watch, score and draw it; it never proposes, never reaches Nova's bot, and its On is locked.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from bot.errors import BotError
from bot.setup_levels import apply, on_lock
from constants_bot import BOT_REASON_SETUP_WATCH_ONLY, BOT_WATCH_ONLY_SETUPS, watch_only
from setup_scanner import abcd_shape, target_choices
from setup_scanner.bars import Bar
from setup_scanner.detectors import make_detector
from setup_scanner.engine import SetupEngine
from setup_scanner.lane_params import lane_params
from setup_scanner.store import SetupStore
from setup_scanner.trade_verdict import verdict
from setup_templates import catalogue
from setup_templates.store import TemplateStore, default_template
from tests.setup_scanner_fixtures import add, base_morning
from tests.test_setup_scanner_engine import SYM, FakeTape, bar_msg

ABCD = "abcd"


def params(**values):
    """The default template's pattern, with ``values`` over its own (the operator's units)."""
    t = default_template(ABCD)
    return lane_params(SimpleNamespace(id=t.id, rev=t.rev, fingerprint="x", name=t.name, setup=ABCD,
                                       values={**t.values, **values})).pattern


def candles(bars: list[Bar], rows: list[tuple[float, float, float, float]]) -> list[Bar]:
    for o, h, lo, c in rows:
        add(bars, o, h, lo, c, 60_000)
    return bars


SQUEEZE = [(4.00, 4.16, 3.99, 4.15), (4.15, 4.31, 4.14, 4.30), (4.30, 4.46, 4.29, 4.45), (4.45, 4.60, 4.44, 4.58)]
PULLBACK = [(4.58, 4.59, 4.48, 4.50), (4.50, 4.51, 4.38, 4.40), (4.40, 4.41, 4.30, 4.33)]       # A: 4.30
PUSH = [(4.33, 4.45, 4.32, 4.44), (4.44, 4.50, 4.43, 4.48)]                                    # B: 4.50
DIP = [(4.48, 4.49, 4.40, 4.42), (4.42, 4.44, 4.36, 4.40)]                                     # C: 4.36


def day(*legs) -> list[Bar]:
    """A quiet base at 4.00 from 08:20, then the candles of each leg in turn."""
    bars = base_morning()
    for leg in legs:
        candles(bars, leg)
    return bars


def feed(det, bars: list[Bar]) -> list[tuple[str, dict]]:
    out: list[tuple[str, dict]] = []
    for k in range(len(bars)):
        out += det.on_bars(bars[:k + 1])
    return out


def detector(**values):
    return make_detector(ABCD, SYM, params(**{"macd_positive": False, **values}))


# -- the shape ------------------------------------------------------------------------------------------------
def test_the_zigzag_counts_a_swing_only_once_price_moved_its_size():
    h = [10.0, 10.5, 10.4, 10.3, 10.6, 10.0]
    lo = [9.9, 10.4, 10.3, 10.25, 10.5, 9.9]
    piv = abcd_shape.zigzag(h, lo, 0.03)
    # 10.5 -> 10.25 is under 3%: one swing up to 10.6, then the drop to 9.9 confirms it.
    assert [(p.i, p.price, p.kind, p.confirmed) for p in piv] == [(4, 10.6, "H", True), (5, 9.9, "L", False)]


def test_each_tolerance_is_the_percentage_or_a_cent_whichever_is_more():
    assert abcd_shape.tolerance(4.60, 0.005, 0.01) == pytest.approx(0.023)
    assert abcd_shape.tolerance(1.00, 0.005, 0.01) == pytest.approx(0.01)


def test_a_b_inside_the_tolerance_over_the_high_is_a_double_top_and_past_it_a_new_high():
    p = params(macd_positive=False)
    s = base_morning()
    double = candles(list(s), SQUEEZE + PULLBACK + [(4.33, 4.45, 4.32, 4.44), (4.44, 4.62, 4.43, 4.52)] + DIP)
    got = abcd_shape.read([b.h for b in double], [b.lo for b in double], _hod(double), p)
    assert got.stage == "formed" and got.high.price == 4.60 and got.b.price == 4.62
    clear = candles(list(s), SQUEEZE + PULLBACK + [(4.33, 4.45, 4.32, 4.44), (4.44, 4.65, 4.43, 4.52)] + DIP)
    got = abcd_shape.read([b.h for b in clear], [b.lo for b in clear], _hod(clear), p)
    assert got.high.price == 4.65 and got.stage == "a"          # a new high: the ABCD starts again from it


def _hod(bars: list[Bar]) -> list[float]:
    out, top = [], float("-inf")
    for b in bars:
        top = max(top, b.h)
        out.append(top)
    return out


# -- the detector ----------------------------------------------------------------------------------------------
def test_a_b_c_arms_on_b_with_the_stop_under_c_and_the_high_as_target_1():
    det = detector()
    feed(det, day(SQUEEZE, PULLBACK))
    assert det.state == "leg" and "wait for A" in det.reason
    bars = day(SQUEEZE, PULLBACK, PUSH, DIP)
    det = detector()
    events = feed(det, bars)
    assert det.state == "armed" and [e for e, _ in events].count("armed") == 1
    a = det.armed
    assert a["trigger"] == 4.50 and a["entry"] == 4.51 and a["stop"] == 4.35 and a["risk"] == pytest.approx(0.16)
    assert a["target1"] == pytest.approx(4.59)                  # 1c under the 4.60 high of day
    pts = det.leg["abcd"]
    assert [pts[k][1] for k in ("high", "a", "b", "c")] == [4.60, 4.30, 4.50, 4.36]
    assert pts["b_max"] == pytest.approx(4.623) and pts["a_floor"] == pytest.approx(4.2785)
    assert a["detail"]["deadline"] == det.leg["t"] + 20 * 60


def test_a_lower_c_re_arms_with_the_stop_under_it():
    bars = day(SQUEEZE, PULLBACK, PUSH, DIP)
    det = detector()
    feed(det, bars)
    events = det.on_bars(candles(bars, [(4.40, 4.41, 4.34, 4.36)]))
    assert ("rearmed" in [e for e, _ in events]) and det.armed["stop"] == 4.33


def test_a_price_over_b_triggers_it():
    bars = day(SQUEEZE, PULLBACK, PUSH, DIP)
    det = detector()
    feed(det, bars)
    events = det.on_price(4.52, bars[-1].t + 90, bar_open=4.40)
    assert [e for e, _ in events] == ["triggered"] and det.state == "triggered"
    assert det.triggered["entry"] == 4.51 and det.triggered["kind"] == "abcd"
    assert det.on_bars(candles(bars, [(4.40, 4.58, 4.39, 4.57)])) == []     # the trade is on


def test_a_low_under_a_fails_it_until_a_new_high():
    bars = day(SQUEEZE, PULLBACK, PUSH, DIP)
    det = detector()
    feed(det, bars)
    events = det.on_bars(candles(bars, [(4.40, 4.41, 4.25, 4.27)]))
    assert det.state == "failed" and "undercut A 4.30" in det.reason and [e for e, _ in events] == ["failed"]
    assert det.on_bars(candles(bars, [(4.27, 4.40, 4.26, 4.39)])) == [] and det.state == "failed"


def test_c_inside_the_tolerance_under_a_still_holds():
    det = detector()
    feed(det, day(SQUEEZE, PULLBACK, PUSH, [(4.48, 4.49, 4.40, 4.42), (4.42, 4.44, 4.285, 4.40)]))
    assert det.state == "armed" and det.armed["stop"] == pytest.approx(4.275)


def test_no_break_within_the_window_fails_it_as_too_slow():
    bars = day(SQUEEZE, PULLBACK, PUSH, DIP)
    det = detector(abcd_max_minutes=6)
    feed(det, bars)
    det.on_bars(candles(bars, [(4.40, 4.45, 4.38, 4.43)] * 3))
    assert det.state == "failed" and "too slow" in det.reason


def test_waiting_for_b_past_the_window_fails_it_too():
    det = detector(abcd_max_minutes=6)
    feed(det, day(SQUEEZE, PULLBACK, PUSH[:1], [(4.44, 4.46, 4.42, 4.44)] * 6))
    assert det.state == "failed" and "without a B that fails under the high: too slow" in det.reason


def test_a_weak_push_is_not_b_yet():
    det = detector(abcd_bounce_pct=90)
    feed(det, day(SQUEEZE, PULLBACK, PUSH, DIP))
    assert det.state == "leg" and "real push" in det.reason


def test_the_risk_cap_holds_it_back_and_says_so():
    det = detector(stop_cap=0.10)
    feed(det, day(SQUEEZE, PULLBACK, PUSH, DIP))
    assert det.state == "pullback" and "over 0.10" in det.reason and det.forming["blocked"]


def test_its_template_has_its_own_pattern_and_no_bot_rules():
    t = default_template(ABCD)
    keys = {s.key for s in catalogue.specs(ABCD)}
    assert {"abcd_swing_pct", "abcd_b_over_pct", "abcd_c_under_pct", "abcd_tol_dollars", "abcd_bounce_pct",
            "abcd_max_minutes", "abcd_stop_offset"} <= keys
    assert not [s for s in catalogue.specs(ABCD) if s.group == "bot"]
    assert t.values["abcd_swing_pct"] == 3 and t.values["abcd_b_over_pct"] == 0.5 and t.values["stop_cap"] == 0.30
    assert t.values["target1_kind"] == "hod" and t.values["entry_cutoff"] == "15:30"
    assert "Watch only" in catalogue.SOURCES[ABCD]


# -- watch only ------------------------------------------------------------------------------------------------
def test_it_is_watch_only_and_never_a_trade():
    assert ABCD in BOT_WATCH_ONLY_SETUPS and watch_only(ABCD)
    judged = verdict(grade="A", pillars={"passed": 5, "known": 5, "total": 5}, setup_type=ABCD)
    assert judged["ok"] is False and judged["reasons"][0].startswith("watch only")


def test_its_on_is_locked():
    with pytest.raises(BotError) as refused:
        apply({"level": 2, "setup_levels": {}}, {ABCD: 2})
    assert refused.value.status_code == 409 and refused.value.reason == BOT_REASON_SETUP_WATCH_ONLY
    assert on_lock(ABCD)


def make_engine(tmp_path, seed: list[Bar]):
    clock = {"t": seed[-1].t + 30}
    audits: list[dict] = []
    eng = SetupEngine(store=SetupStore(tmp_path / "setups.db"), tape=FakeTape(), universe=lambda: [SYM],
                      seed=lambda sym, since: list(seed), replay_desk=lambda: False,
                      audit=lambda **kw: audits.append(kw), clock=lambda: clock["t"],
                      templates=lambda: TemplateStore(tmp_path / "t.json"), journal=lambda e: None,
                      levels=lambda: {"chosen": None, "levels": {ABCD: 1}}, setups=(ABCD,))
    eng.pillars = lambda sym, now: {"price": 4.4, "change_pct": 12.0, "rvol": 6.0, "float": 9e6, "news": None,
                                    "headline": None, "catalyst": None}
    return eng, audits, clock


def test_its_lane_scores_the_trigger_and_never_proposes_or_tells_the_bot(tmp_path):
    bars = day(SQUEEZE, PULLBACK, PUSH, DIP)
    eng, audits, clock = make_engine(tmp_path, bars)
    heard: list[dict] = []
    eng.add_trigger_listener(heard.append)
    asyncio.run(eng.tick(clock["t"]))
    lane = eng.playing_lane(ABCD)
    assert lane is not None and lane.det[SYM].state == "armed"
    clock["t"] = bars[-1].t + 90
    eng.on_l1_minute("last", SYM, {"price": 4.52, "ts": clock["t"], "bar_open": 4.40})
    asyncio.run(eng.tick(clock["t"]))
    assert lane.det[SYM].state == "triggered"
    [row] = eng.store.rows(setup_type=ABCD)
    assert row["kind"] == "abcd" and row["entry"] == 4.51 and row["stop"] == 4.35
    assert row["id"].endswith("@abcd") and set(row["target_scores"]["choices"]) == set(target_choices.NAMES)
    assert heard == [] and lane.proposals == {}
    assert not [a for a in audits if a.get("action") == "setup_proposal"]
    card = next(s for s in eng.board(clock["t"])["setups"] if s["id"] == ABCD)
    assert card["watch_only"] is True and card["proposing"] is False
