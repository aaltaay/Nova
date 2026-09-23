"""In-app Sim toggle -- header Paper / Live / Sim posts here."""
from __future__ import annotations

import logging
import math

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from sim.history_routes import router as history_router
from sim.mode import set_sim_mode, status_payload

logger = logging.getLogger(__name__)

router = APIRouter(tags=["sim"])
router.include_router(history_router)


def _replay_quote_fields() -> dict:
    """``replay_quote``: a loaded capture's market at the playhead, else null (R10).

    The Trader's quote head and ticket read it on every clock poll, so they move
    with a seek instead of freezing at the price the tab opened on. Never raises
    into the clock: a failure is logged and reads as no quote.
    """
    from sim import capture_player
    from sim import replay as _replay

    if not _replay.is_capture_replay():
        return {"replay_quote": None}
    try:
        return {"replay_quote": capture_player.replay_quote()}
    except Exception:
        logger.warning("SIM: capture replay quote unavailable", exc_info=True)
        return {"replay_quote": None}


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

    return {"sim": is_sim_mode(), **_clock.status_payload(), **_replay.status_payload(), **_replay_quote_fields()}


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
    if "session_date" in body:
        return _post_day(body.get("session_date"))
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
    return {"sim": is_sim_mode(), **payload, **_replay.status_payload(), **_replay_quote_fields()}


def _post_day(value: object) -> dict:
    """Move Sim to another day with nothing loaded; null returns to today (ADR 022)."""
    from sim import day_jump
    from sim import replay as _replay
    from sim.mode import is_sim_mode

    if not is_sim_mode():
        raise HTTPException(status_code=409, detail="Moving to another day requires Sim mode")
    if value is not None and not isinstance(value, str):
        raise HTTPException(status_code=422, detail="session_date must be YYYY-MM-DD or null")
    try:
        payload = day_jump.jump_to_day(value)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"sim": is_sim_mode(), **payload, **_replay.status_payload(), **_replay_quote_fields()}


@router.get("/api/sim/replay")
def get_sim_replay() -> dict:
    from sim import replay as _replay
    from sim.mode import is_sim_mode

    return {"sim": is_sim_mode(), **_replay.status_payload()}


@router.post("/api/sim/replay")
def post_sim_replay(body: SimReplayRequest) -> dict:
    """Select capture day+ticker for Sim, or clear both to unload it.

    Answers the same envelope as ``GET /api/sim/clock``: the clock the selection
    left (a capture aligns the playhead to its first print) plus the replay
    fields. The replay fields alone made the desk read ``--:--:--`` and park the
    thumb at the open until its next poll (QA 2026-09-22, C42).
    """
    from sim import replay as _replay
    from sim import session_clock as _clock
    from sim.mode import is_sim_mode

    replay_fields = _replay.set_replay(body.date, body.symbol)
    return {"sim": is_sim_mode(), **_clock.status_payload(), **replay_fields, **_replay_quote_fields()}
