"""The pullback dip (#847; operator ask 2026-10-12): the first pullback's run and pullback, bought at the candle
that bottoms it -- a bottoming wick or the first green close -- with the high of the pullback as target 1.

Watch only: the eyes watch, score and draw it; it never proposes, never reaches Nova's bot, Auto-entry or Approve,
and its On is locked.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from bot.errors import BotError
from bot.setup_levels import apply, effective, on_lock
from constants_bot import BOT_REASON_SETUP_WATCH_ONLY, BOT_WATCH_ONLY_SETUPS, watch_only
from setup_scanner import dip_candle, target_choices
from setup_scanner.bars import Bar
from setup_scanner.detectors import make_detector
from setup_scanner.engine import SetupEngine
from setup_scanner.lane_params import lane_params
from setup_scanner.pullback_dip import PullbackDipDetector
from setup_scanner.store import SetupStore
from setup_scanner.trade_verdict import of_event, verdict
from setup_templates import catalogue
from setup_templates.store import TemplateStore, default_template
from tests.setup_scanner_fixtures import add, base_morning, leg_up
from tests.test_setup_scanner_engine import SYM, FakeTape, bar_msg

DIP = "pullback_dip"
LEG_HIGH = 4.39                     # leg_up's last close 4.38, its high a cent over


def params(**values):
    """The default template's pattern, with ``values`` over its own (the operator's units)."""
    t = default_template(DIP)
    return lane_params(SimpleNamespace(id=t.id, rev=t.rev, fingerprint="x", name=t.name, setup=DIP,
                                       values={**t.values, **values})).pattern


def run_up() -> list[Bar]:
    """A quiet base at 4.00 from 08:20, then a 10% run to a 4.39 high of day."""
    return leg_up(base_morning(), [4.08, 4.18, 4.28, 4.38])


def feed(det, bars: list[Bar]) -> list[tuple[str, dict]]:
    out: list[tuple[str, dict]] = []
    for k in range(len(bars)):
        out += det.on_bars(bars[:k + 1])
    return out


def at_the_high(**values) -> tuple[PullbackDipDetector, list[Bar]]:
    bars = run_up()
    det = make_detector(DIP, SYM, params(**values))
    feed(det, bars)
    assert det.state == "leg" and det.leg["high"] == pytest.approx(LEG_HIGH)
    return det, bars


# -- the bottoming wick -------------------------------------------------------------------------
def test_a_bottoming_wick_after_the_pullback_arms_and_triggers_at_its_close():
    det, bars = at_the_high()
    assert isinstance(det, PullbackDipDetector) and det.p.entry_mode == "wick"
    add(bars, 4.38, 4.38, 4.30, 4.32, 30_000)                   # the pullback's first candle: red, no wick
    assert det.on_bars(bars) == [] and det.state == "pullback"
    assert "waiting for a bottoming wick" in det.reason and det.forming["waiting"] == "a bottoming wick"
    wick = add(bars, 4.31, 4.33, 4.24, 4.32, 30_000)[-1]        # a new low, 7c of lower wick, closing near the top
    (armed, a), (trig, t) = det.on_bars(bars)
    assert (armed, trig) == ("armed", "triggered")
    s = t["setup"]
    assert (s["trigger"], s["entry"], s["stop"], s["risk"]) == (4.32, 4.33, 4.23, 0.1)   # a cent over the close,
    assert s["kind"] == "pullback_dip" and s["nth"] == 1 and s["pullback_bars"] == 2    # a cent under the low
    assert s["triggered_at"] == wick.t + 60 and s["score_bar_t"] == wick.t and s["half_on_entry_bar"] is False
    assert s["detail"]["entry_mode"] == "wick" and s["detail"]["entry_bar_t"] == wick.t
    assert s["detail"]["pullback_low"] == 4.24 and s["detail"]["pullback_high"] == pytest.approx(LEG_HIGH)
    assert s["detail"]["wick_pct"] == pytest.approx(0.7778) and s["detail"]["close_pct"] == pytest.approx(0.8889)
    assert "a bottoming wick" in t["reason"] and det.state == "triggered" and det.armed is None
    assert a["setup"]["armed_at"] == wick.t + 60 and a["state"] == "armed"


@pytest.mark.parametrize("candle, words", [
    ((4.31, 4.33, 4.29, 4.30), "lower wick is 1c"),             # 1c of wick: the spread, not buyers
    ((4.33, 4.34, 4.25, 4.27), "lower wick is 2c"),              # a long red body, a short wick
    ((4.30, 4.31, 4.24, 4.25), "lower wick is 1c"),              # closed at its low
    ((4.33, 4.36, 4.31, 4.35), "is over the pullback's low"),   # a fine candle that is not the pullback's bottom
])
def test_a_candle_that_is_not_a_bottoming_wick_keeps_it_waiting(candle, words):
    det, bars = at_the_high()
    add(bars, 4.38, 4.38, 4.30, 4.32, 30_000)
    det.on_bars(bars)
    add(bars, *candle, 30_000)
    assert det.on_bars(bars) == [] and det.state == "pullback" and words in det.reason, det.reason
    assert dip_candle.wick(bars[-2:], det.p).ok is False


def test_the_wick_and_close_thresholds_are_the_templates():
    b = Bar(0, 4.31, 4.33, 4.24, 4.32)
    p = SimpleNamespace(wick_min=0.5, close_min=0.6, wick_min_dollars=0.02)
    assert dip_candle.wick([b], p).ok
    assert not dip_candle.wick([b], SimpleNamespace(wick_min=0.8, close_min=0.6, wick_min_dollars=0.02)).ok
    assert not dip_candle.wick([b], SimpleNamespace(wick_min=0.5, close_min=0.95, wick_min_dollars=0.02)).ok
    assert not dip_candle.wick([b], SimpleNamespace(wick_min=0.5, close_min=0.6, wick_min_dollars=0.08)).ok


# -- the first candle to close green --------------------------------------------------------------
def test_the_first_green_close_after_a_red_one_is_the_entry():
    det, bars = at_the_high(dip_entry="green")
    add(bars, 4.38, 4.38, 4.30, 4.32, 30_000)                   # red
    assert det.on_bars(bars) == [] and "waiting for the first green close" in det.reason
    green = add(bars, 4.32, 4.36, 4.31, 4.35, 30_000)[-1]       # green
    events = det.on_bars(bars)
    assert [e for e, _ in events] == ["armed", "triggered"]
    s = events[-1][1]["setup"]
    assert (s["entry"], s["stop"], s["risk"]) == (4.36, 4.29, 0.07)
    assert s["detail"]["entry_mode"] == "green" and s["detail"]["red_bars"] == 1 and s["score_bar_t"] == green.t
    assert "the first green close after 1 red candle" in events[-1][1]["reason"]


def test_a_green_close_before_any_red_is_not_it_and_a_later_green_is_not_the_first():
    det, bars = at_the_high(dip_entry="green", min_pullback_bars=3)
    add(bars, 4.36, 4.38, 4.34, 4.37, 30_000)                   # green, no red before it: not the entry
    assert det.on_bars(bars) == [] and det.state == "pullback"
    add(bars, 4.37, 4.37, 4.31, 4.32, 30_000)                   # red
    add(bars, 4.32, 4.35, 4.31, 4.34, 30_000)                   # the first green after a red -- at candle 3
    events = det.on_bars(bars[:-1]) + det.on_bars(bars)
    assert [e for e, _ in events] == ["armed", "triggered"]

    det, bars = at_the_high(dip_entry="green", min_pullback_bars=3)
    add(bars, 4.38, 4.38, 4.30, 4.32, 30_000)                   # red
    add(bars, 4.32, 4.35, 4.31, 4.34, 30_000)                   # the first green, too early for a 3-candle pullback
    add(bars, 4.34, 4.36, 4.32, 4.35, 30_000)                   # green again: not the first
    feed_tail = det.on_bars(bars[:-2]) + det.on_bars(bars[:-1]) + det.on_bars(bars)
    assert feed_tail == [] and det.state == "failed"
    assert "the first green close came 1 candle ago and was not the entry" in det.reason


# -- the run, the stop, the targets -----------------------------------------------------------------
def test_no_entry_without_a_fresh_run():
    bars = base_morning(n=45)                                   # a quiet day: no leg
    det = make_detector(DIP, SYM, params())
    feed(det, bars)
    add(bars, 4.01, 4.02, 3.95, 4.01, 30_000)                   # a perfect bottoming wick, but no run before it
    assert det.on_bars(bars) == [] and det.state == "watching" and det.triggered is None


def test_a_pullback_that_gives_back_half_the_leg_fails():
    det, bars = at_the_high()
    add(bars, 4.38, 4.38, 4.30, 4.32, 30_000)
    det.on_bars(bars)
    add(bars, 4.31, 4.33, 4.15, 4.32, 30_000)                   # a wick that gives back 60% of the leg
    assert det.on_bars(bars) == [] and det.state == "failed" and det.reason == "gave back half the leg"


def test_the_stop_cap_and_floor_block_the_entry_and_say_so():
    det, bars = at_the_high(stop_cap=0.08)
    add(bars, 4.38, 4.38, 4.30, 4.32, 30_000)
    det.on_bars(bars)
    add(bars, 4.31, 4.33, 4.24, 4.32, 30_000)                   # risk 4.33 - 4.23 = 0.10
    assert det.on_bars(bars) == [] and det.state == "pullback" and det.triggered is None
    assert "risk 0.10 is over 0.08" in det.reason and det.forming["blocked"] == "risk 0.10 is over 0.08"
    assert det.p.risk_slippage == 0.0                            # the entry's cent over the close is the slippage

    det, bars = at_the_high(dip_stop_offset=0.03)
    add(bars, 4.38, 4.38, 4.30, 4.32, 30_000)
    det.on_bars(bars)
    add(bars, 4.31, 4.33, 4.24, 4.32, 30_000)
    s = det.on_bars(bars)[-1][1]["setup"]
    assert (s["stop"], s["risk"]) == (4.21, 0.12)               # the template's offset under the pullback low


def test_target_1_is_the_high_the_pullback_came_off_and_target_2_the_menus():
    det, bars = at_the_high()
    add(bars, 4.38, 4.38, 4.30, 4.32, 30_000)
    det.on_bars(bars)
    add(bars, 4.31, 4.33, 4.24, 4.32, 30_000)
    s = det.on_bars(bars)[-1][1]["setup"]
    t = s["targets"]
    assert t["rule"]["first"] == "pullback_high" and t["rule"]["second"] == "hod_or_level"
    assert t["first"]["kind"] == "pullback_high" and s["target1"] == pytest.approx(LEG_HIGH)
    assert t["pullback_high"] == pytest.approx(LEG_HIGH) and s["target1_fraction"] == 0.5
    assert s["target2"] is not None and s["target2"] >= s["target1"] + 0.05
    assert params(target1_kind="fixed").targets.first == "fixed"   # the menu stays the operator's


def test_two_dips_a_day_then_none():
    det, _ = at_the_high()
    det.restore(2)
    assert det.nth == 2 and det.state == "watching" and "used" in det.reason


# -- the template --------------------------------------------------------------------------------
def test_its_template_is_the_first_pullbacks_run_with_its_own_entry_and_no_bot_rules():
    values = catalogue.defaults(DIP)
    fp = catalogue.defaults("first_pullback")
    for key in ("leg_pct", "leg_window", "leg_lookback", "require_hod", "max_retrace", "ema_period", "macd_positive",
                "stop_cap", "min_stop", "entry_offset", "session_start", "entry_cutoff"):
        assert values[key] == fp[key], key
    assert (values["min_pullback_bars"], values["max_pullback_bars"]) == (2, 4)
    assert values["dip_entry"] == "wick" and values["dip_wick_min_pct"] == 50 and values["dip_close_min_pct"] == 60
    assert values["dip_wick_min_dollars"] == 0.02 and values["dip_min_red_bars"] == 1 and values["dip_stop_offset"] == 0.01
    assert values["target1_kind"] == "pullback_high" and values["target2_kind"] == "hod_or_level"
    assert not any(k.startswith("bot_") for k in values) and "near_dollars" not in values
    assert "risk_slippage" not in values
    specs = {s.key: s for s in catalogue.specs(DIP)}
    assert [v for v, _ in specs["dip_entry"].choices] == ["wick", "green"]
    with pytest.raises(catalogue.TemplateError):
        catalogue.validate(DIP, {**values, "dip_entry": "the moon"})
    assert default_template(DIP).rev == 1
    assert "Watch only" in catalogue.SOURCES[DIP]


# -- watch only ------------------------------------------------------------------------------------
def test_it_is_the_one_watch_only_setup_and_never_a_trade():
    assert BOT_WATCH_ONLY_SETUPS == frozenset({DIP, "abcd"}) and watch_only(DIP) and not watch_only("first_pullback")
    judged = verdict(grade="A", pillars={"passed": 5, "known": 5, "total": 5}, setup_type=DIP)
    assert judged["ok"] is False and judged["reasons"][0].startswith("watch only")
    assert verdict(grade="A", setup_type="first_pullback")["ok"] is True
    event = {"setup_type": DIP, "grade": "A", "tape": {"verdict": "go"}, "setup": {"risk": 0.1}}
    assert of_event(event)["ok"] is False


def test_its_on_is_locked_and_an_old_on_reads_as_eyes():
    row = {"level": 2, "setup_levels": {}}
    with pytest.raises(BotError) as refused:
        apply(row, {DIP: 2})
    assert refused.value.status_code == 409 and refused.value.reason == BOT_REASON_SETUP_WATCH_ONLY
    assert "watch only" in refused.value.message and on_lock(DIP) and on_lock("first_pullback") is None
    assert apply(row, {DIP: 1}) == {DIP: (0, 1)}
    assert effective({"level": 2, "setup_levels": {DIP: 2, "first_pullback": 2}})[DIP] == 1
    assert effective({"level": 2, "setup_levels": {DIP: 2, "first_pullback": 2}})["first_pullback"] == 2


def test_the_bot_and_auto_entry_hold_it_back_whatever_its_level():
    from bot.first_pullback.admit import blockers, taker
    from bot.persist import load_session
    from tests.bot_helpers import ready_l2

    now = 1_790_000_000.0
    event = {"symbol": "IMCC", "setup_id": "IMCC-2026-09-24-1@pullback_dip", "setup_type": DIP,
             "setup": {"kind": "pullback_dip", "trigger": 10.0, "entry": 10.01, "stop": 9.9, "risk": 0.11,
                       "target1": 10.2, "triggered_at": now, "nth": 1},
             "tape": {"verdict": "go", "reasons": ["green"]}, "grade": "A",
             "pillars": {"passed": 5, "known": 5, "total": 5}, "filtered": None, "spread": 0.02}
    ready_l2(brain=None, symbols=("IMCC",), setups=("first_pullback",))
    held = dict(blockers(event, load_session(), now=now))
    assert "watch only" in held["BOT_SETUP_NOT_STRATEGY"]
    assert taker("IMCC", DIP) is None


def test_the_stock_modes_approve_and_the_plan_say_not_a_trade():
    from stock_mode.model import lane_verdict
    from stock_read.plan import choose, trade_verdict

    lane = {"setup_type": DIP, "state": "triggered", "grade": "A", "setup": {"risk": 0.1}}
    assert lane_verdict(lane)["ok"] is False
    assert trade_verdict({"source": "setup", "setup_type": DIP, "grade": "A", "state": "armed"}, lane)["ok"] is False
    dip = {"setup_type": DIP, "state": "triggered", "setup": {"triggered_at": 100.0}, "level": 1}
    pull = {"setup_type": "first_pullback", "state": "leg", "forming": {"entry": 1.0}, "level": 1}
    assert choose([pull, dip], 110.0) is pull           # a tradeable lane forming leads a dip that triggered
    assert choose([dip], 110.0) is dip                  # alone, the dip leads (and its plan is NOT A TRADE)


def test_it_takes_no_auto_record_line_and_a_dip_that_died_refused_no_trade():
    from eyes.aftermath import after
    from leaderboard.auto_record_picks import pick_setups

    def fake(setup: str) -> SimpleNamespace:
        return SimpleNamespace(p=SimpleNamespace(setup=setup, short=False), trade_symbols=lambda now: {SYM},
                               watching=lambda: set(), det={})

    assert pick_setups([fake(DIP)], 0.0) == []
    assert pick_setups([fake("first_pullback")], 0.0) == [(SYM, "trade")]
    ep = {"setup_type": DIP, "died_at": 100.0, "end": "failed", "leg": {"t": 0.0, "high": 4.39, "low": 3.99},
          "setup": None, "died_bar_t": 60.0}
    assert after(ep, [], now=1_000.0) is None


# -- the lane: rows, scores side by side, no proposal, no bot ------------------------------------------
def make_engine(tmp_path, seed: list[Bar], level: int = 1):
    audits: list[dict] = []
    clock = {"t": seed[-1].t + 30}
    eng = SetupEngine(store=SetupStore(tmp_path / "setups.db"), tape=FakeTape(), universe=lambda: [SYM],
                      seed=lambda sym, since: list(seed), replay_desk=lambda: False,
                      audit=lambda **kw: audits.append(kw), clock=lambda: clock["t"],
                      templates=lambda: TemplateStore(tmp_path / "t.json"), journal=lambda e: None,
                      levels=lambda: {"chosen": None, "levels": {DIP: level}}, setups=(DIP,))
    eng.pillars = lambda sym, now: {"price": 4.3, "change_pct": 12.0, "rvol": 6.0, "float": 9e6, "news": None,
                                    "headline": None, "catalyst": None}
    return eng, audits, clock


@pytest.mark.parametrize("level", [1, 2])
def test_its_lane_scores_every_target_choice_and_never_proposes_or_tells_the_bot(tmp_path, level):
    bars = run_up()
    eng, audits, clock = make_engine(tmp_path, bars, level=level)
    heard: list[dict] = []
    eng.add_trigger_listener(heard.append)
    asyncio.run(eng.tick(clock["t"]))
    lane = eng.playing_lane(DIP)
    assert lane is not None and lane.det[SYM].state == "leg"
    red = Bar(bars[-1].t + 60, 4.38, 4.38, 4.30, 4.32, 30_000)
    eng.on_l1_minute("bar", SYM, bar_msg(red))
    clock["t"] = red.t + 61
    asyncio.run(eng.tick(clock["t"]))
    # Waiting for the candle that bottoms it, its prints are kept: the trigger reads the tape printed into it.
    assert lane.det[SYM].state == "pullback" and SYM in eng.tape.synced and SYM not in lane.watching()
    wick = Bar(red.t + 60, 4.31, 4.33, 4.24, 4.32, 30_000)
    eng.on_l1_minute("bar", SYM, bar_msg(wick))
    clock["t"] = wick.t + 61
    asyncio.run(eng.tick(clock["t"]))
    assert lane.det[SYM].state == "triggered"
    [row] = eng.store.rows(setup_type=DIP)
    assert row["kind"] == "pullback_dip" and row["entry"] == 4.33 and row["stop"] == 4.23
    assert row["id"].endswith("@pullback_dip") and row["trigger_tape"]["verdict"] in ("go", "wait", "veto", "blind")
    assert set(row["target_scores"]["choices"]) == set(target_choices.NAMES)       # side by side, like every setup
    assert row["tf5_armed"] is None and row["tf5_trigger"] is None      # registered after trial T8: not its rows
    assert row["target_scores"]["choices"]["pullback_high"]["target1"] == pytest.approx(LEG_HIGH)
    assert heard == [] and lane.open_proposals() == [] and lane.proposals == {}
    assert not [a for a in audits if a.get("action") == "setup_proposal"]
    card = next(s for s in eng.board(clock["t"])["setups"] if s["id"] == DIP)
    assert card["watch_only"] is True and card["proposing"] is False
    assert [r["state"] for r in eng.board(clock["t"])["rows"] if r["setup_type"] == DIP] == ["triggered"]
