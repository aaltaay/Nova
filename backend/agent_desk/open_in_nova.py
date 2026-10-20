"""Open in Nova: a thin wrapper around the existing show command.

maintainer: one-concern the open-in-nova request (arguments, session gate, and stake) must live in one place

``POST /api/agent/show`` already plans the window, queues a ``show`` command, and the desk
lands it (``landSim`` posts the day, which calls ``jump_to_day``, then parks with
``scrub_to_second``). This route queues that same command. It adds only what show does
not have: a separate Sim window while the session is open (premarket, regular hours,
and after-hours, including a 13:00 early close), an install token instead of the API
key, and strict arguments. A venue change runs the show at-stake check first and
refuses when anything is at stake. It does not jump the clock itself, and it never
calls ``leave_safely`` or an order route.

The browser caller uses ``X-Nova-Open-Token``, not ``X-Nova-Api-Key``.
"""
from __future__ import annotations

import ipaddress
import json
import logging
import re
from collections.abc import Callable
from datetime import date, datetime, time
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from agent_desk import commands, planner
from agent_desk.open_token import (
    OPEN_TOKEN_UNAVAILABLE,
    OPEN_TOKEN_UNAVAILABLE_TEXT,
    TokenError,
    token_matches,
)
from constants_agent_desk import OPEN_IN_NOVA_HEADER, OPEN_IN_NOVA_TRIGGER_LEAD_SEC
from constants_scanner import SESSION_PREMARKET_START_MIN_ET, SESSION_RTH_OPEN_MIN_ET
from constants_sim import SIM_SESSION_OPEN_HOUR
from market_board.clock import after_hours_end_minute, close_minute

logger = logging.getLogger(__name__)

ET = ZoneInfo("America/New_York")
_LOOPBACK = (ipaddress.ip_address("127.0.0.1"), ipaddress.ip_address("::1"))
_SYMBOL = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_CLOCK = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)(?::([0-5]\d))?$")
_ARGUMENTS = ("symbol", "date", "as_of")
DESK_NOT_RUNNING_TEXT = (
    "Nova's desk is not running. Start it with scripts/windows/Run Nova Desktop.bat, then ask again."
)
SESSION_OPEN_MIN = SIM_SESSION_OPEN_HOUR * 60
SESSION_CLOSE_MIN = 20 * 60


class OpenError(Exception):
    def __init__(self, status: int, reason: str, error: str) -> None:
        super().__init__(error)
        self.status = status
        self.reason = reason
        self.error = error


def wall_clock() -> datetime:
    return datetime.now(ET)


def this_pc_host(host: str) -> bool:
    """``localhost``, or the address 127.0.0.1 or ::1. Never a ``127.`` prefix."""
    name = host.lower().rstrip(".")
    if name == "localhost":
        return True
    try:
        return ipaddress.ip_address(name) in _LOOPBACK
    except ValueError:
        return False


def foreign_origin(origin: str | None) -> bool:
    """A browser page on another host. Loopback, no Origin, and ``file://`` are this PC.

    The host is parsed and compared with ``ipaddress``. A DNS name that only starts
    with ``127.`` (``http://127.0.0.1.evil.example``) is foreign. Any port on an
    allowed host is allowed.
    """
    if origin is None or origin == "" or origin == "file://":
        return False
    if origin == "null" or "\r" in origin or "\n" in origin:
        return True
    parsed = urlparse(origin)
    if parsed.scheme not in {"http", "https"} or parsed.username is not None or parsed.password is not None:
        return True
    host = parsed.hostname
    if not host:
        return True
    return not this_pc_host(host)


def chat_message(symbol: str, day: str, clock: str, *, separate: bool) -> str:
    if separate:
        return (
            f"Opened {symbol} in a separate Sim window on {day} at {clock} ET, paused. "
            "The live desk stayed on its own view."
        )
    return f"Opened {symbol} in Nova Sim on {day} at {clock} ET, paused."


def in_rth(now: datetime, trading_day: Callable[[date], bool]) -> bool:
    """Wall-clock regular hours: 09:30 inclusive, the close exclusive.

    The close is 16:00 ET, or 13:00 ET on an NYSE early close.
    """
    moment = now.astimezone(ET)
    if not trading_day(moment.date()):
        return False
    minute = moment.hour * 60 + moment.minute
    return SESSION_RTH_OPEN_MIN_ET <= minute < close_minute(moment.date())


