"""Capture HTTP routes.

Record holds a reference on its stock's tape and depth lines (``capture.feed_hold``) for as long as it
records, so a panel closing never ends it (#315). The lines themselves are a lane's (ADR 071): Record
records only a stock a lane is on (409 otherwise) and ends, as planned, when its stock leaves every lane
(``line_lanes.recording.stop_for``). Lifecycle calls run on a worker thread -- ``capture.worker``
refuses to run inside the event loop.
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from capture import feed_hold, keepalive
from capture.constants_capture import CAPTURE_MAX_CONCURRENT
from capture.mode import capture_symbols, is_capture_mode, set_capture_mode, status_payload
from capture.recorder import status as recorder_status
from capture.sessions import list_sessions

logger = logging.getLogger(__name__)
router = APIRouter(tags=["capture"])

# Background releases, kept referenced so the loop cannot drop them mid-flight.
_releases: set[asyncio.Task] = set()


class CaptureToggleRequest(BaseModel):
    enabled: bool
    symbol: str | None = Field(default=None, description="Symbol to record; set Monday morning")


def _release_later(symbol: str) -> None:
    """Release a hold without holding up the response (depth waits a grace window)."""
    task = asyncio.get_running_loop().create_task(feed_hold.release(symbol))
    _releases.add(task)
    task.add_done_callback(_releases.discard)


def _release_orphans() -> None:
    """Drop holds the recorder no longer uses -- never a start still in flight (#525)."""
    recording = set(capture_symbols()) if is_capture_mode() else set()
    for symbol in feed_hold.orphans(recording):
        _release_later(symbol)


@router.get("/api/capture")
async def get_capture() -> dict:
    out = await asyncio.to_thread(status_payload)
    _release_orphans()
    return {**out, "recorder": recorder_status()}


def _lanes_hook(name: str, symbol: str | None) -> None:
    """Hand a symbol to the operator: the lanes' recording never stops or restarts it (ADR 071)."""
    try:
        from line_lanes import recording

        getattr(recording, name)(symbol)
    except Exception:
        logger.exception("LANES recording: %s hook failed for %s", name, symbol)


@router.post("/api/capture")
async def post_capture(body: CaptureToggleRequest) -> dict:
    requested = (body.symbol or "").strip().upper()
    recording = capture_symbols() if is_capture_mode() else []
    if body.enabled:
        target = requested or (recording[0] if recording else "")
        if target and target not in recording:
            # Only a stock a lane is on is recorded (ADR 071 decision 8): a lane holds its lines.
            from line_lanes import lanes

            if lanes.enforced() and not lanes.on_lane(target):
                raise HTTPException(status_code=409,
                                    detail=f"{target} is on no lane: open it in front to record it")
        # Refuse a fourth symbol before touching any IBKR line: opening and
        # closing a tape line costs IBKR's 15 s resubscribe guard.
        if target and target not in recording and len(recording) >= CAPTURE_MAX_CONCURRENT:
            raise HTTPException(
                status_code=409,
                detail=f"Already recording {', '.join(recording)} -- IBKR allows "
                       f"{CAPTURE_MAX_CONCURRENT} depth lines; stop one first",
            )
        if target:
            error = await feed_hold.acquire(target)
            if error:
                out = await asyncio.to_thread(status_payload)
                return {**out, "error": error, "recorder": recorder_status()}
        out = await asyncio.to_thread(set_capture_mode, True, symbol=body.symbol, protect_active=True)
        if target and target in (out.get("capture_symbols") or []):
            keepalive.operator_started(target)
            _lanes_hook("operator_took", target)
    else:
        # Before the stop: the keepalive must never read this as a death.
        keepalive.operator_stopped(requested or None)
        _lanes_hook("operator_stopped", requested or None)
        out = await asyncio.to_thread(set_capture_mode, False, symbol=body.symbol, protect_active=True)
    _release_orphans()
    if out.pop("conflict", False):
        raise HTTPException(status_code=409, detail=out["error"])
    return {**out, "recorder": recorder_status()}


@router.get("/api/capture/sessions")
def get_capture_sessions() -> dict:
    """List recorded days/tickers under the capture root for Sim replay pickers."""
    return list_sessions()
