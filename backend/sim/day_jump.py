"""Move the Sim clock to another day with nothing loaded (ADR 023).

``POST /api/sim/clock {session_date}``: the Scanner board and the HOD Momo
strip follow the playhead through the leaderboard, so a past day needs no
symbol to be watched. Picking a day means "watch the whole day" (operator
decision, 2026-09-22): any loaded replay -- a historical download or a Session
Record, of that day or another -- is unloaded first, so the clock opens the full
04:00-20:00 session instead of a download's narrow window. Unloading never
deletes: the download or recording stays on disk and reloads at once; the Sim
scratch account starts over, as any unload does. The clock parks paused at
``SIM_DAY_JUMP_PARK_MIN_ET`` so nothing runs off before the operator presses
play. ``None`` returns to today, unloading a replay of another date, and follows
the wall clock again.
"""
from __future__ import annotations

import logging
from datetime import date as date_cls
from datetime import datetime
from typing import Any

from constants_sim import SIM_DAY_JUMP_PARK_MIN_ET, SIM_SESSION_OPEN_HOUR

logger = logging.getLogger(__name__)


def _today_et() -> date_cls:
    from sim.session_clock import ET

    return datetime.now(ET).date()


def _unload(day: str | None, *, same_day_too: bool) -> None:
    """Unload the loaded replay: always when ``same_day_too``, else only one of another date."""
    from sim import replay

    loaded = replay.status_payload()
    loaded_date = loaded.get("replay_date")
    if loaded_date and (same_day_too or loaded_date != day):
        replay.set_replay(None, None)
        logger.info(
            "SIM day: unloaded the %s %s replay to open %s",
            loaded_date, loaded.get("replay_source"), day or "today",
        )


def jump_to_day(day: str | None) -> dict[str, Any]:
    """Re-date the Sim clock. Raises ``ValueError`` for a day the desk cannot open."""
    from sim import session_clock as clock
    from sim import trading_day

    if day is None:
        _unload(_today_et().isoformat(), same_day_too=False)
        clock.set_session_date(None)
        return clock.clear_scrub()
    target = date_cls.fromisoformat(day)
    trading_day.require_supported(target)
    if target > _today_et():
        raise ValueError(f"{day} has not happened yet")
    if not trading_day.is_trading_day(target):
        raise ValueError(f"{day} is not an exchange day")
    _unload(day, same_day_too=True)
    before = clock.now_et()
    clock.set_session_date(day)
    park_second = (SIM_DAY_JUMP_PARK_MIN_ET - SIM_SESSION_OPEN_HOUR * 60) * 60
    clock.scrub_to_second(float(park_second), notify=False)
    if not clock.is_paused():
        clock.set_paused(True)
    clock.notify_moved(before)  # the venue reseeds and unwinds orders placed after the new playhead
    logger.info("SIM day: moved to %s, parked at %s", day, clock.now_et().isoformat())
    return clock.status_payload()
