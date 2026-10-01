"""The bot's entry window sits inside its setup's arming window (operator ask 2026-09-30). Pure.

A setup arms -- and triggers -- only inside its arming window (``session_start`` to
``entry_cutoff``; red to green: the open to ``r2g_cutoff``), so a bot window that
reaches outside it promised entries that could never come. Two rules, one per path:

- a write (``setup_templates.store``: create, update) whose bot window reaches
  outside the arming window is refused -- ``problem`` names the field and both
  windows;
- a template read from disk (or the defaults) whose bot window reaches outside is
  clipped to the part inside -- ``clip`` -- and says so: ``Template.bot_window`` is
  ``{start, end, clipped, empty, arming: {start, end}, stored: {start, end} | null,
  note}``. A window wholly outside is empty (``start == end``): the bot never enters
  on that template until the operator sets one inside.

Windows are half-open, ``[start, end)``, on the venue's clock -- the same reading as
``setup_scanner.detectors.window_state`` and ``bot.entry_rules.in_window``.
"""
from __future__ import annotations

import re
from typing import Any

from constants_bot import (
    BOT_SETUP_BULL_FLAG,
    BOT_SETUP_FIRST_PULLBACK,
    BOT_SETUP_FLAT_TOP,
    BOT_SETUP_RED_TO_GREEN,
)
from setup_templates.catalogue import Problem

BOT_START, BOT_END = "bot_window_start", "bot_window_end"
# Each setup with a scanner: the keys of its arming window (``detectors.window`` reads the same).
ARMING_KEYS: dict[str, tuple[str, str]] = {
    BOT_SETUP_FIRST_PULLBACK: ("session_start", "entry_cutoff"),
    BOT_SETUP_BULL_FLAG: ("session_start", "entry_cutoff"),
    BOT_SETUP_FLAT_TOP: ("session_start", "entry_cutoff"),
    BOT_SETUP_RED_TO_GREEN: ("session_start", "r2g_cutoff"),
}
_TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


def _time(value: Any) -> str | None:
    text = str(value).strip() if isinstance(value, str) else ""
    return text if _TIME_RE.match(text) else None


def _m(text: str) -> int:
    hour, minute = text.split(":")
    return int(hour) * 60 + int(minute)


def arming_window(setup_id: str, values: dict[str, Any]) -> tuple[str, str] | None:
    """``(start, end)`` ET when the setup may arm and trigger; ``None`` for a setup without a
    scanner, or values that hold no readable window."""
    keys = ARMING_KEYS.get(setup_id)
    if keys is None:
        return None
    start, end = _time(values.get(keys[0])), _time(values.get(keys[1]))
    if start is None or end is None or _m(start) >= _m(end):
        return None
    return start, end


def _bot_window(values: dict[str, Any]) -> tuple[str, str] | None:
    start, end = _time(values.get(BOT_START)), _time(values.get(BOT_END))
    if start is None or end is None or _m(start) >= _m(end):
        return None
    return start, end


def problem(setup_id: str, values: dict[str, Any]) -> Problem | None:
    """Why a written bot window is refused (it reaches outside the arming window), else ``None``."""
    arming, bot = arming_window(setup_id, values), _bot_window(values)
    if arming is None or bot is None:
        return None
    (a0, a1), (s, e) = arming, bot
    both = f"the bot window {s}-{e} must sit inside the arming window {a0}-{a1}"
    if _m(s) < _m(a0):
        return Problem(f"Bot entries from (bot_window_start) {s} is before the setup arms at {a0}: {both}", BOT_START)
    if _m(e) > _m(a1):
        return Problem(f"Bot entries until (bot_window_end) {e} is after the setup stops arming at {a1}: {both}",
                       BOT_END)
    return None


def clip(setup_id: str, values: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """``(values with the bot window inside the arming window, the bot window as read)``.

    The second is ``None`` for a setup without a bot window (no scanner) or values whose
    windows cannot be read (a template that no longer validates, which never runs)."""
    out = dict(values)
    arming, bot = arming_window(setup_id, values), _bot_window(values)
    if arming is None or bot is None:
        return out, None
    (a0, a1), (s, e) = arming, bot
    lo = s if _m(s) >= _m(a0) else a0
    hi = e if _m(e) <= _m(a1) else a1
    clipped = (lo, hi) != (s, e)
    empty = _m(lo) >= _m(hi)
    if empty:   # wholly outside: no entry ever, at a time inside the arming window
        lo = hi = a1 if _m(s) >= _m(a1) else a0
    out[BOT_START], out[BOT_END] = lo, hi
    note = None
    if empty:
        note = (f"The saved bot window {s}-{e} lies outside the arming window {a0}-{a1}, so the bot never enters "
                f"on this template. Set a bot window inside {a0}-{a1}.")
    elif clipped:
        note = (f"The saved bot window {s}-{e} reaches outside the arming window {a0}-{a1}; the bot enters only "
                f"{lo}-{hi}. Save the template to keep that, or set a window inside {a0}-{a1}.")
    return out, {"start": lo, "end": hi, "clipped": clipped, "empty": empty, "arming": {"start": a0, "end": a1},
                 "stored": {"start": s, "end": e} if clipped else None, "note": note}
