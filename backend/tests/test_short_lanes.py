"""A short setup on the scanner's lanes end to end (ADR 049, #778 step 4): it arms, comes near from above,
proposes at Eyes with nobody taking it, triggers downward, scores mirrored and says its side and SSR
everywhere -- and nothing trades it until step 5."""
from __future__ import annotations

import asyncio

import pytest

from setup_scanner.engine import SetupEngine
from setup_scanner.store import SetupStore
from setup_templates.store import TemplateStore
from tests.test_short_detectors import _backside_day

SYM = "FADE"
SETUP = "backside_lower_high"


class ShortTape:
    """A book at the backside's 5.47 trigger and red prints at the bid."""

    def __init__(self):
        self.now = 0.0

    def sync(self, wanted, now):
        self.now = now

    def books(self, sym):
        book = {"bids": [{"price": 5.47, "size": 800}, {"price": 5.46, "size": 1200}],
                "asks": [{"price": 5.48, "size": 900}, {"price": 5.49, "size": 1000}]}
        return [(self.now - 5, book), (self.now - 0.2, book)]

    def prints(self, sym):
        return [{"ts": self.now - 3 + i * 0.5, "size": 300, "side": "bid", "price": 5.47} for i in range(4)]

    def has_depth(self, sym):
        return True

    def has_tape(self, sym):
        return True

    def close(self):
        pass


def make(tmp_path, level=1):
    bars = _backside_day()
    audits: list[dict] = []
    lines: list[dict] = []
    triggers: list[dict] = []
    clock = {"t": bars[-1].t + 61}
    eng = SetupEngine(store=SetupStore(tmp_path / "setups.db"), tape=ShortTape(), universe=lambda: [SYM],
                      seed=lambda sym, since: list(bars), replay_desk=lambda: False,
                      audit=lambda **kw: audits.append(kw), clock=lambda: clock["t"],
                      templates=lambda: TemplateStore(tmp_path / "t.json"), journal=lines.append,
                      levels=lambda: {"chosen": None, "levels": {SETUP: level}}, setups=(SETUP,))
    eng.pillars = lambda sym, now: {"price": 5.48, "change_pct": 37.0, "rvol": 6.0, "float": 9e6, "news": None,
                                    "headline": None, "catalyst": None}
    eng.short_context = lambda sym, now: {"prior_close": 4.00, "ssr_yesterday": False}
    eng.add_trigger_listener(triggers.append)
    return eng, audits, lines, triggers, clock


def run(eng, now):
    asyncio.run(eng.tick(now))


def last(eng, price, ts, bar_open):
    eng.on_l1_minute("last", SYM, {"price": price, "ts": ts, "bar_open": bar_open})


def test_a_short_arms_proposes_triggers_downward_and_scores_with_its_side_and_ssr(tmp_path):
    eng, audits, lines, triggers, clock = make(tmp_path)
    run(eng, clock["t"])
    [lane] = eng.playing_lanes()
    assert lane.p.side == "short" and lane.det[SYM].state == "armed", lane.det[SYM].reason
    [row] = lane.rows.values()
    assert row["side"] == "short" and row["ssr"] == "off"         # the prior close 4.00: never under 3.60
    assert row["trigger"] == 5.47 and row["entry_planned"] == 5.46 and row["stop"] == 5.56
    assert row["target1"] == pytest.approx(5.26)
    checks = row["pillars"]["checks"]
    assert checks["run"] is True and checks["fade"] is True and checks["vwap"] is True
    assert checks["bad_news"] is None and checks["borrow"] is None and row["grade"] == "C"
    armed = next(e for e in lines if e["event"] == "armed")
    assert armed["ssr"] == "off" and armed["setup_type"] == SETUP

    last(eng, 5.49, clock["t"], 5.48)                              # two cents over the trigger: near
    run(eng, clock["t"])
    assert lane.det[SYM].state == "near"
    board = eng.board(clock["t"])
    [brow] = board["rows"]
    assert brow["side"] == "short" and brow["ssr"] == "off" and brow["distance"] == pytest.approx(0.02)
    assert board["setups"][0]["side"] == "short" and board["setups"][0]["test"]["state"] == "queued"
    [prop] = board["proposals"]
    assert prop["side"] == "short" and prop["ssr"] == "off" and prop["taken_by"] is None   # nothing takes a short
    assert prop["tape_now"] == "go" and audits[0]["outcome"] == "proposed"

    clock["t"] += 2
    last(eng, 5.46, clock["t"], 5.48)                              # at the entry: triggered
    run(eng, clock["t"])
    assert lane.det[SYM].state == "triggered"
    saved = eng.store.rows()[0]
    assert saved["side"] == "short" and saved["ssr"] == "off" and saved["trigger_tape"]["verdict"] == "go"
    assert saved["trigger_tape"]["metrics"]["side"] == "short"
    [event] = triggers
    assert event["side"] == "short" and event["ssr"] == "off" and event["setup_type"] == SETUP
    fired = next(e for e in lines if e["event"] == "triggered")
    assert fired["ssr"] == "off" and fired["reason"].startswith("traded 5.46 under the 5.47 trigger")

    clock["t"] += 5
    last(eng, 5.25, clock["t"], 5.48)                              # under target 1: target first
    run(eng, clock["t"])
    assert eng.store.rows()[0]["outcome"] == "target_first"


def test_the_bot_and_auto_entry_skip_a_short_trigger_until_step_5():
    from bot.first_pullback import admit
    from constants_bot import BOT_SKIP_SHORT_LATER

    event = {"symbol": SYM, "setup_type": SETUP, "side": "short", "tape": {"verdict": "go"}, "grade": "A"}
    found = admit.blockers(event, {}, now=0.0, venue_now=("paper", True, True))
    assert found[0][0] == BOT_SKIP_SHORT_LATER and "step 5 of #778" in found[0][1]
    assert admit.taker(SYM, SETUP) is None


def test_the_squares_say_a_short_trigger_waits_on_step_5():
    from bot import trigger_cells

    cell = trigger_cells._strategy_on({"setup_type": "bear_flag", "symbol": SYM, "ts": 0.0}, "paper", None)
    assert cell["ok"] is False and "step 5 of #778" in cell["why"]


def test_auto_record_gives_a_short_setup_no_line_and_leaves_its_window_out():
    from types import SimpleNamespace

    from leaderboard.auto_record_picks import pick_setups
    from leaderboard.auto_record_windows import _windows_of
    from setup_templates import catalogue

    class Lane:
        def __init__(self, short):
            self.p = SimpleNamespace(short=short)
            self.det = {"X": SimpleNamespace(state="near")}

        def trade_symbols(self, now):
            return []

        def watching(self):
            return {"X"}

    assert pick_setups([Lane(short=True)], 0.0) == [] and pick_setups([Lane(short=False)], 0.0) == [("X", "near")]
    found = {setup for setup, _start, _end in _windows_of(catalogue.defaults)}
    assert SETUP not in found and "ssr_bounce" not in found and "first_pullback" in found
