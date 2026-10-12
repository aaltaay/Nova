"""Every target choice, scored side by side on each trigger (#845, operator ask 2026-10-12). Pure.

For each trigger the eyes score the menu's choices beside the template's own exit: a fixed 10c, 20c and 30c,
the next level of today's map, the pullback's high and the high of day -- each selling everything at its one
target -- and the menu's default pair (target 1 and target 2, split as the template splits). Every choice
enters at the trigger's entry with the same stop, bailout, flush exit and close (``scoring.ScoreTracker``,
the template's numbers): only the target differs. A choice a trigger has no price for (no level of today's
map past the entry, a setup without a pullback high) is scored as the menu would trade it -- at the fixed
amount, the template's -- and ``fell_back`` says so, so every choice is scored on the same triggers.

The scores ride on the trigger's ``setups.db`` row (``target_scores``) and its backtest row::

  {schema_version, entry, stop, risk, choices: {NAME: {kind, target1, target2, target1_fraction, why,
   fell_back, bar_r, exit_reason, closed_at}}}

``book`` builds a trigger's choices from its detector; the lane feeds them every completed bar and flow
reading (``feed_bar``, ``feed_flow``) until each has closed. ``eyes/target_readout.py`` ranks them.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from constants_setups import (
    SETUPS_TARGET_CHOICE_DEFAULT,
    SETUPS_TARGET_CHOICE_FIXED,
    SETUPS_TARGET_CHOICES_SCHEMA_VERSION,
    SETUPS_TARGET_FIXED,
    SETUPS_TARGET_HOD,
    SETUPS_TARGET_NEXT_LEVEL,
    SETUPS_TARGET_NONE,
    SETUPS_TARGET_PULLBACK_HIGH,
)
from setup_scanner import targets as _targets
from setup_scanner.bars import Bar
from setup_scanner.scoring import ScoreTracker


def fixed_name(amount: float) -> str:
    return f"fixed_{round(amount * 100):d}c"


# The choices in the order the read-out lists them: name -> the menu kind for target 1 (target 2 none).
SINGLE_KINDS: dict[str, str] = {
    **{fixed_name(a): SETUPS_TARGET_FIXED for a in SETUPS_TARGET_CHOICE_FIXED},
    SETUPS_TARGET_NEXT_LEVEL: SETUPS_TARGET_NEXT_LEVEL,
    SETUPS_TARGET_PULLBACK_HIGH: SETUPS_TARGET_PULLBACK_HIGH,
    SETUPS_TARGET_HOD: SETUPS_TARGET_HOD,
}
NAMES: tuple[str, ...] = (*SINGLE_KINDS, SETUPS_TARGET_CHOICE_DEFAULT)


def plans(spec: _targets.TargetSpec, *, side: str, entry: float, levels: Any, hod: float | None,
          pullback_high: float | None) -> dict[str, _targets.Targets]:
    """Each choice's targets for one entry: the single kinds, then the menu's default pair (``spec``'s fixed
    amount and split, the default kinds)."""
    out: dict[str, _targets.Targets] = {}
    kw = {"side": side, "entry": entry, "levels": levels, "hod": hod, "pullback_high": pullback_high}
    fixed_amounts = dict(zip((fixed_name(a) for a in SETUPS_TARGET_CHOICE_FIXED), SETUPS_TARGET_CHOICE_FIXED,
                             strict=True))
    for name, kind in SINGLE_KINDS.items():
        one = _targets.TargetSpec(first=kind, second=SETUPS_TARGET_NONE, fixed=fixed_amounts.get(name, spec.fixed))
        out[name] = _targets.plan(one, **kw)
    out[SETUPS_TARGET_CHOICE_DEFAULT] = _targets.plan(
        _targets.TargetSpec(fixed=spec.fixed, split=spec.split), **kw)
    return out


@dataclass
class ChoiceBook:
    """One trigger's choices and their trackers."""

    entry: float
    stop: float
    risk: float
    trackers: dict[str, ScoreTracker] = field(default_factory=dict)
    meta: dict[str, dict[str, Any]] = field(default_factory=dict)

    @property
    def done(self) -> bool:
        return all(t.exit_px is not None for t in self.trackers.values())

    def on_bar(self, bar: Bar) -> bool:
        """Feed a completed bar to every open choice; True when one closed on it."""
        closed = False
        for t in self.trackers.values():
            if t.exit_px is None and t.on_bar(bar):
                closed = True
        return closed

    def on_flow(self, **reading: Any) -> bool:
        acted = False
        for t in self.trackers.values():
            if t.exit_px is None and t.on_flow(**reading) == "exit":
                acted = True
        return acted

    def wire(self) -> dict[str, Any]:
        return {"schema_version": SETUPS_TARGET_CHOICES_SCHEMA_VERSION, "entry": round(self.entry, 4),
                "stop": round(self.stop, 4), "risk": round(self.risk, 4),
                "choices": {name: {**self.meta[name], "bar_r": t.bar_r(), "exit_reason": t.exit_reason,
                                   "closed_at": t.closed_at} for name, t in self.trackers.items()}}


