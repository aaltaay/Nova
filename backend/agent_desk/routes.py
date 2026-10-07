"""``/api/agent`` (ADR 050): the private endpoints agents use to find stock-days and show them on the desk.

Loopback clients only. Every write -- and the desk's own long poll -- needs the desk's API key even on loopback
(``auth.is_agent_mutate`` and ``require_agent_key``). Percentages on this wire are percent points. Nothing here
places, stages or cancels an order, or arms the desk.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Annotated, Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from agent_desk import commands, dictionary, movers_read, planner
from agent_desk.desk_view import desk_state, loaded_window, sim_state
from auth import require_agent_key
from constants_agent_desk import AGENT_DESK_SCHEMA_VERSION, AGENT_LONG_POLL_MAX_SEC
from constants_bot import BOT_LOOPBACK_HOSTS
from day_movers.query import QueryError

ET = ZoneInfo("America/New_York")
_SYMBOL = re.compile(r"^[A-Za-z][A-Za-z0-9.\-]{0,9}$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def require_local(request: Request) -> None:
    host = ((request.client.host if request.client else "") or "").strip().lower()
    if host in BOT_LOOPBACK_HOSTS or host.startswith("127."):
        return
    raise HTTPException(status_code=403, detail={"reason": "AGENT_NOT_LOCAL",
                                                 "error": "the agent endpoints answer only on this PC"})


router = APIRouter(prefix="/api/agent", tags=["agent"], dependencies=[Depends(require_local)])
_keyed = [Depends(require_agent_key)]

ENDPOINTS = (
    ("GET", "/api/agent", "this catalogue: the endpoints, the index's reach, the dictionary, the desk"),
    ("GET", "/api/agent/movers", "find stock-days by the numbers (percent moves, price, float, time of the high)"),
    ("GET", "/api/agent/movers/{date}/{symbol}", "one stock-day as the index holds it"),
    ("POST", "/api/agent/show", "put the desk on a stock-day in the Sim, paused at a moment (a command)"),
    ("POST", "/api/agent/move", "move the Sim's playhead in the loaded day, or pause / play (a command)"),
    ("GET", "/api/agent/commands/{id}?wait=", "follow a command (waits up to `wait` seconds for a change)"),
    ("POST", "/api/agent/commands/{id}/cancel", "stop a command"),
    ("GET", "/api/agent/desk", "what the desk shows now, and what a venue switch would put at stake"),
    ("GET", "/api/agent/dictionary", "the operator's words for commands: read it before acting"),
    ("POST", "/api/agent/dictionary", "add or replace an entry the operator confirmed ({entry})"),
    ("DELETE", "/api/agent/dictionary/{id}", "drop an operator entry"),
)
RULES = (
    "Nothing on these endpoints places, stages or cancels an order, or arms the desk.",
    "Nova defines no shape words: turn the operator's words into numbers, show the numbers, ask when they have "
    "no agreed meaning, and save what the operator confirms to the dictionary.",
    "On AGENT_AT_STAKE, tell the operator what the show or move puts at stake (a venue switch, the Sim account "
    "starting over) and wait for their OK before sending confirm: true.",
    "A float passes only on evidence (the float Nova knew that day, or SEC shares outstanding under the limit); "
    "everything else is 'float unknown' -- say so, never guess it.",
    "Percentages on this wire are percent points (300 = +300%).",
)


def board() -> commands.CommandBoard:
    return commands.BOARD


def _refuse(status: int, reason: str, error: str, **extra: Any) -> HTTPException:
    return HTTPException(status_code=status, detail={"reason": reason, "error": error, **extra})


def _today_et() -> str:
    return datetime.now(ET).date().isoformat()


# ── Catalogue and search ────────────────────────────────────────────────────

@router.get("")
async def get_catalogue() -> dict[str, Any]:
    index = await run_in_threadpool(movers_read.index_status)
    words = await run_in_threadpool(dictionary.view)
    return {
        "schema_version": AGENT_DESK_SCHEMA_VERSION,
        "endpoints": [{"method": m, "path": p, "does": d} for m, p, d in ENDPOINTS],
        "index": index,
        "dictionary": {"entries": len(words["entries"]), "error": words["error"]},
        "desk": board().desk(),
        "rules": list(RULES),
    }


@router.get("/movers")
def get_movers(request: Request) -> dict[str, Any]:
    try:
        return movers_read.search(dict(request.query_params))
    except QueryError as exc:
        raise _refuse(400, "AGENT_INVALID", str(exc), field=exc.field) from exc
    except movers_read.IndexUnavailable as exc:
        raise _refuse(503, "AGENT_INDEX_UNAVAILABLE", str(exc)) from exc


@router.get("/movers/{day}/{symbol}")
def get_mover(day: str, symbol: str) -> dict[str, Any]:
    if not _DATE.match(day) or not _SYMBOL.match(symbol):
        raise _refuse(400, "AGENT_INVALID", "the path is /api/agent/movers/YYYY-MM-DD/SYMBOL")
    try:
        found = movers_read.search({"date_from": day, "date_to": day, "symbol": symbol, "kinds": "all",
                                    "splits": "include", "limit": 1})
    except movers_read.IndexUnavailable as exc:
        raise _refuse(503, "AGENT_INDEX_UNAVAILABLE", str(exc)) from exc
    if not found["rows"]:
        raise _refuse(404, "AGENT_NOT_IN_INDEX",
                      f"{symbol.upper()} on {day} is not in the movers index (it did not move, or that day is not built)")
    return {"schema_version": AGENT_DESK_SCHEMA_VERSION, "row": found["rows"][0], "coverage": found["coverage"]}


# ── Commands for the desk ───────────────────────────────────────────────────

class ShowRequest(BaseModel):
    symbol: str
    date: str
    at: str | None = Field(default=None, description="run | drop | high | low | open | premarket | HH:MM (ET)")
    confirm: bool = Field(default=False, description="the operator agreed to what is at stake (never on your own)")


class MoveRequest(BaseModel):
    to: str | None = None
    by_min: float | None = None
    paused: bool | None = None
    confirm: bool = False


def _require_listening() -> None:
    if not board().listening():
        raise _refuse(409, "AGENT_NO_DESK",
                      "no main desk window is listening: open Nova's desk (its main window), then ask again")


def _same_window(loaded: dict[str, Any] | None, symbol: str, day: str, window: dict[str, Any] | None) -> bool:
    return bool(loaded and window and loaded.get("symbol") == symbol and loaded.get("date") == day
                and loaded.get("start") == window["start"] and loaded.get("end") == window["end"])


def _stake_check(*, switching: bool, reloading: bool, confirm: bool) -> None:
    """Refuses (``AGENT_AT_STAKE``) when the command would put something at stake the operator did not agree to."""
    from agent_desk.safety import at_stake
    from sim.mode import venue

    current = venue()
    stake = at_stake(current, switching=switching, reloading=reloading)
    if stake["safe"] or confirm:
        return
    names = "; ".join(i["text"] for i in stake["items"]) or "a check could not be read"
    what = (f"the desk is on {current.capitalize()} -- a venue change disarms, turns the Bot off and cancels "
            "Nova's working entries there" if switching and current != "sim" else "the Sim is loaded")
    raise _refuse(
        409, "AGENT_AT_STAKE",
        f"{what}, and this puts something at stake: {names}. Ask the operator; send confirm: true only after "
        "they agree.",
        at_stake=stake,
    )


@router.post("/show", status_code=202, dependencies=_keyed)
async def post_show(body: ShowRequest) -> dict[str, Any]:
    symbol, day = body.symbol.strip().upper(), body.date.strip()
    if not _SYMBOL.match(symbol) or not _DATE.match(day):
        raise _refuse(400, "AGENT_INVALID", "symbol must be a ticker and date YYYY-MM-DD")
    from constants_sim import SIM_MASSIVE_TRADES
    from sim.massive_files import day_file

    if await run_in_threadpool(day_file, SIM_MASSIVE_TRADES, day) is None:
        raise _refuse(404, "AGENT_NOT_ON_FILE",
                      f"no trades file for {day} in the Massive folder: the Sim cannot replay that day from the files")
    row = await run_in_threadpool(movers_read.row_or_none, day, symbol)
    try:
        plan = planner.plan_show(symbol, day, body.at, row, today=_today_et())
    except planner.PlanError as exc:
        raise _refuse(400, "AGENT_INVALID", str(exc)) from exc
    _require_listening()
    from sim.mode import venue

    switching = venue() != "sim"
    loaded = await run_in_threadpool(loaded_window)
    reloading = not _same_window(loaded, symbol, day, plan["window"])
    await run_in_threadpool(lambda: _stake_check(switching=switching, reloading=reloading, confirm=body.confirm))
    plan.update(switch_venue=switching, in_index=row is not None)
    return {"command": board().create("show", body.model_dump(), plan)}


@router.post("/move", status_code=202, dependencies=_keyed)
async def post_move(body: MoveRequest) -> dict[str, Any]:
    _require_listening()
    sim = await run_in_threadpool(sim_state)
    loaded = await run_in_threadpool(loaded_window)
    if sim is None or loaded is None:
        raise _refuse(409, "AGENT_NOTHING_LOADED", "the desk is not on the Sim with a day loaded: show one first")
    row = await run_in_threadpool(movers_read.row_or_none, str(loaded["date"]), str(loaded["symbol"]))
    try:
        plan = planner.plan_move(loaded, float(sim["playhead_ts"]), to=body.to, by_min=body.by_min,
                                 paused=body.paused, row=row)
    except planner.PlanError as exc:
        raise _refuse(400, "AGENT_INVALID", str(exc)) from exc
    if plan["window"] is not None:
        await run_in_threadpool(lambda: _stake_check(switching=False, reloading=True, confirm=body.confirm))
    return {"command": board().create("move", body.model_dump(), plan)}


@router.get("/commands")
async def get_commands() -> dict[str, Any]:
    return {"commands": board().recent()}


@router.get("/commands/{command_id}")
async def get_command(command_id: str, wait: Annotated[float, Query(ge=0)] = 0.0) -> dict[str, Any]:
    command = await board().wait_get(command_id, min(wait, AGENT_LONG_POLL_MAX_SEC))
    if command is None:
        raise _refuse(404, "AGENT_UNKNOWN_COMMAND", f"no command {command_id} (only the newest are kept)")
    return {"command": command}


@router.post("/commands/{command_id}/cancel", dependencies=_keyed)
async def post_cancel(command_id: str) -> dict[str, Any]:
    command = board().cancel(command_id)
    if command is None:
        raise _refuse(404, "AGENT_UNKNOWN_COMMAND", f"no command {command_id}")
    return {"command": command}


@router.get("/desk")
def get_desk() -> dict[str, Any]:
    return desk_state(board())


# ── The dictionary ──────────────────────────────────────────────────────────

class DictionaryRequest(BaseModel):
    entry: dict[str, Any]


@router.get("/dictionary")
def get_dictionary() -> dict[str, Any]:
    return dictionary.view()


@router.post("/dictionary", dependencies=_keyed)
def post_dictionary(body: DictionaryRequest) -> dict[str, Any]:
    try:
        return {"entry": dictionary.put(body.entry), **dictionary.view()}
    except dictionary.EntryInvalid as exc:
        raise _refuse(400, "AGENT_INVALID", str(exc), field=exc.field) from exc
    except dictionary.DictionaryUnreadable as exc:
        raise _refuse(409, "AGENT_DICTIONARY_UNREADABLE", str(exc)) from exc


@router.delete("/dictionary/{entry_id}", dependencies=_keyed)
def delete_dictionary(entry_id: str) -> dict[str, Any]:
    try:
        removed = dictionary.remove(entry_id)
    except dictionary.DictionaryUnreadable as exc:
        raise _refuse(409, "AGENT_DICTIONARY_UNREADABLE", str(exc)) from exc
    if not removed:
        raise _refuse(404, "AGENT_UNKNOWN_ENTRY", f"no operator entry {entry_id} (a seed cannot be removed)")
    return dictionary.view()


# ── The desk's side ─────────────────────────────────────────────────────────

class DeskReport(BaseModel):
    status: str
    step: str | None = None
    text: str | None = None
    result: Any = None
    error: str | None = None


@router.get("/desk/next", dependencies=_keyed)
async def get_desk_next(request: Request, wait: Annotated[float, Query(ge=0)] = 0.0,
                        window_id: str | None = None) -> dict[str, Any]:
    """The main desk window's long poll: the oldest queued command, now its own; null after ``wait`` seconds.

    A poll whose window went away while it waited (a reload) hands its command back for the next one.
    """
    command = await board().next_for_desk(min(wait, AGENT_LONG_POLL_MAX_SEC), window_id)
    if command is not None and await request.is_disconnected():
        board().release(command["id"])
        return {"command": None}
    return {"command": command}


@router.post("/desk/commands/{command_id}", dependencies=_keyed)
async def post_desk_report(command_id: str, body: DeskReport) -> dict[str, Any]:
    try:
        command = board().report(command_id, status=body.status, step=body.step, text=body.text,
                                 result=body.result, error=body.error)
    except ValueError as exc:
        raise _refuse(400, "AGENT_INVALID", str(exc)) from exc
    if command is None:
        raise _refuse(404, "AGENT_UNKNOWN_COMMAND", f"no command {command_id}")
    return {"command": command}
