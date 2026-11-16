"""The three lanes on the wire: ``GET /api/ibkr/lanes`` and ``/api/ibkr/status`` ``lanes`` (ADR 071).

Shape: ``architecture/schema/market-data.md`` "Three lanes". Memory reads only, safe on the loop.
"""
from __future__ import annotations

import logging
import time
from typing import Any

from line_lanes import bots, lanes, recording
from line_lanes.constants_lanes import LANES_SCHEMA_VERSION
from line_lanes.table import BOTS, CLAUDE, YOU

logger = logging.getLogger(__name__)


def _lane(owner: str, recorded: set[str]) -> dict[str, Any]:
    sym = lanes.table().on(owner)
    up = lanes.lines_up(sym) if sym else {lanes.DEPTH: False, lanes.TAPE: False}
    return {"symbol": sym, "since": lanes.since(owner), "depth": up[lanes.DEPTH], "tape": up[lanes.TAPE],
            "recording": bool(sym) and sym in recorded, "error": lanes.error(sym) if sym else None}


def _tape_capacity() -> dict[str, Any] | None:
    try:
        from ibkr import tape_admission

        return tape_admission.view()
    except Exception:
        logger.exception("LANES: the tape admission could not be read")
        return None


def view(now: float | None = None) -> dict[str, Any]:
    from capture.mode import capture_symbols

    ts = time.time() if now is None else float(now)
    rec = recording.status(ts)
    recorded = set(capture_symbols())
    return {
        "schema_version": LANES_SCHEMA_VERSION,
        "generated_at": ts,
        "you": _lane(YOU, recorded),
        "claude": _lane(CLAUDE, recorded),
        "bots": {**_lane(BOTS, recorded), **bots.status()},
        "tape_capacity": _tape_capacity(),
        "recording_error": rec["last_error"],
    }


def recording_switch(now: float | None = None) -> dict[str, Any]:
    """The recording switch (``auto-record-switch.json``): ``{mode, source, day, until, error}``."""
    return recording.status(now)["switch"]
