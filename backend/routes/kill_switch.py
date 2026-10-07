"""Kill switch routes (D-037, ADR 025) -- thin handlers over ``kill_switch``.

Endpoints:
  GET  /api/kill-switch        -- {tripped, reason, ts}
  POST /api/kill-switch        -- trip: latch, then cancel every working order on every venue but
                                  the stops protecting a position (ADR 048); adds {persisted,
                                  sweep: [{venue, cancelled, failed, kept, error, note}],
                                  cancelled_order_ids, failed_cancel_order_ids, kept_order_ids,
                                  receipt_error}
  POST /api/kill-switch/reset  -- clear the latch; adds {persisted}

The trip is async: its cancels go through ``execution.service.execute`` on this loop, the one
every other order runs on (#656: a sync handler ran them under ``asyncio.run``, a second loop
that could not share the door's lock).
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
async def kill_switch_trip() -> dict:
    return await _kill_switch.trip()


@router.post("/reset", dependencies=[Depends(require_auth)])
def kill_switch_reset() -> dict:
    return _kill_switch.reset()