def keeps_the_main_desk(now: datetime, trading_day: Callable[[date], bool]) -> bool:
    """Premarket, regular hours, and after-hours stay on the desk the operator is using.

    A half-day ends the regular session at 13:00 ET and after-hours at 17:00 ET.
    Overnight, a weekend, and a holiday may leave that desk only when nothing is at stake.
    """
    moment = now.astimezone(ET)
    if not trading_day(moment.date()):
        return False
    minute = moment.hour * 60 + moment.minute
    return SESSION_PREMARKET_START_MIN_ET <= minute < after_hours_end_minute(moment.date())


def stake_text(current: str, stake: dict[str, Any]) -> str:
    parts = [str(item.get("text") or item.get("kind") or "at stake") for item in stake.get("items") or []]
    unknown = list(stake.get("unknown") or [])
    if unknown:
        kinds = ", ".join(str(item.get("kind") or "check") for item in unknown)
        parts.append(f"a check could not be read ({kinds})")
    names = "; ".join(parts) or "a check could not be read"
    return (
        f"The desk is on {current.capitalize()}, and this puts something at stake: {names}. "
        "The main desk was not switched."
    )


def second_from_open(day: str, park_ts: int) -> float:
    return float(park_ts - planner.et_ts(day, SESSION_OPEN_MIN))


def parse_payload(body: Any) -> dict[str, Any]:
    if not isinstance(body, dict):
        raise OpenError(400, "BAD_REQUEST", "body must be a JSON object")
    for key in body:
        if key not in _ARGUMENTS:
            raise OpenError(400, "UNKNOWN_ARGUMENT", str(key))
    symbol = body.get("symbol")
    day = body.get("date")
    if not isinstance(symbol, str) or not isinstance(day, str):
        raise OpenError(400, "BAD_REQUEST", "symbol and date are required strings")
    symbol = symbol.strip().upper()
    day = day.strip()
    if not _SYMBOL.match(symbol):
        raise OpenError(400, "BAD_REQUEST", "symbol must be a ticker (A-Z, dot, dash, at most 10)")
    if not _DATE.match(day):
        raise OpenError(400, "BAD_REQUEST", "date must be YYYY-MM-DD")
    try:
        date.fromisoformat(day)
    except ValueError as exc:
        raise OpenError(400, "BAD_REQUEST", "date must be YYYY-MM-DD") from exc
    as_of = body.get("as_of")
    if as_of is None:
        return {"symbol": symbol, "date": day, "as_of": None}
    if not isinstance(as_of, str) or not _clock_ok(as_of.strip()):
        raise OpenError(400, "BAD_REQUEST", "as_of must be HH:MM or HH:MM:SS ET between 04:00:00 and 20:00:00")
    return {"symbol": symbol, "date": day, "as_of": _normalize_clock(as_of.strip())}


def park_before_setup(day: str, setups: list[dict[str, Any]] | None) -> int | None:
    """Two minutes before the earliest setup, not earlier than 04:00 ET."""
    stamps: list[int] = []
    for item in setups or []:
        raw = item.get("time") if isinstance(item, dict) else None
        if not isinstance(raw, str) or not raw:
            continue
        try:
            moment = datetime.fromisoformat(raw)
        except ValueError:
            continue
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=ET)
        stamps.append(int(moment.timestamp()))
    if not stamps:
        return None
    earliest = min(stamps) - OPEN_IN_NOVA_TRIGGER_LEAD_SEC
    floor = planner.et_ts(day, SESSION_OPEN_MIN)
    ceiling = planner.et_ts(day, SESSION_CLOSE_MIN)
    return max(floor, min(earliest, ceiling))


def switch_main_view_to_sim() -> None:
    """Move the desk view to Sim without cancelling working orders (``left=[]`` skips ADR 042 F)."""
    from sim.mode import set_venue, venue

    if venue() == "sim":
        return
    set_venue("sim", left=[])


def refuse_transport(request: Request) -> None:
    if foreign_origin(request.headers.get("origin")):
        raise OpenError(403, "FORBIDDEN", "this open path refuses a foreign Origin")
    ctype = (request.headers.get("content-type") or "").split(";", 1)[0].strip().lower()
    if ctype != "application/json":
        raise OpenError(415, "BAD_REQUEST", "Content-Type must be application/json")
    if not token_matches(request.headers.get(OPEN_IN_NOVA_HEADER)):
        raise OpenError(401, "BAD_TOKEN", "missing or wrong open token")


