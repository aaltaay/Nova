"""Auto-record the leaders 07:00-10:00 ET (ADR 023) -- on free Level 2 lines only.

The leaders are ``ranking.leader_symbols(rows, LEADERS_RULES)`` over the live
Gainers board, the same call playback makes on the recorded minute. Rules the
operator set (2026-09-22):

* only a FREE line is taken (``IBKR_MAX_DEPTH_SYMBOLS`` counts every line in
  use); the operator never loses Level 2 -- ``make_room_for`` gives back the
  lowest-ranked auto line the moment they open Level 2 on another symbol;
* a symbol the operator recorded by hand is never started, stopped or adopted,
  and one the operator stopped is not taken again that day;
* every auto stop is planned (segment ``reason: "auto"``) -- never the loud
  unrequested stop.

Start / stop go through the Session Record path (``capture.feed_hold`` +
``capture.mode.set_capture_mode``), so recordings land where the operator's do.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import datetime
from typing import Any

from capture.constants_capture import CAPTURE_MAX_CONCURRENT, CAPTURE_STOP_AUTO
from constants_ibkr import IBKR_MAX_DEPTH_SYMBOLS
from constants_leaderboard import (
    LEADERBOARD_AUTO_RECORD_END_MIN_ET,
    LEADERBOARD_AUTO_RECORD_MIN_HOLD_SEC,
    LEADERBOARD_AUTO_RECORD_START_MIN_ET,
    LEADERBOARD_AUTO_RECORD_TICK_SEC,
    LEADERBOARD_AUTO_RECORD_TOP_N,
    LEADERBOARD_BOARD_GAINERS,
)
from leaderboard.ranking import LEADERS_RULES, leader_symbols
from leaderboard.recorder import exchange_day
from leaderboard.rows import ET, from_desk_row

logger = logging.getLogger(__name__)

AUTO_RECORD_ENV = "NOVA_AUTO_RECORD"
WINDOW_LABEL = "07:00-10:00 ET"
_RETRY_AFTER_FAILURE_SEC = 300.0

_lock = asyncio.Lock()
_auto: dict[str, float] = {}             # symbol -> when auto-record started it
_candidate_since: dict[str, float] = {}  # symbol -> when it entered the leaders
_declined: dict[str, str] = {}           # symbol -> session date the operator stopped it
_failed: dict[str, float] = {}           # symbol -> when a start failed
_yielded: list[dict[str, Any]] = []
_leaders: list[str] = []
_last_error: str | None = None


def enabled() -> bool:
    return (os.environ.get(AUTO_RECORD_ENV) or "1").strip().lower() not in ("0", "false", "off", "no")


def in_window(now: float) -> bool:
    when = datetime.fromtimestamp(now, ET)
    minutes = when.hour * 60 + when.minute
    return exchange_day(when) and LEADERBOARD_AUTO_RECORD_START_MIN_ET <= minutes < LEADERBOARD_AUTO_RECORD_END_MIN_ET


def pick_leaders(surfaced_gainers: list[dict], now: float) -> list[str]:
    """The same ranking playback applies to the recorded Gainers minute."""
    minute_ts = int(now) // 60 * 60
    rows = []
    for position, raw in enumerate(surfaced_gainers, start=1):
        try:
            rows.append(from_desk_row(raw, minute_ts=minute_ts, board=LEADERBOARD_BOARD_GAINERS, rank=position))
        except (TypeError, ValueError):
            continue
    return leader_symbols(rows, LEADERS_RULES)[:LEADERBOARD_AUTO_RECORD_TOP_N]


def _live_gainers() -> list[dict]:
    from runtime_state import get_runtime_state
    from scanner_surface import surface_rows

    state = get_runtime_state()
    if getattr(state.gainer_table, "state", None) != "live":
        return []
    return surface_rows(list(state.gainer_cache or []), LEADERBOARD_BOARD_GAINERS)


def _busy_lines() -> list[str]:
    from ibkr import depth

    return [s for s in depth.subscribed_symbols() if depth.viewer_count(s) > 0]


def _recording() -> list[str]:
    from capture.mode import capture_symbols

    return capture_symbols()


def free_lines() -> int:
    return max(0, min(
        IBKR_MAX_DEPTH_SYMBOLS - len(_busy_lines()),
        CAPTURE_MAX_CONCURRENT - len(_recording()),
    ))


async def _start(symbol: str) -> bool:
    from capture import feed_hold, keepalive
    from capture.mode import set_capture_mode

    global _last_error
    error = await feed_hold.acquire(symbol)
    if error:
        _last_error, _failed[symbol] = f"{symbol}: {error}", time.time()
        return False
    out = await asyncio.to_thread(set_capture_mode, True, symbol=symbol, protect_active=True)
    if symbol not in (out.get("capture_symbols") or []):
        _last_error, _failed[symbol] = f"{symbol}: {out.get('error') or 'recorder refused'}", time.time()
        await feed_hold.release(symbol)
        return False
    keepalive.operator_started(symbol)
    _auto[symbol] = time.time()
    logger.info("AUTO-RECORD: recording leader %s", symbol)
    return True


async def _stop(symbol: str, why: str) -> None:
    from capture import feed_hold, keepalive
    from capture.mode import set_capture_mode

    # Planned: keepalive must never read this as a death, and never resume it.
    keepalive.operator_stopped(symbol)
    await asyncio.to_thread(set_capture_mode, False, symbol=symbol, protect_active=True, reason=CAPTURE_STOP_AUTO)
    await feed_hold.release(symbol)
    _auto.pop(symbol, None)
    logger.info("AUTO-RECORD: stopped %s (%s)", symbol, why)


def _lowest_ranked(exclude: str | None = None) -> str | None:
    owned = [s for s in _auto if s != exclude]
    if not owned:
        return None
    # Out of the leaders first, then the lowest leader, then the newest start.
    return max(owned, key=lambda s: (_leaders.index(s) if s in _leaders else len(_leaders) + 1, _auto[s]))


async def make_room_for(symbol: str, *, for_record: bool = False) -> str | None:
    """The operator wants Level 2 (or a Record) on ``symbol``: give back an auto line if none is free."""
    sym = (symbol or "").strip().upper()
    async with _lock:
        busy = _busy_lines()
        lines_full = sym not in busy and len(busy) >= IBKR_MAX_DEPTH_SYMBOLS
        recording = _recording()
        slots_full = for_record and sym not in recording and len(recording) >= CAPTURE_MAX_CONCURRENT
        if not sym or not (lines_full or slots_full):
            return None
        victim = _lowest_ranked(exclude=sym)
        if victim is None:
            return None
        await _stop(victim, f"yielded its line to {sym}")
        _yielded.append({"symbol": victim, "for": sym, "at": time.time()})
        del _yielded[:-10]
        return victim


def operator_took(symbol: str) -> None:
    """The operator pressed Record on a symbol auto-record holds: it is theirs now."""
    _auto.pop((symbol or "").strip().upper(), None)


def operator_stopped(symbol: str | None, now: float | None = None) -> None:
    """The operator stopped a recording by hand: never take that symbol again today."""
    day = datetime.fromtimestamp(time.time() if now is None else now, ET).date().isoformat()
    targets = [(symbol or "").strip().upper()] if symbol else list(_auto)
    for sym in targets:
        if sym:
            _auto.pop(sym, None)
            _declined[sym] = day


async def tick(now: float | None = None) -> None:
    global _leaders, _last_error
    ts = time.time() if now is None else float(now)
    async with _lock:
        if not enabled() or not in_window(ts):
            for sym in list(_auto):
                await _stop(sym, "auto-record window closed")
            _candidate_since.clear()
            _leaders = []
            return
        from ibkr import client as _client

        if not _client.is_ready():
            return
        today = datetime.fromtimestamp(ts, ET).date().isoformat()
        _leaders = pick_leaders(_live_gainers(), ts)
        for sym in list(_candidate_since):
            if sym not in _leaders:
                _candidate_since.pop(sym)
        for sym in _leaders:
            _candidate_since.setdefault(sym, ts)
        recording = set(_recording())
        for sym in _leaders:
            if sym in _auto or sym in recording or _declined.get(sym) == today:
                continue
            if ts - _failed.get(sym, 0.0) < _RETRY_AFTER_FAILURE_SEC:
                continue
            if free_lines() <= 0:
                # Rotate only for a leader that has held its place, and only out
                # of an auto line whose symbol has left the leaders.
                stale = [s for s in _auto if s not in _leaders]
                if not stale or ts - _candidate_since.get(sym, ts) < LEADERBOARD_AUTO_RECORD_MIN_HOLD_SEC:
                    continue
                await _stop(_lowest_ranked() or stale[0], f"rotated to leader {sym}")
                if free_lines() <= 0:
                    continue
            if await _start(sym):
                _last_error = None


async def run() -> None:
    while True:
        try:
            await tick()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            global _last_error
            _last_error = f"{type(exc).__name__}: {exc}"
            logger.exception("AUTO-RECORD: tick failed")
        await asyncio.sleep(LEADERBOARD_AUTO_RECORD_TICK_SEC)


def status(now: float | None = None) -> dict[str, Any]:
    ts = time.time() if now is None else float(now)
    return {
        "active": bool(enabled() and in_window(ts)),
        "window": WINDOW_LABEL,
        "symbols": sorted(_auto),
        "leaders": list(_leaders),
        "yielded": [entry["symbol"] for entry in _yielded],
        "last_error": _last_error,
    }


def reset_for_tests() -> None:
    global _leaders, _last_error
    _auto.clear()
    _candidate_since.clear()
    _declined.clear()
    _failed.clear()
    _yielded.clear()
    _leaders = []
    _last_error = None
