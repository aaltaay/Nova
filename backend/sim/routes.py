"""In-app Sim toggle -- header Paper / Live / Sim posts here."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from sim.mode import set_sim_mode, status_payload

router = APIRouter(tags=["sim"])


class SimToggleRequest(BaseModel):
    enabled: bool
    persist: bool = False


@router.get("/api/sim")
def get_sim() -> dict:
    return status_payload()


@router.post("/api/sim")
def post_sim(body: SimToggleRequest) -> dict:
    return set_sim_mode(body.enabled, persist=body.persist)

@router.get("/api/sim/clock")
def get_sim_clock() -> dict:
    from sim import session_clock as _clock
    from sim.mode import is_sim_mode

    return {"sim": is_sim_mode(), **_clock.status_payload()}


@router.post("/api/sim/clock")
def post_sim_clock(body: dict) -> dict:
    """Scrub sim session time. Body: {minute_from_open: int} or {follow_wall: true}."""
    from sim import session_clock as _clock
    from sim.mode import is_sim_mode

    if body.get("follow_wall"):
        payload = _clock.clear_scrub()
    else:
        minute = int(body.get("minute_from_open", 0))
        payload = _clock.scrub_to_minute(minute)
    return {"sim": is_sim_mode(), **payload}