def perform(
    body: Any,
    *,
    now: datetime,
    listening: Callable[[], bool] | None = None,
    switch_view: Callable[[], None] | None = None,
    venue: Callable[[], str] | None = None,
    queue: Callable[[dict, dict], Any] | None = None,
    setups_for: Callable[[str, str], list] | None = None,
    row_for: Callable[[str, str], dict | None] | None = None,
    trading_day: Callable[[date], bool] | None = None,
    on_file: Callable[[str], bool] | None = None,
    stake_for: Callable[[str], dict] | None = None,
) -> dict[str, Any]:
    parsed = parse_payload(body)
    day_ok = trading_day or _trading_day
    target = date.fromisoformat(parsed["date"])
    today = now.astimezone(ET).date().isoformat()
    if parsed["date"] >= today:
        raise OpenError(400, "BAD_REQUEST", f"{parsed['date']} is not over yet: the Sim replays past days from the files")
    if not day_ok(target):
        raise OpenError(400, "BAD_REQUEST", f"{parsed['date']} is not an exchange day")
    if not (on_file or _on_file)(parsed["date"]):
        raise OpenError(
            404, "AGENT_NOT_ON_FILE",
            f"no trades file for {parsed['date']} in the Massive folder: the Sim cannot replay that day from the files",
        )
    if not (listening or _listening)():
        raise OpenError(409, "DESK_NOT_RUNNING", DESK_NOT_RUNNING_TEXT)
    separate = keeps_the_main_desk(now, day_ok)
    plan = _plan(parsed, today=today, setups_for=setups_for or _setups_for, row_for=row_for or _row_for)
    plan["separate_sim"] = separate
    plan["switch_venue"] = False
    plan["paused"] = True
    plan["review_path"] = f"/review?symbol={plan['symbol']}&date={plan['date']}&as_of={plan['park_et'][:5]}"
    switched = False
    if not separate:
        # The desk's show landing moves the day and the playhead. Switch the view
        # here, with no order cancel, so that landing does not call leave_safely.
        # set_venue persists the desk, disarms the padlock, and leaves broker
        # orders unwatched, so the show at-stake check runs first and a refusal
        # does not switch.
        current = (venue or _venue)()
        if current != "sim":
            stake = (stake_for or _stake)(current)
            if not stake.get("safe"):
                raise OpenError(409, "AGENT_AT_STAKE", stake_text(current, stake))
            (switch_view or switch_main_view_to_sim)()
            switched = True
    plan["switch_view"] = switched
    command = (queue or _queue)({"symbol": parsed["symbol"], "date": parsed["date"], "as_of": parsed["as_of"]}, plan)
    return {
        "ok": True,
        "chat_message": chat_message(plan["symbol"], plan["date"], plan["park_et"], separate=separate),
        "symbol": plan["symbol"],
        "date": plan["date"],
        "as_of": plan["park_et"],
        "paused": True,
        "separate_sim": separate,
        "command": command,
    }


def register(router: APIRouter) -> None:
    @router.get("/open-token")
    def get_open_token(request: Request) -> dict[str, Any]:
        from agent_desk.open_token import load_or_create

        if foreign_origin(request.headers.get("origin")):
            raise HTTPException(status_code=403, detail={"reason": "FORBIDDEN", "error": "this open path refuses a foreign Origin"})
        try:
            body = load_or_create()
        except Exception as exc:
            raise _token_unavailable(exc) from exc
        return {"schema_version": body["schema_version"], "token": body["token"]}

    @router.post("/open-in-nova")
    async def post_open_in_nova(request: Request) -> dict[str, Any]:
        try:
            refuse_transport(request)
            body = await _json_body(request)
            result = await run_in_threadpool(lambda: perform(body, now=wall_clock()))
        except OpenError as exc:
            raise HTTPException(status_code=exc.status, detail={"reason": exc.reason, "error": exc.error}) from exc
        except TokenError as exc:
            raise _token_unavailable(exc) from exc
        return result


def _token_unavailable(exc: BaseException) -> HTTPException:
    """A token failure is 503 with a stable sentence. The real exception stays in the log."""
    logger.exception("open in nova: token file refused (%s)", type(exc).__name__)
    return HTTPException(
        status_code=503,
        detail={"reason": OPEN_TOKEN_UNAVAILABLE, "error": OPEN_TOKEN_UNAVAILABLE_TEXT},
    )


