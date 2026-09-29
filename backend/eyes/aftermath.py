"""What price did after a setup died (ADR 036 amendment, operator ask 2026-09-29).

For a failed (its lane may still show it) or faded episode (``eyes/episodes.py``) and the day's one-minute bars
(the chart's: ``bars_store``, less IBKR's no-trade minutes):

- ``level`` is the high it was building under -- its trigger when it armed, else
  its leg's high -- and ``floor`` the low it would have stopped under -- its stop
  when it armed, else the lowest low from the candle after the leg's high through
  the candle it died on;
- from the candle after the one it died on (the one it died inside, when it died
  between closes), for ``EYES_EPISODE_AFTER_MIN`` minutes, ``first`` says which it
  crossed first. A candle that did both reads ``low``: the order inside a minute
  is unknown, and the study never credits a run it cannot prove;
- after ``high``, ``trade`` scores the trade the rule refused the way the
  scoreboard scores an armed setup (``setup_scanner/scoring.py``): the first touch
  of the target or the stop, the move for and against it, and the bar exit rules.

Scores, never fills: no tape, no slippage. Pure: an episode and bars in, a dict out.
"""
from __future__ import annotations

from typing import Any

from constants_bot import BOT_SETUP_RED_TO_GREEN
from constants_eyes import EYES_EPISODE_AFTER_MIN
from constants_setups import (
    SETUP_OUTCOME_OPEN,
    SETUP_OUTCOME_STOP_FIRST,
    SETUP_OUTCOME_TARGET_FIRST,
    SETUPS_EMA_PERIOD,
    SETUPS_ENTRY_OFFSET_DOLLARS,
    SETUPS_SCORE_WINDOW_MIN,
    SETUPS_TARGET_R,
)
from setup_scanner.bars import Bar, minute_start
from setup_scanner.scoring import ScoreTracker
from setup_scanner.series import ema

EPS = 1e-9
FIRST_HIGH = "high"
FIRST_LOW = "low"
FIRST_NEITHER = "neither"
FIRST_PENDING = "pending"
FIRST_UNKNOWN = "unknown"


def _num(v: Any) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if x == x else None


def levels(ep: dict[str, Any], bars: list[Bar]) -> tuple[float | None, float | None, float | None, float | None]:
    """``(level, entry, floor, target)`` the episode was working with: its armed setup's, else its leg's
    high, one cent over it, the lowest low from the candle after the leg's high through the candle it
    died on, and no target (the trade sets it from its risk)."""
    setup = ep.get("setup") or {}
    leg = ep.get("leg") or {}
    trigger, stop = _num(setup.get("trigger")), _num(setup.get("stop"))
    if trigger is not None and stop is not None:
        entry = _num(setup.get("entry")) or round(trigger + SETUPS_ENTRY_OFFSET_DOLLARS, 4)
        return trigger, entry, stop, _num(setup.get("target1"))
    level = _num(leg.get("high"))
    if level is None:
        return None, None, None, None
    entry = round(level + SETUPS_ENTRY_OFFSET_DOLLARS, 4)
    if ep.get("setup_type") == BOT_SETUP_RED_TO_GREEN:
        return level, entry, _num(leg.get("low")), None      # the open, and the lowest low since it
    leg_t, died_bar = _num(leg.get("t")), _num(ep.get("died_bar_t"))
    span = [b.lo for b in bars if leg_t is not None and died_bar is not None and leg_t < b.t <= died_bar]
    return level, entry, (min(span) if span else None), None


def died(ep: dict[str, Any]) -> bool:
    """A setup that failed (its lane may still show it) or faded."""
    return ep.get("died_at") is not None and ep.get("end") in ("failed", "faded", None)


def after(ep: dict[str, Any], bars: list[Bar], *, now: float) -> dict[str, Any] | None:
    """What price did after a setup failed or faded; ``None`` for any other episode."""
    died_at = _num(ep.get("died_at"))
    if not died(ep) or died_at is None:
        return None
    level, entry, floor, target = levels(ep, bars)
    if level is None or entry is None:
        return None
    died_bar = _num(ep.get("died_bar_t"))
    start = minute_start(died_at)
    end = start + EYES_EPISODE_AFTER_MIN * 60
    first_i = next((i for i, b in enumerate(bars) if b.t >= start), len(bars))
    window = [b for b in bars[first_i:] if b.t < end]
    complete = now >= end
    death = next((b for b in bars if died_bar is not None and b.t == died_bar), None)
    first, crossed, k = None, None, -1
    for i, b in enumerate(window):
        if floor is not None and b.lo < floor - EPS:
            first, crossed = FIRST_LOW, b.t        # a candle that did both counts the low
            break
        if b.h > level + EPS:
            first, crossed, k = FIRST_HIGH, b.t, i
            break
    if first is None:
        first = (FIRST_NEITHER if window else FIRST_UNKNOWN) if complete else FIRST_PENDING
    trade = None
    if first == FIRST_HIGH and floor is not None:
        trade = refused_trade(bars, first_i + k, level=level, entry=entry, floor=floor, target=target)
    return {
        "from_ts": died_at, "price": death.c if death else None, "level": level, "entry": entry, "floor": floor,
        "window_min": EYES_EPISODE_AFTER_MIN, "complete": complete, "bars": len(window),
        "high": max((b.h for b in window), default=None), "low": min((b.lo for b in window), default=None),
        "first": first, "crossed_at": crossed, "trade": trade,
    }


def refused_trade(bars: list[Bar], i: int, *, level: float, entry: float, floor: float,
                  target: float | None) -> dict[str, Any] | None:
    """The trade the rule refused, bought as price crossed ``level`` on ``bars[i]``: one cent over it (the
    candle's open when it gapped over), stop ``floor``, target ``target`` or entry + 2R."""
    cross = bars[i]
    if cross.o > level + EPS:
        entry = max(entry, cross.o)
    risk = round(entry - floor, 4)
    if risk <= EPS:
        return None
    if target is None or target <= entry + EPS:
        target = round(entry + SETUPS_TARGET_R * risk, 4)
    until = cross.t + SETUPS_SCORE_WINDOW_MIN * 60
    outcome, outcome_at = SETUP_OUTCOME_OPEN, None
    best, worst = cross.h, cross.c
    for j, b in enumerate(bars[i:]):
        if b.t >= until:
            break
        if j:
            best, worst = max(best, b.h), min(worst, b.lo)
        stopped = (b.c if j == 0 else b.lo) <= floor + EPS     # the crossing candle: only a close under it
        if outcome == SETUP_OUTCOME_OPEN and stopped:
            outcome, outcome_at = SETUP_OUTCOME_STOP_FIRST, b.t
        elif outcome == SETUP_OUTCOME_OPEN and b.h >= target - EPS:
            outcome, outcome_at = SETUP_OUTCOME_TARGET_FIRST, b.t
    ema9 = ema([b.c for b in bars], SETUPS_EMA_PERIOD)
    tracker = ScoreTracker(entry=entry, stop=floor, target1=target, risk=risk, triggered_at=cross.t,
                           entry_bar_t=cross.t)
    for b, e in zip(bars[i:], ema9[i:], strict=True):
        if tracker.on_bar(b, e):
            break
    return {"entry": round(entry, 4), "stop": round(floor, 4), "risk": risk, "target": target, "outcome": outcome,
            "outcome_at": outcome_at, "bar_r": tracker.bar_r(), "exit_reason": tracker.exit_reason,
            "mfe_r": round((best - entry) / risk, 2), "mae_r": round(min(0.0, worst - entry) / risk, 2)}
