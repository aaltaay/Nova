"""Followed traders' routes: the gate, the day, records, the feed's images and reads. Read-only; none waits on
IBKR.

``app_routers`` includes this router only when ``NOVA_FOLLOW_FEED_URL`` is set (``config.enabled``); unset, none of
these routes exists and nothing asks the feed. Shapes: architecture/schema/followed-traders.md.
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from datetime import date as Date, timedelta
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse, Response

from followed_traders import config, exits, feed, keeper, lines, pricing, reads, sightings, tickers, view
from followed_traders.constants_followed import (
    FOLLOWED_ERR_BAD_DATE,
    FOLLOWED_ERR_BAD_RANGE,
    FOLLOWED_ERR_BAD_READS,
    FOLLOWED_ERR_FEED_UNREACHABLE,
    FOLLOWED_LEFT_BAR_SEC,
    FOLLOWED_MAX_LINES,
    FOLLOWED_READS_MAX,
    FOLLOWED_RECORD_RANGES,
    FOLLOWED_RECORD_WEEK_DAYS,
    FOLLOWED_SCHEMA_VERSION,
    FOLLOWED_SEEN_CACHE_SEC,
    FOLLOWED_WANTED_SEC,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["followed-traders"])
NAME_RE = re.compile(r"^[0-9a-f]{32}$")
_release_handle: asyncio.TimerHandle | None = None
# The read logs asked of the feed: date -> (when, the log or None, kept for good). A day before the desk's today is
# finished, so its log (or the feed's 404) is kept; today's is asked again after FOLLOWED_SEEN_CACHE_SEC.
_log_cache: dict[str, tuple[float, list[dict[str, Any]] | None, bool]] = {}


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
        return {**view.feed_down(exc.state, exc.message, date, now), "keeper": keeper.view(now)}
    day = {**day, "today": today}
    prices = prices_state(day) if quotes else {"state": "not_asked", "why": "asked without prices"}
    seen = await asyncio.to_thread(_seen, base, day, now)
    ready = _ibkr_ready()
    ticker_for = _ticker_for(now, ready)
    # A trader who left the bar closed every trade then (view.closed_on_leaving): no line is held for those. Nor for a
    # trade whose ticker may be glued to its price until the check settles it; a corrected one holds its own ticker's.
    open_trades = sorted((tickers.shown(t, ticker_for(t)) for t in day["trades"]
                          if t["status"] == "open" and not view.left_bar(seen, t["trader"])
                          and tickers.settled(ticker_for(t))),
                         key=lambda t: t["entry_ts"], reverse=True)
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

    body = view.compose(day, now=now, prices=prices, now_for=now_for, exit_for=_exit_for(now, ready),
                        resets_at=resets_at, seen=seen, ticker_for=ticker_for)
    exits.pump(now, ibkr_ready=ready)
    return {**body, "keeper": keeper.view(now)}


def seen(base: str, day: dict[str, Any], now: float) -> dict[str, dict[str, Any]] | None:
    """The page's own sightings for ``day`` -- the Live Trader bot reads the same (ADR 055)."""
    return _seen(base, day, now)


def ticker_for(now: float, ready: bool):
    """The page's own ticker check for an answer -- the Live Trader bot reads the same (ADR 055)."""
    return _ticker_for(now, ready)


def ibkr_ready() -> bool:
    return _ibkr_ready()


def read_log(base: str, date: str, now: float) -> list[dict[str, Any]] | None:
    """The day's read log as the page reads it (cached) -- the Live Trader bot reads the same (ADR 055)."""
    return _read_log(base, date, now)


def _seen(base: str, day: dict[str, Any], now: float) -> dict[str, dict[str, Any]] | None:
    """Each of the day's traders' sighting on the bar, from the feed's read log; None without one."""
    log = _read_log(base, day["date"], now, final=day["date"] < day["today"])
    if log is None:
        return None
    status = day.get("status") or {}
    names = [t["trader"] for t in day["trades"]] + [s["trader"] for s in status.get("positions") or ()]
    latest = status.get("clock") if day["date"] == day["today"] else None
    return sightings.sightings(log, date=day["date"], traders=names, latest_clock=latest,
                               left_after_sec=FOLLOWED_LEFT_BAR_SEC)


def _seen_by_date(base: str, trades: list[dict[str, Any]], today: str,
                  now: float) -> dict[str, dict[str, dict[str, Any]]]:
    """Each day's sightings, for the days of ``trades`` with a trade still open (no other day needs one)."""
    out = {}
    for date in sorted({t["date"] for t in trades if t["status"] == "open"}):
        log = _read_log(base, date, now, final=date < today)
        if log is not None:
            out[date] = sightings.sightings(log, date=date, traders=[t["trader"] for t in trades if t["date"] == date],
                                            latest_clock=None, left_after_sec=FOLLOWED_LEFT_BAR_SEC)
    return out


def _read_log(base: str, date: str, now: float, *, final: bool = False) -> list[dict[str, Any]] | None:
    """The day's read log, asked of the feed at most every ``FOLLOWED_SEEN_CACHE_SEC``, and once for a ``final``
    day (before the desk's today) that answered."""
    got = _log_cache.get(date)
    if got is not None and (got[2] or now - got[0] < FOLLOWED_SEEN_CACHE_SEC):
        return got[1]
    log: list[dict[str, Any]] | None
    answered = True
    try:
        log = feed.fetch_reads(base, date)
    except feed.FeedError as exc:
        answered = exc.state == "missing"
        if not answered:
            logger.warning("followed traders: the read log for %s could not be read: %s", date, exc.message)
        log = None
    _log_cache[date] = (now, log, final and answered)
    return log


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
    seen_by_date = await asyncio.to_thread(_seen_by_date, base, got["trades"], desk_day(now)[0], now)
    ready = _ibkr_ready()
    body = view.records(got, span=range, now=now, exit_for=_exit_for(now, ready), seen_by_date=seen_by_date,
                        ticker_for=_ticker_for(now, ready))
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


def _ticker_for(now: float, ready: bool):
    """A trade's ticker check (``tickers.check``) over IBKR's tape at its entry, read and kept as an exit's is
    (``exits.view``), once per trade in an answer; pending says why while IBKR is not connected."""
    checked: dict[tuple, dict[str, Any] | None] = {}

    def ticker_for(trade: dict[str, Any]) -> dict[str, Any] | None:
        key = (trade["trader"], trade["side"], trade["symbol"], trade["entry_ts"])
        if key not in checked:
            def tape_at(symbol: str) -> dict[str, Any]:
                got = exits.view(symbol, trade["entry_ts"], trade["entry_since_ts"], now)
                return {**got, "why": "IBKR is not connected"} if got["state"] == "pending" and not ready else got

            checked[key] = tickers.check(trade, tape_at)
        return checked[key]

    return ticker_for


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
