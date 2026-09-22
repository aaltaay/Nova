"""Desk venue routes (ADR 020): ``GET`` / ``POST /api/desk/venue``.

The header pills post here. The venue is ``live`` (IBKR, real money), ``paper``
(Nova's practice account on the live feed) or ``sim`` (the replay playground);
``sim/mode.py`` owns it. A venue change never arms anything -- it disarms
(ADR 018). The legacy ``POST /api/sim {enabled}`` toggle keeps working through
``sim.routes`` for clients that predate this route.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from constants_sim import DESK_VENUE_SCHEMA_VERSION, DESK_VENUES

router = APIRouter(prefix="/api/desk", tags=["desk"])


class DeskVenueRequest(BaseModel):
    venue: str = Field(description="live | paper | sim")


@router.get("/venue")
def get_desk_venue() -> dict:
    """The settled desk venue and the schema version of its cache file."""
    from sim.mode import venue

    return {"venue": venue(), "schema_version": DESK_VENUE_SCHEMA_VERSION}


@router.post("/venue")
def post_desk_venue(body: DeskVenueRequest) -> dict:
    """Settle the desk venue. 400 on anything but live / paper / sim."""
    key = (body.venue or "").strip().lower()
    if key not in DESK_VENUES:
        raise HTTPException(
            status_code=400,
            detail=f"venue must be one of {', '.join(DESK_VENUES)}, not {body.venue!r}",
        )
    from sim.mode import set_venue

    return {"ok": True, "schema_version": DESK_VENUE_SCHEMA_VERSION, **set_venue(key)}
