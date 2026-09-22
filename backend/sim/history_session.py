"""The replayed session's own figures for the historical quote card (QA W7, 2026-09-22).

A downloaded window is rarely the whole day. The snapshot's ``open`` / ``high``
/ ``low`` / ``volume`` count from the window's first print, so a 13:00-13:30
window reported its 13:00 print as the day's open: GRML's Gap% read +223.51%
against the real +156.49%. The quote card needs the *session's* figures, and
where the download cannot give them it must say so rather than pass the
window's off as the day's.

``session_open`` is the regular session's opening print (09:30 ET): the first
reported print at or after 09:30:00 inside the downloaded range that covers
09:30:00 -- or, when that stretch was not downloaded, the stored 1-minute bar
that starts at 09:30 (the bar store the charts fill). ``stats_scope`` is
``"session"`` only when the figures really are the day's so far: the window
starts at the session start (04:00 ET) and the playhead's trades are unbroken
from there; otherwise ``"window"``.
"""
from __future__ import annotations

import bisect
import logging
from datetime import date as _date, datetime, time
from typing import Any, Sequence

from constants_sim import SIM_HISTORY_SESSION_OPEN_HHMM, SIM_HISTORY_SESSION_START_HHMM
from sim import history_coverage as coverage
from sim import history_store as store

logger = logging.getLogger(__name__)

SCOPE_SESSION = "session"
SCOPE_WINDOW = "window"


def et_ts(day: str, hhmm: tuple[int, int]) -> float:
    """Epoch of ``hhmm`` ET on the ISO date ``day``."""
    return datetime.combine(_date.fromisoformat(day), time(*hhmm), store.ET).timestamp()


def _stored_open_bar(symbol: str, open_ts: float) -> tuple[float, float] | None:
    """The stored 1-minute bar that starts at the open, as ``(ts, open price)``."""
    try:
        from bars_store import read

        rows = (read(symbol, "1Min", 1, from_ts=open_ts, through_ts=open_ts) or {}).get("bars") or []
    except Exception:
        logger.warning("Historical replay: stored 09:30 bar unreadable for %s", symbol, exc_info=True)
        return None
    for row in rows:
        price = row.get("o")
        try:
            return float(open_ts), float(price)
        except (TypeError, ValueError):
            continue
    return None


def session_open(
    spec: dict[str, Any],
    eligible: Sequence[dict[str, Any]],
    eligible_keys: Sequence[int],
    ranges: Sequence[Sequence[int]],
) -> tuple[float, float] | None:
    """``(ts, price)`` of the regular session's opening print, or None when it is not known."""
    open_ts = et_ts(spec["date"], SIM_HISTORY_SESSION_OPEN_HHMM)
    covering = coverage.range_at(ranges or [], int(open_ts))
    if covering is not None:
        i = bisect.bisect_left(eligible_keys, open_ts)
        # Only a print inside the stretch that covers 09:30:00 is the open; a
        # later range's first print could follow trades nobody downloaded.
        if i < len(eligible) and eligible_keys[i] < covering[1]:
            return float(eligible_keys[i]), float(eligible[i]["price"])
    return _stored_open_bar(str(spec["symbol"]), open_ts)


def stats_scope(spec: dict[str, Any], source: str, in_range: Sequence[int] | None) -> str:
    """``"session"`` when volume / high / low are the day's so far, else ``"window"``."""
    start = float(spec["start_ts"])
    if start > et_ts(spec["date"], SIM_HISTORY_SESSION_START_HHMM):
        return SCOPE_WINDOW
    if source != "trades" or in_range is None:
        return SCOPE_WINDOW
    # Coverage ranges are merged, so the playhead's range reaching back to the
    # window start means every trade from the session start is in the tally.
    return SCOPE_SESSION if float(in_range[0]) <= start else SCOPE_WINDOW
