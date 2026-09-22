"""Operator-facing acquisition and historical session selection."""
import json
import logging
import sqlite3
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from sim import history_download as download, history_playback as playback, history_store as store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sim/history", tags=["sim-history"])


class Window(BaseModel):
    symbol: str
    date: str
    start: str = "04:00"
    end: str = "20:00"
    kind: Literal["bars", "trades"] = "trades"

    def spec(self):
        return store.window(self.symbol, self.date, self.start, self.end)


def checked(action):
    try:
        return action()
    except (sqlite3.DatabaseError, OSError, json.JSONDecodeError) as exc:
        logger.exception("Historical archive unavailable")
        raise HTTPException(503, "Historical archive is unavailable; check storage and retry") from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


def _default_date() -> str | None:
    """The picker's pre-filled date, or None when it cannot be computed.

    Scoped on purpose (#386): this is one convenience field, and an operator who
    already knows the date they want must still see their jobs, their selection
    and their storage path. Failing it used to fail the whole listing.
    """
    try:
        return store.default_date()
    except ValueError:
        logger.warning("Default replay date is unavailable; listing continues without it",
                       exc_info=True)
        return None


def _listing() -> dict:
    jobs = download.list_jobs()
    selection = playback.status()
    if selection:
        # The selection's download status as of now, from the listing it rides with (C38).
        selection = playback.with_live_download_status(selection, jobs)
    return {"jobs": jobs, "selection": selection, "storage": str(store.path()), "default_date": _default_date()}


@router.get("")
def list_downloads():
    return checked(_listing)


def _begin(body: Window):
    return download.begin(body.spec(), body.kind)


@router.post("")
def begin(body: Window):
    return checked(lambda: _begin(body))


@router.post("/select")
def select(body: Window):
    from sim.mode import is_sim_mode
    if not is_sim_mode():
        raise HTTPException(409, "Select Sim mode before loading historical replay")
    return checked(lambda: playback.select(body.spec()))


@router.get("/snapshot/{symbol}")
def snapshot(symbol: str):
    from sim.mode import is_sim_mode
    return checked(lambda: playback.snapshot(symbol.strip().upper())) if is_sim_mode() else {"active": False}


@router.post("/{job_id}/resume")
def resume(job_id: str):
    return checked(lambda: download.start(job_id))


@router.post("/{job_id}/pause")
def pause(job_id: str):
    return checked(lambda: download.pause(job_id))
