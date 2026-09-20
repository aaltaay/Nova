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


@router.get("")
def list_downloads():
    return checked(lambda: {"jobs": download.list_jobs(), "selection": playback.status(),
                            "storage": str(store.path()), "default_date": store.default_date()})


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
