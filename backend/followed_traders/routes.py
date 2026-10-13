"""Followed traders' routes: the gate, the day, an evidence image. Read-only; none waits on IBKR.

``app_routers`` includes this router only when ``NOVA_FOLLOW_FEED_URL`` is set (``config.enabled``); unset, none of
these routes exists and nothing asks the feed. Shapes: architecture/schema/followed-traders.md.
"""
from __future__ import annotations

import asyncio
import re
import time
from datetime import date as Date, datetime, timedelta
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse, Response

from followed_traders import config, exits, feed, lines, pricing, view
from followed_traders.constants_followed import (
    FOLLOWED_ERR_BAD_DATE,
    FOLLOWED_ERR_BAD_RANGE,
    FOLLOWED_ERR_FEED_UNREACHABLE,
    FOLLOWED_MAX_LINES,
    FOLLOWED_RECORD_RANGES,
    FOLLOWED_RECORD_WEEK_DAYS,
    FOLLOWED_SCHEMA_VERSION,
    FOLLOWED_WANTED_SEC,
)

router = APIRouter(tags=["followed-traders"])
NAME_RE = re.compile(r"^[0-9a-f]{32}$")
_release_handle: asyncio.TimerHandle | None = None


@router.get("/api/followed-traders/config")
def get_config():
    return {"schema_version": FOLLOWED_SCHEMA_VERSION, "enabled": config.enabled()}


@router.get("/api/followed-traders/day")
async def get_day(date: str | None = None):
    if date is not None and not feed.DATE_RE.match(date):
        return _error(400, FOLLOWED_ERR_BAD_DATE, "date must be YYYY-MM-DD", field="date")
    base = config.feed_url()
    if base is None:
        return Response(status_code=404)
    now = time.time()
    try:
        day = await asyncio.to_thread(feed.fetch_day, base, date)
    except feed.FeedError as exc:
        return view.feed_down(exc.state, exc.message, date, now)
    prices = prices_state(day)
    open_trades = sorted((t for t in day["trades"] if t["status"] == "open"), key=lambda t: t["entry_ts"],
                         reverse=True)
    line_syms, over_cap = lines.plan([t["symbol"] for t in open_trades])
    quotes: dict[str, dict[str, Any]] = {}
    if prices["state"] == "live":
        lines.want(line_syms, now)
        _arm_release()
        quotes = lines.quotes(line_syms)

    def now_for(trade: dict[str, Any]) -> dict[str, Any]:
        sym = trade["symbol"]
        if not pricing.priceable(sym):
            return lines.now_state("no_line", why=f"{sym!r} is not a ticker Nova can ask IBKR for")
        if sym in over_cap:
            return lines.now_state("no_line", why=f"more than {FOLLOWED_MAX_LINES} open positions")
        return quotes.get(sym) or lines.now_state("waiting", why="opening IBKR's line")

    ready = _ibkr_ready()
    body = view.compose(day, now=now, prices=prices, now_for=now_for, exit_for=_exit_for(now, ready))
    exits.pump(now, ibkr_ready=ready)
    return body


@router.get("/api/followed-traders/record")
async def get_record(range: str = "week", date: str | None = None):  # noqa: A002 -- the wire's own name
    """Each trader's record over a day, the week ending on it, or every day the feed has."""
    if range not in FOLLOWED_RECORD_RANGES:
        return _error(400, FOLLOWED_ERR_BAD_RANGE, f"range must be one of {', '.join(FOLLOWED_RECORD_RANGES)}",
                      field="range")
    if date is not None and not feed.DATE_RE.match(date):
        return _error(400, FOLLOWED_ERR_BAD_DATE, "date must be YYYY-MM-DD", field="date")
    base = config.feed_url()
    if base is None:
        return Response(status_code=404)
    now = time.time()
    end = date or _today_et()
    start = record_start(range, end)
    try:
        got = await asyncio.to_thread(feed.fetch_trades, base, start, end)
    except feed.FeedError as exc:
        return view.records_down(exc.state, exc.message, range, now)
    ready = _ibkr_ready()
    body = view.records(got, span=range, now=now, exit_for=_exit_for(now, ready))
    exits.pump(now, ibkr_ready=ready)
    return body


def record_start(span: str, end: str) -> str | None:
    """The first day of a record ending on ``end``: itself, the week's first, or None (every day)."""
    if span == "day":
        return end
    if span == "week":
        return (Date.fromisoformat(end) - timedelta(days=FOLLOWED_RECORD_WEEK_DAYS - 1)).isoformat()
    return None


@router.get("/api/followed-traders/evidence/{date}/frames/{name}.jpg")
async def get_evidence(date: str, name: str):
    base = config.feed_url()
    if base is None or not feed.DATE_RE.match(date) or not NAME_RE.match(name):
        return Response(status_code=404)
    try:
        body = await asyncio.to_thread(feed.fetch_evidence, base, date, name)
    except feed.FeedError as exc:
        return _error(502, FOLLOWED_ERR_FEED_UNREACHABLE, exc.message)
    # An event's image never changes once written.
    return Response(body, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=86400"})


def _exit_for(now: float, ready: bool):
    """A closed trade's exit as known now (``exits.view``); pending says why while IBKR is not connected."""
    def exit_for(trade: dict[str, Any]) -> dict[str, Any]:
        sym = trade["symbol"]
        if not pricing.priceable(sym):
            return exits.stated("unavailable", from_ts=trade["exit_since_ts"], to_ts=trade["exit_ts"],
                                why=f"{sym!r} is not a ticker Nova can ask IBKR for")
        got = exits.view(sym, trade["exit_ts"], trade["exit_since_ts"], now)
        if got["state"] == "pending" and not ready:
            return {**got, "why": "IBKR is not connected"}
        return got

    return exit_for


def _today_et() -> str:
    from sim.session_clock import ET

    return datetime.now(ET).date().isoformat()


def prices_state(day: dict[str, Any]) -> dict[str, Any]:
    if day["date"] != day["today"]:
        return {"state": "past_day", "why": f"{day['date']} is not the feed's today; nothing is priced now"}
    if _replay_desk():
        return {"state": "replay_desk", "why": "the desk is on a Sim replay, whose quotes are the recording's"}
    if not _ibkr_ready():
        return {"state": "ibkr_down", "why": "IBKR is not connected"}
    return {"state": "live", "why": None}


def _arm_release() -> None:
    """Let the lines go ``FOLLOWED_WANTED_SEC`` after the last request (checked again until they are)."""
    global _release_handle
    if _release_handle is not None:
        _release_handle.cancel()
    _release_handle = asyncio.get_running_loop().call_later(FOLLOWED_WANTED_SEC + 1.0, _release_tick)


def _release_tick() -> None:
    global _release_handle
    _release_handle = None
    if not lines.release_if_idle(time.time()):
        _release_handle = asyncio.get_running_loop().call_later(FOLLOWED_WANTED_SEC, _release_tick)


def _ibkr_ready() -> bool:
    from ibkr import client

    return client.is_ready()


def _replay_desk() -> bool:
    from sim.mode import is_replay_desk

    return bool(is_replay_desk())


def _error(status: int, reason: str, error: str, *, field: str | None = None) -> JSONResponse:
    detail = {"reason": reason, "error": error}
    if field:
        detail["field"] = field
    return JSONResponse(status_code=status, content={"detail": detail})
