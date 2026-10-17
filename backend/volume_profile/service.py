"""The profiles ``GET /api/volume-profile/{symbol}`` answers (ADR 058, ``architecture/schema/volume-profile.md``).

Today's from the chart store's 1-minute bars (the Trader's 1-minute pane fills them; no IBKR request). Yesterday's from
the chart store when it holds that session, else from one paced IBKR request (``ibkr_minutes``), one at a time per
stock and day however many windows ask; the finished profile is kept in memory (``VP_CACHE_MAX``), never on disk.
Every miss is a stated empty with its reason, never a zero profile.
"""
from __future__ import annotations

import asyncio
import logging
from collections import OrderedDict
from datetime import date, datetime, time, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo

from constants_volume_profile import (
    VP_CACHE_MAX,
    VP_EXTENDED_CLOSE_MIN,
    VP_EXTENDED_OPEN_MIN,
    VP_IB_TIMEOUT_SEC,
    VP_MAX_MINUTES,
    VP_RTH_CLOSE_MIN,
    VP_RTH_OPEN_MIN,
    VP_SCHEMA_VERSION,
    VP_SESSION_MIN_BARS,
    VP_SOURCE_BARS_1M,
)
from volume_profile.profile import Bar, Profile, build

logger = logging.getLogger(__name__)
_ET = ZoneInfo("America/New_York")

Kind = Literal["today", "yesterday"]

_cache: OrderedDict[tuple[str, str], dict[str, Any]] = OrderedDict()
_inflight: dict[tuple[str, str], asyncio.Task] = {}


class BadRequest(ValueError):
    """A query the route answers 422 with these words."""


def reset_for_testing() -> None:
    _cache.clear()
    _inflight.clear()


