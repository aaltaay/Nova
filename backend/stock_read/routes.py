"""The bot's read on one stock (ADR 036). Read-only: nothing here places, stages or cancels an order.

  GET /api/stock-read/{symbol}?entry=&stop=          the plan, the seven groups and every lane (polled)
  GET /api/stock-read/{symbol}/decisions?date=       one symbol's day as the bot saw it
  GET /api/stock-read/{symbol}/history               past runs and what Nova holds on it

Sync routes: FastAPI runs them on its worker threads, off the event loop (the bar store and the
journal are files). One read per (symbol, entry, stop) serves every poll inside
``STOCK_READ_CACHE_SEC``, so several open tabs of one symbol cost one read.
"""
from __future__ import annotations

import logging
import re
import threading
import time
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query

from constants_stock_read import STOCK_READ_CACHE_SEC, STOCK_READ_SCHEMA_VERSION
from scanner_wire import wire_safe
from stock_read import decisions, gather, history, read

router = APIRouter(tags=["stock_read"])
logger = logging.getLogger(__name__)
ET = ZoneInfo("America/New_York")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_cache: dict[tuple, tuple[float, dict[str, Any]]] = {}
_lock = threading.Lock()


def _symbol(raw: str) -> str:
    sym = (raw or "").strip().upper()
    if not sym or len(sym) > 12:
        raise HTTPException(400, "a symbol, up to 12 characters")
    return sym


def stock_read(symbol: str, *, entry: float | None = None, stop: float | None = None,
               now: float | None = None) -> dict[str, Any]:
    now = time.time() if now is None else now
    key = (symbol, entry, stop)
    with _lock:
        hit = _cache.get(key)
        if hit is not None and now - hit[0] < STOCK_READ_CACHE_SEC:
            return hit[1]
    body = read.build(gather.gather(symbol, now), entry=entry, stop=stop)
    with _lock:
        if len(_cache) > 64:
            _cache.clear()
        _cache[key] = (now, body)
    return body


@router.get("/api/stock-read/{symbol}/decisions")
def stock_read_decisions(symbol: str, date: str | None = Query(None, description="YYYY-MM-DD (ET); today by default")):
    sym = _symbol(symbol)
    now = time.time()
    day = date or datetime.fromtimestamp(now, ET).date().isoformat()
    if not _DATE.match(day):
        raise HTTPException(400, "date is YYYY-MM-DD")
    return wire_safe({"schema_version": STOCK_READ_SCHEMA_VERSION, **decisions.timeline(sym, day, now)})


@router.get("/api/stock-read/{symbol}/history")
def stock_read_history(symbol: str):
    sym = _symbol(symbol)
    now = time.time()
    summary = history.summary(sym, now) or {"daily": [], "runs": [], "daily_days": 0}
    facts = None
    try:
        from move_reason import facts as facts_mod

        facts = facts_mod.gather(sym, now)
    except Exception:
        logger.warning("stock read history: the facts of %s could not be read", sym, exc_info=True)
    return wire_safe({
        "schema_version": STOCK_READ_SCHEMA_VERSION, "symbol": sym, "generated_at": now,
        "daily": summary["daily"], "runs": summary["runs"], "split": (facts or {}).get("split"),
        "holdings": history.holdings(sym, now, facts),
    })


@router.get("/api/stock-read/{symbol}")
def stock_read_route(symbol: str, entry: float | None = Query(None, gt=0), stop: float | None = Query(None, gt=0)):
    return stock_read(_symbol(symbol), entry=entry, stop=stop)
