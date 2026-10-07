"""What the desk shows now, for an agent (ADR 050): the venue, the Sim's day and playhead, what is loaded, the
page and symbol in front, and whether a main desk window is listening for commands. Memory reads only.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from constants_agent_desk import AGENT_DESK_SCHEMA_VERSION

logger = logging.getLogger(__name__)
ET = ZoneInfo("America/New_York")


def loaded_window() -> dict[str, Any] | None:
    """The Sim's loaded historical window: ``{source, symbol, date, start, end}``, or ``None``."""
    from sim import history_playback

    spec = history_playback.status()
    if not spec:
        return None
    return {"source": spec.get("source") or "ibkr", "symbol": spec.get("symbol"), "date": spec.get("date"),
            "start": spec.get("start"), "end": spec.get("end")}


def sim_state() -> dict[str, Any] | None:
    """The Sim clock, when the desk is on the Sim."""
    from sim import session_clock
    from sim.mode import is_sim_mode

    if not is_sim_mode():
        return None
    clock = session_clock.status_payload()
    playhead = session_clock.now_et()
    return {
        "session_date": clock.get("session_date"), "playhead_et": playhead.astimezone(ET).strftime("%H:%M:%S"),
        "playhead_ts": playhead.timestamp(), "paused": clock.get("paused"), "live_edge": clock.get("live_edge"),
        "loaded": loaded_window(),
    }


def focus() -> dict[str, Any] | None:
    from sensors import focus_store

    answer = focus_store.resolve()
    if answer.get("window_id") is None:
        return None
    return {key: answer.get(key) for key in ("page", "symbol", "window_id", "nova_in_front")}


def desk_state(board, at_stake: dict[str, Any] | None = None) -> dict[str, Any]:
    from sim.mode import venue

    current = venue()
    if at_stake is None:
        from agent_desk.safety import at_stake as check

        at_stake = check(current)
    sim = sim_state()
    return {
        "schema_version": AGENT_DESK_SCHEMA_VERSION,
        "generated_at": datetime.now(ET).isoformat(),
        "venue": current,
        "live_edge": None if sim is None else sim.get("live_edge"),
        "sim": sim,
        "focus": focus(),
        "listening": board.listening(),
        "at_stake": at_stake,
    }
