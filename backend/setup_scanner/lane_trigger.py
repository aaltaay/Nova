"""A lane's trigger (ADR 022, ADR 029): the row stamped, the scoring started, the bot told.

Moved out of ``lane.py`` (2026-10-12, #845) when the trigger began scoring every target choice beside the
template's own exit (``target_choices.py``). At a trigger the row takes the fill's levels -- the entry, the stop,
both targets and the share sold at target 1 -- and the tape read when the lane saw the price; the template's
exit is scored (``scoring.ScoreTracker``: half at target 1, the rest at target 2, the stop staying put) and so is
every target choice on the same stop; then the open proposal closes and the playing lane tells its host.
"""
from __future__ import annotations

from typing import Any

from constants_setups import SETUP_STATE_TRIGGERED
from setup_scanner import lane_liquidity, lane_rows, target_choices
from setup_scanner.detector import candle_start
from setup_scanner.scoring import ScoreTracker


def tracker(lane: Any, setup: dict[str, Any], ts: float) -> ScoreTracker:
    """The template's exit for a trigger. A flat-top hold enters at a candle's close: it is scored from that
    candle, which takes no half at target 1 (the research's half_on_entry_bar=False)."""
    p = lane.p
    target2 = setup.get("target2")
    return ScoreTracker(
        entry=float(setup["entry"]), stop=float(setup["stop"]), target1=float(setup["target1"]),
        risk=float(setup["risk"]), triggered_at=ts,
        entry_bar_t=float(setup.get("score_bar_t") or candle_start(p, ts)),
        target2=float(target2) if target2 is not None else None,
        target1_fraction=float(setup.get("target1_fraction") or 1.0),
        bailout_bars=p.bailout_bars, window_min=p.score_window_min, bar_sec=p.bar_sec,
        half_on_entry_bar=bool(setup.get("half_on_entry_bar", True)), flush=p.flush, side=p.side)


def on_trigger(lane: Any, sym: str, sid: str, row: dict[str, Any], view: dict[str, Any], now: float) -> None:
    setup = view.get("setup") or {}
    ts = float(setup.get("triggered_at") or now)
    tape = lane.evaluate(sym, lane.read_at(ts))
    row.update({"state": SETUP_STATE_TRIGGERED, "reason": view["reason"], "triggered_at": ts,
                "entry": setup.get("entry"), "nth": setup.get("nth"), "trigger_tape": tape,
                "outcome": "open", "stop": setup.get("stop"), "risk": setup.get("risk"),
                **lane_rows.target_fields(setup), "detail": setup.get("detail"),
                "tf5_trigger": lane.tf5.get(sym), **lane_rows.at_trigger(lane, sym)})
    lane_liquidity.stamp(lane, sym, row, lane.read_at(ts))
    tr = lane.trackers[sid] = tracker(lane, setup, ts)
    det = lane.det.get(sym)
    choices = target_choices.book(det, setup, tr) if det is not None else None
    if choices is not None:
        lane.choices[sid] = choices
        row["target_scores"] = choices.wire()
    lane.journal("triggered", sym, setup_id=sid, setup=setup, price=setup.get("trigger_price"),
                 tape=tape, reason=view["reason"], tf5=row["tf5_trigger"], liquidity=row["liquidity"])
    lane._close_proposal(sid, "triggered")
    lane._announce_trigger(sym, sid, setup, tape, ts)
