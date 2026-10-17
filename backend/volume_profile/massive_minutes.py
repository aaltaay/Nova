"""A past session's 1-minute bars from the operator's Massive files: yesterday's profile on a Massive Sim replay
(ADR 058 amendment 2026-10-17).

Read through the Sim's own reader (``sim.massive_files``): that day's ``minute_aggs_v1`` file, the ticker's rows as
Massive wrote them -- as traded, never split-adjusted, like the replay itself. A file without its seek index is streamed
from the start, which can take seconds to minutes for a ticker late in the alphabet: a blocking read, run in a worker
thread while the desk is told the profile is ``filling``.
"""
from __future__ import annotations

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from constants_volume_profile import VP_RTH_CLOSE_MIN, VP_RTH_OPEN_MIN
from volume_profile.profile import Bar

_ET = ZoneInfo("America/New_York")


def _at(day: date, minute: int) -> float:
    return datetime.combine(day, time(minute // 60, minute % 60), tzinfo=_ET).timestamp()


def session_minutes(symbol: str, day: date) -> list[Bar] | None:
    """``day``'s 09:30-16:00 ET 1-minute bars for ``symbol``, oldest first; None when that day's file is not on disk."""
    from constants_sim import SIM_MASSIVE_MINUTES
    from sim import massive_files

    path = massive_files.day_file(SIM_MASSIVE_MINUTES, day.isoformat())
    if path is None:
        return None
    start, end = _at(day, VP_RTH_OPEN_MIN), _at(day, VP_RTH_CLOSE_MIN)
    out: list[Bar] = []
    for bar in massive_files.rows(path, symbol.strip().upper(), massive_files.minute):
        t = massive_files.minute_start(bar)
        if start <= t < end:
            out.append(Bar(t=t, o=bar["o"], h=bar["h"], l=bar["l"], c=bar["c"], v=bar["v"]))
    return out