def book(det: Any, setup: dict[str, Any], tracker: ScoreTracker) -> ChoiceBook | None:
    """A trigger's choices, read from its detector at the trigger (today's map, the high of day, the pullback's
    high the setup armed with), each tracker a copy of ``tracker`` (the template's stop, bailout, flush, candle
    and side) with its own targets. None without the levels to score."""
    try:
        entry, stop, risk = float(setup["entry"]), float(setup["stop"]), float(setup["risk"])
    except (KeyError, TypeError, ValueError):
        return None
    if risk <= 0:
        return None
    t = setup.get("targets") or {}
    got = plans(det.target_spec(), side=tracker.side, entry=entry,
                levels=_targets.day_map(det.map_series(), entry), hod=det.extreme(),
                pullback_high=t.get("pullback_high"))
    out = ChoiceBook(entry=entry, stop=stop, risk=risk)
    for name, plan in got.items():
        kind = SINGLE_KINDS.get(name)
        out.meta[name] = {"kind": kind or SETUPS_TARGET_CHOICE_DEFAULT, "target1": plan.target1,
                          "target2": plan.target2, "target1_fraction": plan.fraction,
                          "why": plan.first.why + (f"; {plan.second.why}" if plan.second else ""),
                          "fell_back": kind is not None and plan.first.kind != kind}
        out.trackers[name] = ScoreTracker(
            entry=tracker.entry, stop=tracker.stop, target1=plan.target1, risk=tracker.risk,
            triggered_at=tracker.triggered_at, entry_bar_t=tracker.entry_bar_t, target2=plan.target2,
            target1_fraction=plan.fraction, bailout_bars=tracker.bailout_bars,
            half_on_entry_bar=tracker.half_on_entry_bar, flush=tracker.flush, window_min=tracker.window_min,
            bar_sec=tracker.bar_sec, side=tracker.side)
    return out


def feed_bar(lane: Any, sym: str, bar: Bar) -> None:
    """A completed bar for every open book of ``sym``; a book that changed is saved on its row."""
    for sid, b in list(lane.choices.items()):
        row = lane.rows.get(sid)
        if row is None or row.get("symbol") != sym:
            continue
        if b.on_bar(bar):
            save(lane, sid)


def feed_flow(lane: Any, sid: str, **reading: Any) -> None:
    b = lane.choices.get(sid)
    if b is not None and b.on_flow(**reading):
        save(lane, sid)


def save(lane: Any, sid: str) -> None:
    b, row = lane.choices.get(sid), lane.rows.get(sid)
    if b is None or row is None:
        return
    row["target_scores"] = b.wire()
    lane.host.save(row)
    if b.done:
        lane.journal("target_scores", row["symbol"], setup_id=sid, scores=row["target_scores"])
        lane.choices.pop(sid, None)
