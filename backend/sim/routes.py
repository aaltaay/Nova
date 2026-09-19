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
