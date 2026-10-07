"""Where a show lands and where a move goes (ADR 050): pure, from the day movers row and the Sim's state.

A show parks the playhead (paused) at a moment of the day -- a few minutes before the run or the drop began, on
the high or the low, at the open, or at a time -- and loads the desk's usual window around it, with narrower
windows to fall back on when a busy runner's window is over the Sim's print or quote cap.
"""
from __future__ import annotations

import re
from datetime import date, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from constants_agent_desk import (
    AGENT_AT_ANCHORS,
    AGENT_FALLBACK_WINDOWS_MIN,
    AGENT_PARK_LEAD_SEC,
    AGENT_WINDOW_LEAD_MIN,
    AGENT_WINDOW_MINUTES,
)
from constants_day_movers import DAY_MOVERS_SESSION_END_MIN_ET, DAY_MOVERS_SESSION_START_MIN_ET

ET = ZoneInfo("America/New_York")
_HHMM = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


class PlanError(ValueError):
    """The moment or the day cannot be shown; the message says why in the operator's words."""


def et_ts(day: str, minute_of_day: int) -> int:
    d = date.fromisoformat(day)
    return int(datetime.combine(d, time(minute_of_day // 60, minute_of_day % 60), tzinfo=ET).timestamp())


def et_clock(ts: float, seconds: bool = False) -> str:
    return datetime.fromtimestamp(ts, ET).strftime("%H:%M:%S" if seconds else "%H:%M")


def _minute_of_day(ts: float) -> int:
    at = datetime.fromtimestamp(ts, ET)
    return at.hour * 60 + at.minute


def parse_at(at: str | None) -> str:
    value = (at or "run").strip().lower()
    if value in AGENT_AT_ANCHORS or _HHMM.match(value):
        return value
    raise PlanError(f"at must be one of {', '.join(AGENT_AT_ANCHORS)} or an ET time HH:MM, not {at!r}")


# A run starts at the first +20% mark (else +10%); a stock already there at its first print starts at its next leg.
_RUN_MARKS = (("up20_ts", 20), ("up10_ts", 10))
_RUN_NEXT_LEGS = (("up50_ts", 50), ("up100_ts", 100), ("up300_ts", 300))
_DROP_MARKS = (("down20_ts", 20), ("down10_ts", 10))
_DROP_NEXT_LEGS = (("down50_ts", 50),)


def _move_anchor(row: dict[str, Any], marks, legs, sign: str) -> tuple[int, str] | None:
    """The first mark reached after the stock's first print -- a mark it already stood at when it first traded is
    where it opened, not where it moved -- else its next leg."""
    first = row.get("first_ts")

    def usable(column: str) -> bool:
        return row.get(column) is not None and (first is None or int(row[column]) >= int(first) + AGENT_PARK_LEAD_SEC)

    for column, pct in marks:
        if usable(column):
            ts = int(row[column])
            return ts, f"5 min before it first traded {sign}{pct}% ({et_clock(ts)})"
    for column, pct in legs:
        if usable(column):
            ts = int(row[column])
            return ts, f"5 min before it first traded {sign}{pct}% ({et_clock(ts)}), already moving at its first print"
    return None


def anchor(day: str, at: str, row: dict[str, Any] | None) -> tuple[int, int, str]:
    """``(anchor_ts, lead_sec, words)``: the moment ``at`` names on ``day``, how long before it the playhead parks,
    and where that is in words. The index row answers the run, the drop, the high and the low."""
    if m := _HHMM.match(at):
        return et_ts(day, int(m.group(1)) * 60 + int(m.group(2))), 0, f"at {at}"
    if at == "open":
        return et_ts(day, 9 * 60 + 30), 0, "at the 09:30 open"
    if at == "premarket":
        return et_ts(day, DAY_MOVERS_SESSION_START_MIN_ET), 0, "at 04:00, the premarket open"
    if row is None:
        raise PlanError(f"{day} is not in the movers index for this stock: name a time (HH:MM), open or premarket")
    if at in ("run", "drop"):
        found = (_move_anchor(row, _RUN_MARKS, _RUN_NEXT_LEGS, "+") if at == "run"
                 else _move_anchor(row, _DROP_MARKS, _DROP_NEXT_LEGS, "-"))
        if found is not None:
            return found[0], AGENT_PARK_LEAD_SEC, found[1]
        at = "high" if at == "run" else "low"        # no later move: the day's own extreme
    column = "day_high_ts" if at == "high" else "day_low_ts"
    if row.get(column) is None:
        raise PlanError(f"no {at} on file for {row.get('symbol')} on {day}: name a time (HH:MM) instead")
    ts = int(row[column])
    return ts, 0, f"at the {at} ({et_clock(ts)})"


def anchor_ts(day: str, at: str, row: dict[str, Any] | None) -> int:
    return anchor(day, at, row)[0]


def _clamp_window(start_min: int, length: int) -> tuple[int, int]:
    first, last = DAY_MOVERS_SESSION_START_MIN_ET, DAY_MOVERS_SESSION_END_MIN_ET
    start = max(first, start_min)
    end = min(last, start + length)
    start = max(first, end - length)
    return start, end


def window_around(day: str, park_ts: int, length: int, lead_min: int) -> dict[str, Any]:
    """``length`` minutes from the quarter hour (five minutes for a short window) ``lead_min`` before the park:
    ``{start, end}`` as ET ``HH:MM`` (what ``/api/sim/history/select`` takes) and ``start_ts`` / ``end_ts``."""
    step = 15 if length >= 60 else 5
    start_min = _minute_of_day(park_ts) - lead_min
    start_min -= start_min % step
    start, end = _clamp_window(start_min, length)
    return {"start": f"{start // 60:02d}:{start % 60:02d}", "end": f"{end // 60:02d}:{end % 60:02d}",
            "start_ts": et_ts(day, start), "end_ts": et_ts(day, end)}


def window_bounds(day: str, window: dict[str, str]) -> tuple[int, int]:
    h1, m1 = (int(x) for x in window["start"].split(":"))
    h2, m2 = (int(x) for x in window["end"].split(":"))
    return et_ts(day, h1 * 60 + m1), et_ts(day, h2 * 60 + m2)


def windows_for(day: str, park_ts: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    main = window_around(day, park_ts, AGENT_WINDOW_MINUTES, AGENT_WINDOW_LEAD_MIN)
    fallbacks = []
    for minutes in AGENT_FALLBACK_WINDOWS_MIN:
        lead = AGENT_WINDOW_LEAD_MIN if minutes >= 60 else 5
        candidate = window_around(day, park_ts, minutes, lead)
        if candidate != main and candidate not in fallbacks:
            fallbacks.append(candidate)
    return main, fallbacks


def plan_show(symbol: str, day: str, at: str | None, row: dict[str, Any] | None, *, today: str) -> dict[str, Any]:
    """The window to load and the moment to park, for a past session only (a day not over cannot replay)."""
    try:
        date.fromisoformat(day)
    except ValueError:
        raise PlanError("date must be YYYY-MM-DD") from None
    if day >= today:
        raise PlanError(f"{day} is not over yet: the Sim replays past days from the files")
    which = parse_at(at)
    moment, lead, words = anchor(day, which, row)
    park = max(et_ts(day, DAY_MOVERS_SESSION_START_MIN_ET),
               min(moment - lead, et_ts(day, DAY_MOVERS_SESSION_END_MIN_ET) - 60))
    window, fallbacks = windows_for(day, park)
    return {
        "symbol": symbol.upper(), "date": day, "at": which,
        "anchor_et": et_clock(moment), "park_et": et_clock(park, seconds=True), "park_ts": park,
        "park_words": words, "window": window, "fallback_windows": fallbacks,
    }


def plan_move(loaded: dict[str, Any], playhead_ts: float, *, to: str | None, by_min: float | None,
              paused: bool | None, row: dict[str, Any] | None) -> dict[str, Any]:
    """Where the playhead goes in the loaded day, and the window to load when that is outside the loaded one."""
    day, symbol = str(loaded["date"]), str(loaded["symbol"]).upper()
    if to is None and by_min is None and paused is None:
        raise PlanError("say where to move: to (an anchor or HH:MM), by_min, or paused")
    target: int | None = None
    words: str | None = None
    if to is not None:
        moment, lead, words = anchor(day, parse_at(to), row)
        target = moment - lead
    elif by_min is not None:
        target = int(playhead_ts + float(by_min) * 60)
        words = f"{abs(float(by_min)):g} min {'forward' if float(by_min) >= 0 else 'back'}"
    start, end = window_bounds(day, {"start": str(loaded["start"]), "end": str(loaded["end"])})
    plan: dict[str, Any] = {"symbol": symbol, "date": day, "paused": paused, "target_ts": None, "target_et": None,
                            "target_words": words, "loaded_start_ts": start, "window": None, "fallback_windows": []}
    if target is None:
        return plan
    first, last = et_ts(day, DAY_MOVERS_SESSION_START_MIN_ET), et_ts(day, DAY_MOVERS_SESSION_END_MIN_ET) - 1
    target = max(first, min(target, last))
    plan.update(target_ts=target, target_et=et_clock(target, seconds=True))
    if not start <= target < end:
        plan["window"], plan["fallback_windows"] = windows_for(day, target)
    return plan
