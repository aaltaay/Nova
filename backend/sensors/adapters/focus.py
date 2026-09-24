"""Sensor 19: the operator's focus (ADR 033) -- which window, page and symbol, and where."""
from __future__ import annotations

import logging
from typing import Any

from constants_sensors import FOCUS_NOTE, FOCUS_SCHEMA_VERSION, FOCUS_STALE_SEC
from sensors import focus_store
from sensors.envelope import build_envelope

logger = logging.getLogger(__name__)


def _desk() -> dict[str, Any]:
    """The desk's venue beside the focus: a Sim tab off the live edge shows a replay, not now."""
    try:
        from sim import mode

        venue = mode.venue()
        live_edge = None
        if venue == "sim":
            from sim import session_clock

            live_edge = bool(session_clock.live_edge())
        return {"venue": venue, "live_edge": live_edge}
    except Exception:
        logger.warning("focus sensor: could not read the desk venue", exc_info=True)
        return {"venue": None, "live_edge": None}


def read_focus() -> dict[str, Any]:
    answer = focus_store.resolve()
    data = {"schema_version": FOCUS_SCHEMA_VERSION, **answer, **_desk(), "note": FOCUS_NOTE}
    error = None
    if not answer["windows"]:
        error = f"No Nova window has reported its focus in the last {FOCUS_STALE_SEC:.0f} s."
    return build_envelope(sensor="focus", status="live", data=data, error=error)
