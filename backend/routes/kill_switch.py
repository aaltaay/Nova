"""Kill switch routes (D-037, ADR 025) -- thin handlers over ``kill_switch``.

Endpoints:
  GET  /api/kill-switch        -- {tripped, reason, ts}
  POST /api/kill-switch        -- trip: latch, then cancel every working order
  POST /api/kill-switch/reset  -- clear the latch
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

import kill_switch as _kill_switch
from auth import require_auth

router = APIRouter(prefix="/api/kill-switch", tags=["kill-switch"])


@router.get("")
def kill_switch_status() -> dict:
    return _kill_switch.status()


@router.post("", dependencies=[Depends(require_auth)])
def kill_switch_trip() -> dict:
    return _kill_switch.trip()


@router.post("/reset", dependencies=[Depends(require_auth)])
def kill_switch_reset() -> dict:
    return _kill_switch.reset()