def _at(day: date, minute: int) -> float:
    return datetime.combine(day, time(minute // 60, minute % 60), tzinfo=_ET).timestamp()


def exchange_day(now: float | None = None) -> date:
    """The last exchange day on the ET wall clock (today on a trading day)."""
    from sim.trading_day import last_open_day

    wall = datetime.now(_ET) if now is None else datetime.fromtimestamp(now, _ET)
    return last_open_day(wall.date())


def _wire(symbol: str, kind: Kind, day: date, start: float, end: float, p: Profile | None, *,
          error: str | None = None, filling: bool = False) -> dict[str, Any]:
    base: dict[str, Any] = {
        "schema_version": VP_SCHEMA_VERSION, "enabled": True, "symbol": symbol, "kind": kind,
        "day": day.isoformat(), "from": start, "to": end, "source": VP_SOURCE_BARS_1M,
    }
    if p is None:
        return {**base, "bars": 0, "row_size": None, "low": None, "high": None, "total_volume": None, "poc": None,
                "vah": None, "val": None, "poc_row": None, "vah_row": None, "val_row": None, "histogram": [],
                "filling": filling, "error": error or "No 1-minute bars in this stretch"}
    rows = [[round(p.low + i * p.row_size, 6), round(u, 2), round(d, 2)]
            for i, (u, d) in enumerate(zip(p.up, p.down, strict=True))]
    return {**base, "bars": p.bars, "row_size": p.row_size, "low": p.low, "high": p.high,
            "total_volume": round(p.total, 2), "poc": round(p.poc, 4), "vah": round(p.vah, 4), "val": round(p.val, 4),
            "poc_row": p.poc_row, "vah_row": p.vah_row, "val_row": p.val_row, "histogram": rows,
            "filling": False, "error": None}


def _stored_minutes(symbol: str, start: float, end: float) -> list[Bar]:
    """The chart store's 1-minute bars starting in ``[start, end)``. A SQLite read: run it in a worker thread."""
    import bars_store
    from ibkr.historical_derive import bar_unix

    got = bars_store.read(symbol, "1Min", VP_MAX_MINUTES, from_ts=start, through_ts=end - 1)
    out: list[Bar] = []
    for b in (got or {}).get("bars") or []:
        ts = bar_unix(b)
        if ts is None or not start <= ts < end:
            continue
        out.append(Bar(t=ts, o=float(b["o"]), h=float(b["h"]), l=float(b["l"]), c=float(b["c"]), v=float(b["v"])))
    return out


async def _ibkr_minutes(symbol: str, day: date) -> list[Bar]:
    from ibkr import client
    from ibkr.loop_supervisor import on_ib
    from volume_profile.ibkr_minutes import session_minutes

    if not client.is_ready():
        raise ConnectionError("IBKR is not connected")
    return await on_ib(session_minutes(symbol, day, timeout=VP_IB_TIMEOUT_SEC), VP_IB_TIMEOUT_SEC + 5.0,
                       label="volume_profile.session_minutes")


def _settled(key: tuple[str, str], done: asyncio.Task) -> None:
    """The request is over: the next ask may send another. Its outcome was handed to every waiter; one whose browser
    left still has it read here, so it is never an unretrieved exception."""
    if _inflight.get(key) is done:
        del _inflight[key]
    if not done.cancelled() and done.exception() is not None:
        logger.info("volume profile: %s %s 1-minute read ended: %s", key[0], key[1], done.exception())


async def _yesterday(symbol: str, session: date) -> dict[str, Any]:
    from ibkr.historical_service import HistoricalShed

    start, end = _at(session, VP_RTH_OPEN_MIN), _at(session, VP_RTH_CLOSE_MIN)
    key = (symbol, session.isoformat())
    if key in _cache:
        _cache.move_to_end(key)
        return _cache[key]
    bars = await asyncio.to_thread(_stored_minutes, symbol, start, end)
    if len(bars) < VP_SESSION_MIN_BARS:
        task = _inflight.get(key)
        if task is None:
            task = asyncio.create_task(_ibkr_minutes(symbol, session), name=f"volume_profile.{symbol}.{session}")
            _inflight[key] = task
            task.add_done_callback(lambda done: _settled(key, done))
        try:
            bars = await asyncio.shield(task)
        except HistoricalShed as exc:
            return _wire(symbol, "yesterday", session, start, end, None, filling=True,
                         error=f"Reading {session.isoformat()}'s 1-minute bars from IBKR waits: {exc}")
        except (ConnectionError, asyncio.TimeoutError) as exc:
            return _wire(symbol, "yesterday", session, start, end, None, filling=True,
                         error=f"IBKR did not answer for {session.isoformat()}'s 1-minute bars ({type(exc).__name__}: {exc})")
        except ValueError as exc:
            return _wire(symbol, "yesterday", session, start, end, None, error=str(exc))
        bars = [b for b in bars if start <= b.t < end]
    answer = _wire(symbol, "yesterday", session, start, end, build(bars),
                   error=f"IBKR has no 1-minute bars for {session.isoformat()}'s regular session")
    if answer["histogram"]:
        _cache[key] = answer
        while len(_cache) > VP_CACHE_MAX:
            _cache.popitem(last=False)
    return answer


async def profile(symbol: str, kind: Kind, day: date | None, anchor: float | None) -> dict[str, Any]:
    from sim.mode import is_replay_desk
    from sim.trading_day import last_open_day

    session = day or exchange_day()
    if is_replay_desk():
        start, end = _at(session, VP_RTH_OPEN_MIN), _at(session, VP_RTH_CLOSE_MIN)
        return _wire(symbol, kind, session, start, end, None,
                     error="The volume profile reads live IBKR bars, so it is not drawn on a Sim replay")
    if kind == "yesterday":
        return await _yesterday(symbol, last_open_day(session - timedelta(days=1)))
    open_, close = _at(session, VP_EXTENDED_OPEN_MIN), _at(session, VP_EXTENDED_CLOSE_MIN)
    start = _at(session, VP_RTH_OPEN_MIN) if anchor is None else float(anchor)
    if not open_ <= start < close:
        raise BadRequest(f"anchor must fall inside {session.isoformat()} 04:00-20:00 ET")
    bars = await asyncio.to_thread(_stored_minutes, symbol, start, close)
    return _wire(symbol, "today", session, start, close, build(bars),
                 error=f"No 1-minute bars for {symbol} since the anchor yet")
