"""The bot's read on one stock (ADR 036). Read-only: nothing here places, stages or cancels an order.

  GET /api/stock-read/{symbol}?entry=&stop=&side=    the plan, the seven groups and every lane (polled);
                                                     side=short: your own plan is a short (ADR 048)
      &held_qty=&held_avg=&held_stop=&held_risk=&held_since=&held_side=   with ``held``: the trade you hold
                                                     (held_side=short: you hold it short)
  GET /api/stock-read/{symbol}/flush                 trial T1's 30 s tape reading (sensor rings only)
  GET /api/stock-read/{symbol}/decisions?date=       one symbol's day as the bot saw it
  GET /api/stock-read/{symbol}/past-setups?date=&tf= the day's setups that ended, and what price did next
                                                     (tf=5m: the 5-minute lanes')
  GET /api/stock-read/{symbol}/history               past runs and what Nova holds on it

Sync routes: FastAPI runs them on its worker threads, off the event loop (the bar store and the
journal are files). One read per (symbol, entry, stop) serves every poll inside
``STOCK_READ_CACHE_SEC``, so several open tabs of one symbol cost one read.

On a Sim replay desk (ADR 052) the read is the replay's at the playhead (``stock_read.replay_read``); a
cached read is served only for a playhead at or after its own and inside the cache time, so a rewind never
shows what came later. The day routes (past setups, decisions) read whole days and answer nothing there;
the history reads the days before the replayed one; the flush reading is the live tape's and is blind.
"""
from __future__ import annotations

import logging
import re
import threading
import time
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query

from constants_stock_read import STOCK_READ_CACHE_SEC, STOCK_READ_SCHEMA_VERSION
from hot_list import trading_day
from scanner_wire import wire_safe
from stock_read import decisions, flush, gather, history, past_setups, read, replay_read

router = APIRouter(tags=["stock_read"])
logger = logging.getLogger(__name__)
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_cache: dict[tuple, tuple[float, dict[str, Any], float]] = {}
# A day route's default is the trading day (the hot list's, from 04:00 ET), never the calendar date: from
# midnight to 04:00 the chart still shows the day before (#695).
_DAY = "YYYY-MM-DD; the trading day (from 04:00 ET) by default"
_lock = threading.Lock()


def _symbol(raw: str) -> str:
    sym = (raw or "").strip().upper()
    if not sym or len(sym) > 12:
        raise HTTPException(400, "a symbol, up to 12 characters")
    return sym


def _replay_desk() -> bool:
    from sim.mode import is_replay_desk

    try:
        return bool(is_replay_desk())
    except Exception:
        logger.warning("stock read: the Sim live edge is unreadable -- the desk counts as a replay", exc_info=True)
        return True


def stock_read(symbol: str, *, entry: float | None = None, stop: float | None = None,
               held: dict[str, Any] | None = None, now: float | None = None, side: str = "long") -> dict[str, Any]:
    replay = _replay_desk()
    if now is None:
        now = replay_read.playhead() if replay else time.time()
    key = (symbol, entry, stop, side, tuple(sorted((held or {}).items())), replay)
    wall = time.monotonic()
    with _lock:
        hit = _cache.get(key)
        # Fresh by the read's own clock (a rewind is never served a later read) and by the wall's (a paused
        # playhead still sees the Sim eyes catch up).
        if hit is not None and 0 <= now - hit[0] < STOCK_READ_CACHE_SEC and wall - hit[2] < STOCK_READ_CACHE_SEC:
            return hit[1]
    facts = replay_read.gather(symbol, now) if replay else gather.gather(symbol, now)
    body = read.build(facts, entry=entry, stop=stop, held=held, side=side)
    with _lock:
        if len(_cache) > 64:
            _cache.clear()
        _cache[key] = (now, body, wall)
    return body


@router.get("/api/stock-read/{symbol}/decisions")
def stock_read_decisions(symbol: str, date: str | None = Query(None, description=_DAY)):
    sym = _symbol(symbol)
    now = time.time()
    day = date or trading_day(now)
    if not _DATE.match(day):
        raise HTTPException(400, "date is YYYY-MM-DD")
    if _replay_desk():
        return wire_safe({"schema_version": STOCK_READ_SCHEMA_VERSION,
                          **replay_read.empty_day(sym, date, replay_read.playhead(), kind="decisions")})
    return wire_safe({"schema_version": STOCK_READ_SCHEMA_VERSION, **decisions.timeline(sym, day, now)})


@router.get("/api/stock-read/{symbol}/past-setups")
def stock_read_past_setups(symbol: str, date: str | None = Query(None, description=_DAY),
                           tf: str = Query("1m", description="1m: the setups in play's; 5m: the 5-minute lanes'")):
    sym = _symbol(symbol)
    if tf not in ("1m", "5m"):
        raise HTTPException(400, "tf is 1m or 5m")
    now = time.time()
    today = trading_day(now)
    day = date or today
    if not _DATE.match(day):
        raise HTTPException(400, "date is YYYY-MM-DD")
    if _replay_desk():
        return wire_safe({"schema_version": STOCK_READ_SCHEMA_VERSION,
                          **replay_read.empty_day(sym, date, replay_read.playhead(), kind="past")})
    return wire_safe({"schema_version": STOCK_READ_SCHEMA_VERSION,
                      **past_setups.read(sym, day, now, today=day == today, five=tf == "5m")})


@router.get("/api/stock-read/{symbol}/history")
def stock_read_history(symbol: str):
    sym = _symbol(symbol)
    replay = _replay_desk()
    now = replay_read.playhead() if replay else time.time()
    summary = history.summary(sym, now, replay=replay) or {"daily": [], "runs": [], "daily_days": 0}
    facts = None
    try:
        from move_reason import facts as facts_mod

        facts = None if replay else facts_mod.gather(sym, now)
    except Exception:
        logger.warning("stock read history: the facts of %s could not be read", sym, exc_info=True)
    return wire_safe({
        "schema_version": STOCK_READ_SCHEMA_VERSION, "symbol": sym, "generated_at": now,
        "daily": summary["daily"], "runs": summary["runs"], "split": (facts or {}).get("split"),
        "holdings": [] if replay else history.holdings(sym, now, facts), "replay": replay,
    })


@router.get("/api/stock-read/{symbol}/flush")
def stock_read_flush(symbol: str):
    sym = _symbol(symbol)
    if _replay_desk():
        return wire_safe(flush.blind(sym, replay_read.playhead()))     # the live tape is not the replay's
    return wire_safe(flush.reading(sym, time.time()))


@router.get("/api/stock-read/{symbol}")
def stock_read_route(symbol: str, entry: float | None = Query(None, gt=0), stop: float | None = Query(None, gt=0),
                     held_qty: float | None = Query(None, gt=0), held_avg: float | None = Query(None, gt=0),
                     held_stop: float | None = Query(None, gt=0), held_risk: float | None = Query(None, gt=0),
                     held_since: float | None = Query(None, gt=0),
                     side: Literal["long", "short"] = Query("long", description="your own plan's side"),
                     held_side: Literal["long", "short"] = Query("long", description="the side you hold")):
    held = ({"qty": held_qty, "avg": held_avg, "stop": held_stop, "risk": held_risk, "since": held_since,
             "side": held_side} if held_qty and held_avg else None)
    return stock_read(_symbol(symbol), entry=entry, stop=stop, held=held, side=side)
