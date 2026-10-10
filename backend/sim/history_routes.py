"""Operator-facing acquisition and historical session selection.

Two sources fill a historical window (ADR 046): an IBKR download (paced, trades and
candles) and an import from the operator's Massive flat files (trades, 1-minute bars
and the NBBO). ``source`` on a request is ``auto`` by default: a download or a
selection takes the Massive files when the day's trades file is on disk, and an
IBKR download otherwise -- even over a window already downloaded from IBKR, which
plays only when the files' import of it failed. ``ibkr`` / ``massive`` force one.
"""
import json
import logging
import sqlite3
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from sim import history_download as download, history_playback as playback, history_store as store
from sim import massive_days, massive_import, massive_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sim/history", tags=["sim-history"])


class Window(BaseModel):
    symbol: str
    date: str
    start: str = "04:00"
    end: str = "20:00"
    kind: Literal["bars", "trades"] = "trades"
    source: Literal["auto", "ibkr", "massive"] = "auto"

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


def _massive_jobs() -> tuple[list[dict], str | None]:
    """The Massive imports, or none with the reason the store could not be read -- stated, never an empty list."""
    error = None
    try:
        jobs = massive_import.list_jobs()
    except (sqlite3.DatabaseError, OSError) as exc:
        logger.warning("Massive replay store unreadable; its imports are not listed", exc_info=True)
        jobs, error = [], f"The Massive replay store cannot be read: {exc}"
    return jobs, error


def _listing() -> dict:
    imports, store_error = _massive_jobs()
    # Every job, IBKR downloads and Massive imports, the most recently active first.
    jobs = sorted([*download.list_jobs(), *imports], key=lambda job: job.get("updated") or 0, reverse=True)
    selection = playback.status()
    if selection:
        # The selection's download status as of now, from the listing it rides with (C38).
        selection = playback.with_live_download_status(selection, jobs)
    return {"jobs": jobs, "selection": selection, "storage": str(store.path()), "default_date": _default_date(),
            "massive": dict(massive_days.summary(), store_error=store_error)}


@router.get("")
def list_downloads():
    return checked(_listing)


def _massive_available(window: dict) -> bool:
    return massive_import.availability(window["date"])["available"]


def _begin(body: Window):
    window = body.spec()
    if body.source == "massive" or (body.source == "auto" and _massive_available(window)):
        # One import fills trades, candles and quotes, so either download button starts it.
        return massive_import.begin(window)
    return download.begin(window, body.kind)


@router.post("")
def begin(body: Window):
    return checked(lambda: _begin(body))


def _import_failed(job: dict | None) -> bool:
    return job is not None and massive_import.effective_status(job) == "failed"


def _select_spec(body: Window) -> dict:
    """The window to load, from the source the request names or ``auto`` picks.

    ``auto`` puts the Massive files first (operator, 2026-10-09: "shouldn't we have
    prioritized it over ibkr data?"): an import of the window, or the day's files on
    disk, win over an IBKR download of the same hours -- the files carry the whole
    tape and the bid and ask, the download neither. An IBKR download plays only when
    the files hold neither the window nor the day, or their import of it failed.
    """
    window = body.spec()
    if body.source == "ibkr":
        return window
    # One import per stock-day (amendment 2026-10-09): when it holds the window, load what it holds -- the
    # whole day, or the window a capped day kept -- so a scrub anywhere in it needs no other import.
    day = massive_import.day_job(window)
    if massive_import.holds(day, window):
        return massive_import.held_spec(day)
    massive = massive_import.spec(window)
    older = massive_store.find(massive)                 # an import of exactly this window, from before stock-days
    if older is not None and day is not None and older["id"] == day["id"]:
        older = None                                    # the window asked for is the day itself
    if massive_import.holds(older, window):
        return massive
    if body.source == "massive":
        return massive
    imported = day or older
    if store.find(window, "trades") is not None and (_import_failed(imported) or not _massive_available(window)):
        return window
    if imported is not None or _massive_available(window):
        return massive
    return window


def _select(body: Window):
    spec = _select_spec(body)
    if playback.is_massive(spec) and massive_import.wants_import(body.spec(), massive_import.availability(spec["date"])):
        # Picked up on selection: the stock-day's import starts (or starts again, once the
        # day's quotes are on disk, or for a capped day's other window), and the desk's
        # quiet re-select folds it in when it completes. What was imported before keeps playing.
        massive_import.begin(body.spec())
    return playback.select(spec, request=body.spec())


@router.post("/select")
def select(body: Window):
    from sim.mode import is_sim_mode
    if not is_sim_mode():
        raise HTTPException(409, "Select Sim mode before loading historical replay")
    return checked(lambda: _select(body))


@router.get("/snapshot/{symbol}")
def snapshot(symbol: str):
    from sim.mode import is_sim_mode
    return checked(lambda: playback.snapshot(symbol.strip().upper())) if is_sim_mode() else {"active": False}


@router.get("/massive/days")
def massive_day_list():
    """The days whose Massive files are whole on disk (the Sim Day calendar's mark)."""
    return checked(massive_days.listing)


@router.get("/massive/{day}")
def massive_day(day: str):
    """What the Massive folder holds for one ISO date."""
    return checked(lambda: dict(date=massive_days.iso_date(day), **massive_import.availability(day)))


class DepthLine(BaseModel):
    symbol: str
    hold: bool = True


@router.post("/depth-line")
def depth_line(body: DepthLine):
    """The historical Level 2 holds (or lets go of) the replay depth slot a bot's gate reads (QA R44)."""
    from sim import history_depth_line

    return history_depth_line.hold(body.symbol) if body.hold else history_depth_line.release(body.symbol)


def _massive_job(job_id: str) -> dict | None:
    try:
        return massive_store.get(job_id)
    except (sqlite3.DatabaseError, OSError):
        logger.warning("Massive replay store unreadable while routing job %s", job_id, exc_info=True)
        return None


def _resume(job_id: str):
    job = _massive_job(job_id)
    if job is not None:
        # A Massive import does not resume mid-file: it reads the day again from the start, for the same focus.
        return massive_import.begin(store.window(job["symbol"], job["date"], job.get("focus_start") or job["start"],
                                                 job.get("focus_end") or job["end"]))
    return download.start(job_id)


@router.post("/{job_id}/resume")
def resume(job_id: str):
    return checked(lambda: _resume(job_id))


@router.post("/{job_id}/pause")
def pause(job_id: str):
    return checked(lambda: massive_import.pause(job_id) if _massive_job(job_id) is not None else download.pause(job_id))
