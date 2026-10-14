"""Followed traders' routes: the gate, the day, records, the feed's images and reads. Read-only; none waits on
IBKR.

``app_routers`` includes this router only when ``NOVA_FOLLOW_FEED_URL`` is set (``config.enabled``); unset, none of
these routes exists and nothing asks the feed. Shapes: architecture/schema/followed-traders.md.
"""
from __future__ import annotations

import asyncio
import re
import time
from datetime import date as Date, timedelta
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse, Response

from followed_traders import config, exits, feed, lines, pricing, reads, view
from followed_traders.constants_followed import (
    FOLLOWED_ERR_BAD_DATE,
    FOLLOWED_ERR_BAD_RANGE,
    FOLLOWED_ERR_BAD_READS,
    FOLLOWED_ERR_FEED_UNREACHABLE,
    FOLLOWED_MAX_LINES,
    FOLLOWED_READS_MAX,
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
async def get_day(date: str | None = None, quotes: int = 1):
    """The day; ``quotes=0`` reads the feed only and opens no IBKR line (the desk's trade toasts)."""
    if date is not None and not feed.DATE_RE.match(date):
        return _error(400, FOLLOWED_ERR_BAD_DATE, "date must be YYYY-MM-DD", field="date")
    base = config.feed_url()
    if base is None:
        return Response(status_code=404)
    now = time.time()
    today, resets_at = desk_day(now)
    try:
        # The desk's today is asked by name: the feed's own default turns at midnight, the desk's at 04:00 ET.
        day = await asyncio.to_thread(feed.fetch_day, base, date or today)
    except feed.FeedError as exc:
        return view.feed_down(exc.state, exc.message, date, now)
    day = {**day, "today": today}
    prices = prices_state(day) if quotes else {"state": "not_asked", "why": "asked without prices"}
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
    body = view.compose(day, now=now, prices=prices, now_for=now_for, exit_for=_exit_for(now, ready),
                        resets_at=resets_at)
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
    end = date or desk_day(now)[0]
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


@router.get("/api/followed-traders/live/{name}.jpg")
async def get_live(name: str):
    """A trader's slot as the feed last saw it; it changes every few seconds, so it is never cached."""
    return await _image(lambda base: feed.fetch_live(base, name), name, cache="no-store")


@router.get("/api/followed-traders/faces/{date}/{name}.jpg")
async def get_face(date: str, name: str):
    if not feed.DATE_RE.match(date):
        return Response(status_code=404)
    return await _image(lambda base: feed.fetch_face(base, date, name), name, cache="private, max-age=86400")


async def _image(fetch, name: str, *, cache: str):
    base = config.feed_url()
    if base is None or not feed.NAME_RE.match(name):
        return Response(status_code=404)
    try:
        body = await asyncio.to_thread(fetch, base)
    except feed.FeedError as exc:
        if exc.state == "missing":
            return Response(status_code=404)
        return _error(502, FOLLOWED_ERR_FEED_UNREACHABLE, exc.message)
    return Response(body, media_type="image/jpeg", headers={"Cache-Control": cache})


@router.get("/api/followed-traders/reads")
async def get_reads(date: str, trader: str, from_ts: float, to_ts: float):
    """What the feed read off one trader's slot between two times, so a trade can be checked against its images."""
    if not feed.DATE_RE.match(date):
        return _error(400, FOLLOWED_ERR_BAD_DATE, "date must be YYYY-MM-DD", field="date")
    if not trader or len(trader) > 32 or not (from_ts <= to_ts):
        return _error(400, FOLLOWED_ERR_BAD_READS, "trader is required and from_ts must not be after to_ts")
    base = config.feed_url()
    if base is None:
        return Response(status_code=404)
    now = time.time()
    head = {"schema_version": FOLLOWED_SCHEMA_VERSION, "generated_at": round(now, 3), "date": date,
            "trader": trader}
    try:
        log = await asyncio.to_thread(feed.fetch_reads, base, date)
    except feed.FeedError as exc:
        if exc.state == "missing":
            return {**head, "feed": {"state": "ok", "error": None}, "available": False,
                    "why": "the feed keeps no read log for that day", "reads": [], "truncated": False}
        return {**head, "feed": {"state": exc.state, "error": exc.message}, "available": False, "why": None,
                "reads": [], "truncated": False}
    got = reads.trader_reads(log, date=date, trader=trader, from_ts=from_ts, to_ts=to_ts,
                             max_reads=FOLLOWED_READS_MAX)
    return {**head, "feed": {"state": "ok", "error": None}, "available": True, "why": None, **got}


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


def desk_day(now: float) -> tuple[str, float]:
    """The desk's trading day at ``now`` and the epoch second it ends: the ET date whose 04:00 ET has passed, turning
    at the next 04:00 ET -- the premarket open the rest of the desk rolls at (``practice.clock``)."""
    from practice.clock import at, day_start_ts

    start = at(day_start_ts(now))
    return start.date().isoformat(), (start + timedelta(days=1)).timestamp()


def prices_state(day: dict[str, Any]) -> dict[str, Any]:
    if day["date"] != day["today"]:
        return {"state": "past_day", "why": f"{day['date']} is not today; nothing is priced now"}
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
