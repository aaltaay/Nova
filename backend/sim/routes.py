"""In-app Sim toggle -- header Paper / Live / Sim posts here."""
from __future__ import annotations

import math

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from sim.history_routes import router as history_router
from sim.mode import set_sim_mode, status_payload

router = APIRouter(tags=["sim"])
router.include_router(history_router)


class SimToggleRequest(BaseModel):
    enabled: bool
    persist: bool = False


class SimReplayRequest(BaseModel):
    date: str | None = Field(default=None, description="ET session date YYYY-MM-DD, or null to unload the capture")
    symbol: str | None = Field(default=None, description="Captured ticker, or null to unload the capture")


@router.get("/api/sim")
def get_sim() -> dict:
    from sim import replay as _replay

    return {**status_payload(), **_replay.status_payload()}


@router.post("/api/sim")
def post_sim(body: SimToggleRequest) -> dict:
    from sim import replay as _replay

    return {**set_sim_mode(body.enabled, persist=body.persist), **_replay.status_payload()}


@router.get("/api/sim/clock")
def get_sim_clock() -> dict:
    from sim import session_clock as _clock
    from sim import replay as _replay
    from sim.mode import is_sim_mode

    return {"sim": is_sim_mode(), **_clock.status_payload(), **_replay.status_payload()}


@router.post("/api/sim/clock")
def post_sim_clock(body: dict) -> dict:
    """Scrub sim session time. Body: {minute_from_open: int} or {follow_wall: true}.

    ``symbol`` (optional) names the tab the operator scrubbed from: a move
    that leaves the live edge with nothing loaded selects that symbol's
    Session Record for today underneath the playhead (``sim.live_edge``).
    """
    from sim import live_edge as _edge
    from sim import session_clock as _clock
    from sim import replay as _replay
    from sim.mode import is_sim_mode

    was_edge = is_sim_mode() and _clock.live_edge()
    symbol = body.get("symbol")
    if "paused" in body:
        if not is_sim_mode():
            raise HTTPException(status_code=409, detail="Playback controls require Sim mode")
        if not isinstance(body["paused"], bool):
            raise HTTPException(status_code=422, detail="paused must be a boolean")
        payload = _clock.set_paused(body["paused"])
    elif "second_from_open" in body:
        second = body["second_from_open"]
        if isinstance(second, bool) or not isinstance(second, (int, float)) or not math.isfinite(second):
            raise HTTPException(status_code=422, detail="second_from_open must be a finite number")
        payload = _clock.scrub_to_second(float(second))
    elif body.get("follow_wall"):
        payload = _clock.clear_scrub()
    else:
        minute = int(body.get("minute_from_open", 0))
        payload = _clock.scrub_to_minute(minute)
    if "paused" not in body:
        # The playhead moved: a running download of this window fetches there next.
        from sim import history_download
        history_download.follow_playhead(_clock.now_et().timestamp())
    if _edge.select_recording_after_leaving(symbol if isinstance(symbol, str) else None, was_edge=was_edge):
        payload = _clock.status_payload()
    return {"sim": is_sim_mode(), **payload, **_replay.status_payload()}


@router.get("/api/sim/replay")
def get_sim_replay() -> dict:
    from sim import replay as _replay
    from sim.mode import is_sim_mode

    return {"sim": is_sim_mode(), **_replay.status_payload()}


@router.post("/api/sim/replay")
def post_sim_replay(body: SimReplayRequest) -> dict:
    """Select capture day+ticker for Sim, or clear both to unload it."""
    from sim import replay as _replay
    from sim.mode import is_sim_mode

    return {"sim": is_sim_mode(), **_replay.set_replay(body.date, body.symbol)}
