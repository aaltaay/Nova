"""The operator's recording switch on the wire (operator ask 2026-10-14; ADR 071).

Shape: ``architecture/schema/scanner.md``, "The recording switch". ``POST /api/auto-record {mode}`` saves the switch
(``auto_record_switch``, its file and route kept under their names so the saved file still reads) and answers
``{lanes, recording_switch, stopped}``: ``stopped`` lists the lanes' recordings turning it off ended (planned,
``reason: "lane"``). It never touches a recording the operator started, nor a lane's lines. The file is written off
the loop.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from leaderboard import auto_record_switch

logger = logging.getLogger(__name__)
router = APIRouter(tags=["auto-record"])


class AutoRecordSwitchRequest(BaseModel):
    mode: Literal["on", "off_today", "off"]


@router.post("/api/auto-record")
async def post_auto_record(body: AutoRecordSwitchRequest) -> dict:
    from line_lanes import recording, view

    try:
        await asyncio.to_thread(auto_record_switch.set_mode, body.mode)
    except auto_record_switch.EnvHoldsOff as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except OSError as exc:
        logger.exception("RECORDING: could not save the switch")
        raise HTTPException(
            status_code=503,
            detail=f"Nova could not save the switch ({type(exc).__name__}: {exc}); recording is unchanged",
        ) from exc
    if body.mode != auto_record_switch.MODE_ON:
        stopped = await recording.turned_off()
    else:
        stopped = []
        await recording.sync()
    return {"lanes": view.view(), "recording_switch": view.recording_switch(), "stopped": stopped}
