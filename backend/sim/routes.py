"""In-app Sim toggle -- header Paper / Live / Sim posts here."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from sim.mode import set_sim_mode, status_payload

router = APIRouter(tags=["sim"])


class SimToggleRequest(BaseModel):
    enabled: bool
    persist: bool = False


class SimReplayRequest(BaseModel):
    date: str | None = Field(default=None, description="ET session date YYYY-MM-DD, or null for synthetic")
    symbol: str | None = Field(default=None, description="Captured ticker, or null for synthetic SIM1")


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
    """Scrub sim session time. Body: {minute_from_open: int} or {follow_wall: true}."""
    from sim import session_clock as _clock
    from sim import replay as _replay
    from sim.mode import is_sim_mode

    if "paused" in body:
        if not is_sim_mode():
            raise HTTPException(status_code=409, detail="Playback controls require Sim mode")
        if not isinstance(body["paused"], bool):
            raise HTTPException(status_code=422, detail="paused must be a boolean")
        payload = _clock.set_paused(body["paused"])
    elif body.get("follow_wall"):
        payload = _clock.clear_scrub()
    else:
        minute = int(body.get("minute_from_open", 0))
        payload = _clock.scrub_to_minute(minute)
    return {"sim": is_sim_mode(), **payload, **_replay.status_payload()}


@router.get("/api/sim/replay")
def get_sim_replay() -> dict:
    from sim import replay as _replay
    from sim.mode import is_sim_mode

    return {"sim": is_sim_mode(), **_replay.status_payload()}


@router.post("/api/sim/replay")
def post_sim_replay(body: SimReplayRequest) -> dict:
    """Select capture day+ticker for Sim, or clear both for synthetic SIM1."""
    from sim import replay as _replay
    from sim.mode import is_sim_mode

    return {"sim": is_sim_mode(), **_replay.set_replay(body.date, body.symbol)}
