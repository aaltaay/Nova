"""The operator's auto-record switch on the wire (operator ask 2026-10-14).

Shape: ``architecture/schema/scanner.md``, Auto-record. ``POST /api/auto-record {mode}`` saves the
switch (``auto_record_switch``) and answers the ``auto_record`` status with ``stopped``, the lines
turning it off stopped. The file is written off the loop.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from leaderboard import auto_record, auto_record_switch

logger = logging.getLogger(__name__)
router = APIRouter(tags=["auto-record"])


class AutoRecordSwitchRequest(BaseModel):
    mode: Literal["on", "off_today", "off"]


@router.post("/api/auto-record")
async def post_auto_record(body: AutoRecordSwitchRequest) -> dict:
    try:
        await asyncio.to_thread(auto_record_switch.set_mode, body.mode)
    except auto_record_switch.EnvHoldsOff as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except OSError as exc:
        logger.exception("AUTO-RECORD: could not save the switch")
        raise HTTPException(
            status_code=503,
            detail=f"Nova could not save the switch ({type(exc).__name__}: {exc}); auto-record is unchanged",
        ) from exc
    stopped = await auto_record.turned_off() if body.mode != auto_record_switch.MODE_ON else []
    return {**auto_record.status(), "stopped": stopped}
