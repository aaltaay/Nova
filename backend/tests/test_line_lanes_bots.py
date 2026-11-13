"""The bots' lane (ADR 071 decision 6; operator 2026-11-13: "only what a bot may buy"): one setup at a time, a trade
first, then near, then armed; the stock on the lane keeps it while it qualifies; a failed read moves nothing."""
from __future__ import annotations

from types import SimpleNamespace

from constants_bot import BOT_LEVEL_EYES, BOT_LEVEL_OFF, BOT_LEVEL_STRATEGY
from constants_setups import SETUP_STATE_NEAR
from line_lanes import bots_pick
from line_lanes.bots import choose
from line_lanes.bots_pick import Candidate, Wanted


def _w(*cands: tuple[str, str], error: str | None = None) -> Wanted:
    return Wanted(candidates=tuple(Candidate(s, "first_pullback", None, why) for s, why in cands), error=error)


def no_trade(_symbol: str) -> bool:
    return False


def test_an_empty_lane_takes_the_best_candidate():
    assert choose(None, _w(("AISP", "near"), ("RUNR", "armed")), no_trade)[0] == "AISP"


def test_no_candidate_leaves_the_lane_empty():
    assert choose(None, _w(), no_trade) == (None, None)
    assert choose("AISP", _w(), no_trade) == (None, None)       # its setup ended: the lane lets it go


def test_the_stock_on_the_lane_keeps_it_while_it_qualifies():
    assert choose("RUNR", _w(("AISP", "armed"), ("RUNR", "armed")), no_trade)[0] == "RUNR"


def test_a_better_tier_takes_the_lane_from_an_armed_one():
    assert choose("RUNR", _w(("AISP", "near"), ("RUNR", "armed")), no_trade)[0] == "AISP"


def test_nothing_takes_the_lane_from_a_trade():
    assert choose("RUNR", _w(("AISP", "trade"), ("RUNR", "trade")), no_trade)[0] == "RUNR"
    held = choose("RUNR", _w(("AISP", "near")), lambda s: s == "RUNR")   # Nova still holds RUNR
    assert held == ("RUNR", None)


def test_a_failed_read_moves_nothing():
    assert choose("RUNR", _w(error="the setup scanner could not be read"), no_trade)[0] == "RUNR"
    assert choose(None, _w(error="the bot session could not be read"), no_trade) == (None, None)


class _Lane:
    def __init__(self, setup: str, *, watching=(), near=(), trades=()) -> None:
        self.setup = setup
        self._watching = list(watching) + list(near)
        self.det = {s: SimpleNamespace(state=SETUP_STATE_NEAR if s in near else "armed") for s in self._watching}
        self.active_id = {s: f"{setup}-{s}" for s in self._watching}
        self.rows = {f"t-{s}": {"symbol": s} for s in trades}
        self._trades = [f"t-{s}" for s in trades]

    def watching(self):
        return list(self._watching)

    def trades(self, _now):
        return list(self._trades)


def test_only_a_setup_a_bot_may_buy_is_a_candidate():
    lanes = [_Lane("first_pullback", watching=["AISP"]), _Lane("bull_flag", near=["RUNR"]),
             _Lane("pullback_dip", near=["DIPP"]), _Lane("flat_top_5m", trades=["FLAT"])]
    levels = {"first_pullback": BOT_LEVEL_STRATEGY, "bull_flag": BOT_LEVEL_EYES, "pullback_dip": BOT_LEVEL_STRATEGY,
              "flat_top_5m": BOT_LEVEL_STRATEGY}
    got = bots_pick.pick(lanes, levels, {"AISP", "RUNR", "DIPP"}, 0.0)
    # bull flag at Eyes: watched, never bought; the pullback dip is watch-only (#847); FLAT's Buy is not Nova.
    assert [(c.symbol, c.why) for c in got] == [("AISP", "armed")]
    assert bots_pick.pick(lanes, {"first_pullback": BOT_LEVEL_OFF}, {"AISP"}, 0.0) == []