async def _json_body(request: Request) -> Any:
    raw = await request.body()
    try:
        return json.loads(raw.decode("utf-8") if raw else "null")
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OpenError(400, "BAD_REQUEST", "body must be JSON") from exc


def _clock_ok(value: str) -> bool:
    match = _CLOCK.match(value)
    if not match:
        return False
    hour, minute, second = int(match.group(1)), int(match.group(2)), int(match.group(3) or 0)
    stamp = hour * 3600 + minute * 60 + second
    return SESSION_OPEN_MIN * 60 <= stamp <= SESSION_CLOSE_MIN * 60


def _normalize_clock(value: str) -> str:
    match = _CLOCK.match(value)
    assert match is not None
    second = match.group(3) or "00"
    return f"{int(match.group(1)):02d}:{match.group(2)}:{second}"


def _plan(parsed: dict[str, Any], *, today: str, setups_for, row_for) -> dict[str, Any]:
    symbol, day, as_of = parsed["symbol"], parsed["date"], parsed["as_of"]
    if as_of is not None:
        hour, minute, second = (int(part) for part in as_of.split(":"))
        park = _et_ts(day, hour, minute, second)
        words = f"at {as_of}"
        which = as_of[:5]
    else:
        park = park_before_setup(day, setups_for(symbol, day))
        if park is None:
            row = row_for(day, symbol)
            try:
                planned = planner.plan_show(symbol, day, "run" if row else "open", row, today=today)
            except planner.PlanError as exc:
                raise OpenError(400, "BAD_REQUEST", str(exc)) from exc
            return planned
        words = "2 min before the first setup"
        which = planner.et_clock(park)
    window, fallbacks = planner.windows_for(day, park)
    return {
        "symbol": symbol, "date": day, "at": which,
        "anchor_et": which, "park_et": planner.et_clock(park, seconds=True), "park_ts": park,
        "park_words": words, "window": window, "fallback_windows": fallbacks,
    }


def _et_ts(day: str, hour: int, minute: int, second: int) -> int:
    found = date.fromisoformat(day)
    return int(datetime.combine(found, time(hour, minute, second), tzinfo=ET).timestamp())


def _trading_day(day: date) -> bool:
    from sim.trading_day import is_trading_day

    return bool(is_trading_day(day))


def _listening() -> bool:
    return commands.BOARD.listening()


def _venue() -> str:
    from sim.mode import venue

    return str(venue())


def _stake(current: str) -> dict[str, Any]:
    """Show's at-stake check, plus a live IBKR session that has not answered.

    ``POST /api/agent/show`` still treats a missing IBKR session as nothing at stake
    (``restart_check.ibkr`` returns []). This venue switch does not.
    """
    from agent_desk.safety import at_stake

    report = at_stake(current, switching=True, reloading=False)
    if current != "live" or not _live_ibkr_unreadable():
        return report
    unknown = [*(report.get("unknown") or []), {"kind": "orders", "error": "IBKR enabled but no session"}]
    return {**report, "unknown": unknown, "safe": False}


def _live_ibkr_unreadable() -> bool:
    """IBKR is enabled and the session is not ready. Disabled in config is readable."""
    from ibkr import client

    try:
        if not client.is_enabled():
            return False
        return not client.is_ready()
    except Exception:
        logger.exception("open in nova: could not read the IBKR session")
        return True


def _on_file(day: str) -> bool:
    from constants_sim import SIM_MASSIVE_TRADES
    from sim.massive_files import day_file

    return day_file(SIM_MASSIVE_TRADES, day) is not None


def _queue(args: dict, plan: dict) -> dict:
    """The same command ``POST /api/agent/show`` queues. The desk lands it."""
    return commands.BOARD.create("show", args, plan)


def _row_for(day: str, symbol: str) -> dict | None:
    from agent_desk import movers_read

    return movers_read.row_or_none(day, symbol)


def _setups_for(symbol: str, day: str) -> list:
    """Flat tops the review page already knows, when the review loader is on this machine."""
    found = _read_setups(symbol, day)
    return list(found) if isinstance(found, list) else []


def _read_setups(symbol: str, day: str):
    try:
        import nova_review_load as review_load
    except ImportError:
        logger.info("open in nova: review loader is not installed")
        return None
    try:
        body = review_load.load_review(symbol, day, "5m", "20:00")
    except Exception:
        logger.exception("open in nova: setups for %s %s were not readable", symbol, day)
        return None
    return body.get("setups") if isinstance(body, dict) else None
