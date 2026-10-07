"""Which auto-record window is open (ADR 023, ADR 041; operator ask 2026-09-30).

Two windows, on exchange days:

* **setups** -- whenever any setup's arming window is open: each setup with a
  scanner, its template in play's ``setup_templates.windows.arming_window``
  (07:00-11:30 ET by default, red to green 09:30-10:30, the 5-minute flat top
  07:00-15:30). Red to green triggered 32 times and was never at go, partly
  because no line was held after 10:00.
* **leaders** -- 07:00-10:00 ET, as the operator set it (2026-09-22).

``window_state`` answers both, and ``window_label`` says which is open in words --
``/api/ibkr/status`` ``auto_record.window`` / ``windows``. Templates that cannot be
read fall back to the pre-registered arming windows and say so (``setups.error``),
never a silent guess. Reads the template store (in memory once loaded); no network.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from constants_leaderboard import LEADERBOARD_AUTO_RECORD_END_MIN_ET, LEADERBOARD_AUTO_RECORD_START_MIN_ET
from leaderboard.recorder import exchange_day
from leaderboard.rows import ET

logger = logging.getLogger(__name__)

# Which window is open (``window_state(...)["open"]``).
OPEN_BOTH, OPEN_SETUPS, OPEN_LEADERS, OPEN_NONE = "setups_and_leaders", "setups", "leaders", "none"


def _hm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _minutes(text: str) -> int:
    hour, minute = text.split(":")
    return int(hour) * 60 + int(minute)


def leaders_open(now: float) -> bool:
    """The leaders' window: 07:00-10:00 ET on an exchange day."""
    when = datetime.fromtimestamp(now, ET)
    minutes = when.hour * 60 + when.minute
    return exchange_day(when) and LEADERBOARD_AUTO_RECORD_START_MIN_ET <= minutes < LEADERBOARD_AUTO_RECORD_END_MIN_ET


def _windows_of(values_of) -> list[tuple[str, str, str]]:
    from constants_bot import BOT_SCANNER_SETUPS
    from setup_templates import windows

    out: list[tuple[str, str, str]] = []
    for setup in BOT_SCANNER_SETUPS:
        found = windows.arming_window(setup, values_of(setup))
        if found is not None:
            out.append((setup, found[0], found[1]))
    return out


def arming_windows() -> list[tuple[str, str, str]]:
    """``(setup, start, end)`` ET of every setup with a scanner: its template in play's arming window."""
    from setup_templates.store import get_store

    store = get_store()
    return _windows_of(lambda setup: store.in_play(setup).values)


def _read_arming_windows() -> tuple[list[tuple[str, str, str]], str | None]:
    """The templates in play's arming windows, or -- when they cannot be read -- the
    pre-registered ones, with the reason."""
    try:
        return arming_windows(), None
    except Exception as exc:
        from setup_templates import catalogue

        logger.warning("AUTO-RECORD: could not read the templates in play's arming windows", exc_info=True)
        return _windows_of(catalogue.defaults), (
            f"the templates in play could not be read ({type(exc).__name__}: {exc}); using the pre-registered "
            "arming windows")


def window_state(now: float) -> dict[str, Any]:
    """Which window is open at ``now``: ``{open, setups: {open, start, end, by_setup: [{setup, start,
    end, open}], error}, leaders: {open, start, end}}`` -- ``setups.start`` / ``end`` span every
    setup's arming window."""
    when = datetime.fromtimestamp(now, ET)
    minute = when.hour * 60 + when.minute
    trading = exchange_day(when)
    found, error = _read_arming_windows()
    by_setup = [{"setup": setup, "start": start, "end": end,
                 "open": trading and _minutes(start) <= minute < _minutes(end)} for setup, start, end in found]
    setups = {"open": any(w["open"] for w in by_setup),
              "start": min((w["start"] for w in by_setup), key=_minutes, default=None),
              "end": max((w["end"] for w in by_setup), key=_minutes, default=None),
              "by_setup": by_setup, "error": error}
    leaders = {"open": leaders_open(now), "start": _hm(LEADERBOARD_AUTO_RECORD_START_MIN_ET),
               "end": _hm(LEADERBOARD_AUTO_RECORD_END_MIN_ET)}
    is_open = (OPEN_BOTH if setups["open"] and leaders["open"] else OPEN_SETUPS if setups["open"]
               else OPEN_LEADERS if leaders["open"] else OPEN_NONE)
    return {"open": is_open, "setups": setups, "leaders": leaders}


def window_label(state: dict[str, Any]) -> str:
    """Which window is open, in words; outside both, the windows themselves (the checklist's
    ``auto_record`` row reads "outside <label>")."""
    s, ld = state["setups"], state["leaders"]
    setups = f"setups {s['start']}-{s['end']} ET" if s.get("start") else "setups (no arming window)"
    leaders = f"leaders {ld['start']}-{ld['end']} ET"
    if state["open"] == OPEN_BOTH:
        return f"setups and leaders ({setups}, {leaders})"
    if state["open"] == OPEN_SETUPS:
        return f"setups only ({setups}; {leaders})"
    if state["open"] == OPEN_LEADERS:
        return f"leaders only ({leaders}; {setups})"
    return f"its windows ({setups}, {leaders})"
