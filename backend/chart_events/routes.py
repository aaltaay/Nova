"""``GET /api/chart-events/{symbol}``: the earnings reports and splits the daily charts mark.

Answers from the reader's memory at once (``reader.py``). Events are cut at the desk's clock: on a Sim
replay, only what was filed or took effect before the replayed day, and a split that takes effect on it (at
its open); a report filed on the replayed day is left out, since SEC's time of day is not read
(``earnings.py``). Live, everything SEC and Yahoo list.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException

from chart_events import reader
from sim.replay_playhead import replay_playhead

router = APIRouter(tags=["chart_events"])
ET = ZoneInfo("America/New_York")
_PARTS = ("earnings", "splits")


def _symbol(raw: str) -> str:
    sym = (raw or "").strip().upper()
    if not sym or len(sym) > 12:
        raise HTTPException(400, "a symbol, up to 12 characters")
    return sym


def known_by(event: dict[str, Any], through: datetime) -> bool:
    """Whether the desk at ``through`` (Eastern) could know ``event``: its day before the desk's, or a split
    on the desk's day (it takes effect at the open)."""
    day = through.date().isoformat()
    return event["day"] < day or (event["day"] == day and event["kind"] == "split")


def answer(view: dict[str, Any], playhead: float | None) -> dict[str, Any]:
    """The reader's view as the route's answer, each part's events cut at the replay's playhead."""
    out = {k: v for k, v in view.items() if k not in _PARTS}
    through = datetime.fromtimestamp(playhead, ET) if playhead is not None else None
    out["replay"] = through is not None
    out["through"] = through.isoformat() if through else None
    for part in _PARTS:
        held = view.get(part)
        if held is None:
            out[part] = None
            continue
        events = held.get("events") or []
        out[part] = {**held, "events": [e for e in events if through is None or known_by(e, through)]}
    return out


@router.get("/api/chart-events/{symbol}")
def get_chart_events(symbol: str) -> dict[str, Any]:
    return answer(reader.view(_symbol(symbol)), replay_playhead())
