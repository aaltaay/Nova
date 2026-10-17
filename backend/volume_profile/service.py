"""The profiles ``GET /api/volume-profile/{symbol}`` answers (ADR 058, ``architecture/schema/volume-profile.md``).

One feed, the desk's: live, today's from the chart store's 1-minute bars (the Trader's 1-minute pane fills them; no
IBKR request) and yesterday's from the chart store when it holds that session, else from one paced IBKR request
(``ibkr_minutes``). On a Sim replay, what the replay's chart reads (amendment 2026-10-17): today's from the replay's own
1-minute bars up to the playhead, yesterday's on a Massive replay from the same Massive files (``massive_minutes``).
A past session is read once per feed, stock and day however many windows ask, and its profile kept in memory
(``VP_CACHE_MAX``), never on disk. Every miss is a stated empty with its reason, never a zero profile.
"""
from __future__ import annotations

import asyncio
import logging
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from datetime import date, datetime, time, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo

from constants_volume_profile import (
    VP_CACHE_MAX,
    VP_EXTENDED_CLOSE_MIN,
    VP_EXTENDED_OPEN_MIN,
    VP_FEED_IBKR,
    VP_FEED_MASSIVE,
    VP_IB_TIMEOUT_SEC,
    VP_MASSIVE_WAIT_SEC,
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
Key = tuple[str, str, str]  # (feed, symbol, ISO day)

_cache: OrderedDict[Key, dict[str, Any]] = OrderedDict()
_inflight: dict[Key, asyncio.Task] = {}


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


def _wire(symbol: str, kind: Kind, day: date, start: float, end: float, p: Profile | None, *, feed: str,
          error: str | None = None, filling: bool = False) -> dict[str, Any]:
    base: dict[str, Any] = {
        "schema_version": VP_SCHEMA_VERSION, "enabled": True, "symbol": symbol, "kind": kind,
        "day": day.isoformat(), "from": start, "to": end, "source": VP_SOURCE_BARS_1M, "feed": feed,
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


def _bars(rows: list[dict], start: float, end: float) -> list[Bar]:
    from ibkr.historical_derive import bar_unix

    out: list[Bar] = []
    for b in rows:
        ts = bar_unix(b)
        if ts is None or not start <= ts < end:
            continue
        out.append(Bar(t=ts, o=float(b["o"]), h=float(b["h"]), l=float(b["l"]), c=float(b["c"]), v=float(b["v"])))
    return out


def _stored_minutes(symbol: str, start: float, end: float) -> list[Bar]:
    """The chart store's 1-minute bars starting in ``[start, end)``. A SQLite read: run it in a worker thread."""
    import bars_store

    got = bars_store.read(symbol, "1Min", VP_MAX_MINUTES, from_ts=start, through_ts=end - 1)
    return _bars((got or {}).get("bars") or [], start, end)


def _replay_minutes(symbol: str, start: float, end: float) -> tuple[list[Bar], str]:
    """The replay's own 1-minute bars in ``[start, end)`` -- what its 5-minute pane draws, none after the playhead --
    and who drew them. Run it in a worker thread."""
    from constants_sim import SIM_MASSIVE_SOURCE
    from sim.chart_replay import fetch_replay_bars

    got = fetch_replay_bars(symbol, "1Min", VP_MAX_MINUTES)
    source = str(got.get("source") or VP_FEED_IBKR)
    return _bars(got.get("bars") or [], start, end), VP_FEED_MASSIVE if source == SIM_MASSIVE_SOURCE else source


def _massive_replay(symbol: str) -> bool:
    """A Massive window of this stock is the loaded replay: its yesterday comes from the same files."""
    from sim import history_playback

    loaded = history_playback.status()
    return history_playback.is_massive(loaded) and (loaded or {}).get("symbol") == symbol


async def _ibkr_minutes(symbol: str, day: date) -> list[Bar]:
    from ibkr import client
    from ibkr.loop_supervisor import on_ib
    from volume_profile.ibkr_minutes import session_minutes

    if not client.is_ready():
        raise ConnectionError("IBKR is not connected")
    return await on_ib(session_minutes(symbol, day, timeout=VP_IB_TIMEOUT_SEC), VP_IB_TIMEOUT_SEC + 5.0,
                       label="volume_profile.session_minutes")


async def _massive_minutes(symbol: str, day: date) -> list[Bar] | None:
    from volume_profile.massive_minutes import session_minutes

    return await asyncio.to_thread(session_minutes, symbol, day)


def _settled(key: Key, done: asyncio.Task) -> None:
    """The read is over: the next ask may start another. Its outcome was handed to every waiter; one whose browser
    left still has it read here, so it is never an unretrieved exception."""
    if _inflight.get(key) is done:
        del _inflight[key]
    if not done.cancelled() and done.exception() is not None:
        logger.info("volume profile: %s %s %s 1-minute read ended: %s", *key, done.exception())


def _once(key: Key, read: Callable[[], Awaitable[Any]]) -> asyncio.Task:
    """The one read in flight for ``key``, started if none is."""
    task = _inflight.get(key)
    if task is None:
        task = asyncio.create_task(read(), name=f"volume_profile.{'.'.join(key)}")
        _inflight[key] = task
        task.add_done_callback(lambda done: _settled(key, done))
    return task


async def _ibkr_session(symbol: str, session: date, start: float, end: float) -> tuple[list[Bar] | None, dict | None]:
    """The session's bars from the chart store, else IBKR: ``(bars, None)``, or ``(None, stated empty)``."""
    from ibkr.historical_service import HistoricalShed

    bars = await asyncio.to_thread(_stored_minutes, symbol, start, end)
    if len(bars) >= VP_SESSION_MIN_BARS:
        return bars, None
    day = session.isoformat()
    try:
        return await _ibkr_minutes(symbol, session), None
    except HistoricalShed as exc:
        return None, dict(filling=True, error=f"Reading {day}'s 1-minute bars from IBKR waits: {exc}")
    except (ConnectionError, asyncio.TimeoutError) as exc:
        return None, dict(filling=True, error=f"IBKR did not answer for {day}'s 1-minute bars ({type(exc).__name__}: {exc})")
    except ValueError as exc:
        return None, dict(error=str(exc))


async def _massive_session(symbol: str, session: date) -> tuple[list[Bar] | None, dict | None]:
    """The session's bars from the Massive files: ``(bars, None)``, or ``(None, stated empty)``."""
    day = session.isoformat()
    try:
        bars = await _massive_minutes(symbol, session)
    except Exception as exc:  # a damaged or unreadable day file: say so, never a zero profile
        logger.warning("volume profile: Massive minutes for %s %s unreadable", symbol, day, exc_info=True)
        return None, dict(error=f"The Massive files for {day} could not be read ({type(exc).__name__}: {exc})")
    if bars is None:
        return None, dict(error=f"The Massive files hold no 1-minute bars for {day}")
    return bars, None


async def _read_session(symbol: str, session: date, feed: str) -> dict[str, Any]:
    """Read a past session from its feed and build its profile, kept in memory when there is one -- by the read
    itself, so a read that outlives every ask that waited for it is still kept for the next."""
    start, end = _at(session, VP_RTH_OPEN_MIN), _at(session, VP_RTH_CLOSE_MIN)
    if feed == VP_FEED_MASSIVE:
        bars, empty = await _massive_session(symbol, session)
    else:
        bars, empty = await _ibkr_session(symbol, session, start, end)
    if bars is None:
        return _wire(symbol, "yesterday", session, start, end, None, feed=feed, **(empty or {}))
    who = "the Massive files have" if feed == VP_FEED_MASSIVE else "IBKR has"
    answer = _wire(symbol, "yesterday", session, start, end, build([b for b in bars if start <= b.t < end]),
                   feed=feed, error=f"{who} no 1-minute bars for {session.isoformat()}'s regular session")
    if answer["histogram"]:
        _cache[(feed, symbol, session.isoformat())] = answer
        while len(_cache) > VP_CACHE_MAX:
            _cache.popitem(last=False)
    return answer


async def _yesterday(symbol: str, session: date, feed: str) -> dict[str, Any]:
    day = session.isoformat()
    key = (feed, symbol, day)
    if key in _cache:
        _cache.move_to_end(key)
        return _cache[key]
    task = _once(key, lambda: _read_session(symbol, session, feed))
    # A Massive file without its index can take minutes: answer `filling` and let the read go on in its thread.
    wait = VP_MASSIVE_WAIT_SEC if feed == VP_FEED_MASSIVE else None
    try:
        return await asyncio.wait_for(asyncio.shield(task), wait)
    except asyncio.TimeoutError:
        if feed != VP_FEED_MASSIVE:
            raise
        start, end = _at(session, VP_RTH_OPEN_MIN), _at(session, VP_RTH_CLOSE_MIN)
        return _wire(symbol, "yesterday", session, start, end, None, feed=feed, filling=True,
                     error=f"Reading {day}'s 1-minute bars from the Massive files")


async def profile(symbol: str, kind: Kind, day: date | None, anchor: float | None) -> dict[str, Any]:
    from sim.mode import is_replay_desk
    from sim.trading_day import last_open_day

    session = day or exchange_day()
    replay = is_replay_desk()
    if kind == "yesterday":
        feed = VP_FEED_MASSIVE if replay and _massive_replay(symbol) else VP_FEED_IBKR
        return await _yesterday(symbol, last_open_day(session - timedelta(days=1)), feed)
    open_, close = _at(session, VP_EXTENDED_OPEN_MIN), _at(session, VP_EXTENDED_CLOSE_MIN)
    start = _at(session, VP_RTH_OPEN_MIN) if anchor is None else float(anchor)
    if not open_ <= start < close:
        raise BadRequest(f"anchor must fall inside {session.isoformat()} 04:00-20:00 ET")
    if replay:
        bars, feed = await asyncio.to_thread(_replay_minutes, symbol, start, close)
        missing = f"No 1-minute bars in the replay for {symbol} since the anchor, up to the playhead"
    else:
        bars, feed = await asyncio.to_thread(_stored_minutes, symbol, start, close), VP_FEED_IBKR
        missing = f"No 1-minute bars for {symbol} since the anchor yet"
    return _wire(symbol, "today", session, start, close, build(bars), feed=feed, error=missing)
