"""Nova records what a lane watches, and nothing else (ADR 071 decision 8; operator, 2026-11-12 and 2026-11-13).

maintainer: one-concern which lane stocks Nova records, and when those recordings start and stop, change only here

While the recording switch is On (``leaderboard.auto_record_switch``, ``NOVA_AUTO_RECORD=0`` still wins):

- the bots' lane's stock, while it is on the lane;
- Claude's lane's stock, while it is on the lane;
- your lane's stock while you watch it -- a fresh desk window shows it in front (``focus``), or a socket opened in
  front on it is still open and no desk window lists it as a hidden Trader tab (the phone, a browser,
  ``sockets.shown_by_socket``) -- and for ``LANES_YOU_RECORD_TAIL_SEC`` after.

A recording holds no line: it starts through the Session Record path (``capture.feed_hold`` joins the lane's lines,
``capture.mode.set_capture_mode``), and ``stop_for`` -- run by ``lanes.put`` before a stock's lines end -- ends every
recording of that stock first, the operator's own Record included, as a planned stop (segment ``reason: "lane"``).
A recording the operator started by hand is theirs: never started or stopped here otherwise; one they stopped by
hand is not started again that trading day. Memory only.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from line_lanes import focus, lanes, sockets
from capture.constants_capture import CAPTURE_STOP_LANE
from line_lanes.constants_lanes import LANES_RECORD_RETRY_SEC, LANES_YOU_RECORD_TAIL_SEC

logger = logging.getLogger(__name__)


_mine: dict[str, float] = {}       # stock -> when the lanes' recording started it
_operator: set[str] = set()        # stocks the operator recorded by hand (theirs)
_declined: dict[str, str] = {}     # stock -> the trading day the operator stopped it by hand
_seen_you: dict[str, float] = {}   # your lane's stock -> the last moment you watched it
_failed: dict[str, float] = {}     # stock -> when a start failed
_last_error: str | None = None
_lock: asyncio.Lock | None = None


def reset_for_tests() -> None:
    global _last_error, _lock
    _mine.clear()
    _operator.clear()
    _declined.clear()
    _seen_you.clear()
    _failed.clear()
    _last_error = None
    _lock = None


def _get_lock() -> asyncio.Lock:
    global _lock
    if _lock is None:
        _lock = asyncio.Lock()
    return _lock


def switch_on(now: float | None = None) -> bool:
    from leaderboard import auto_record_switch

    return auto_record_switch.is_on(now)


def recorded() -> list[str]:
    """The stocks the lanes' recording records now."""
    return sorted(_mine)


def watching_you(symbol: str, now: float) -> bool:
    """You watch your lane's stock now, or did within the tail."""
    read = focus.read(now)
    shown = sockets.shown_by_socket(symbol)
    if read.known:
        on_screen = symbol in read.front or shown["other"] or (shown["tab"] and symbol not in read.tabs)
    else:
        on_screen = shown["tab"] or shown["other"]
    if on_screen:
        _seen_you[symbol] = now
    last = _seen_you.get(symbol)
    return last is not None and now - last < LANES_YOU_RECORD_TAIL_SEC


def wanted(now: float) -> set[str]:
    """The lane stocks Nova records now (the switch aside)."""
    table = lanes.table()
    out = {s for s in (table.bots, table.claude) if s}
    if table.you and watching_you(table.you, now):
        out.add(table.you)
    for sym in [s for s in _seen_you if s != table.you]:
        _seen_you.pop(sym, None)
    return out


async def sync(now: float | None = None) -> None:
    """Start what a lane watches and stop what no lane watches any more."""
    global _last_error
    from capture.mode import capture_symbols
    from market import session_key_for_ts

    ts = time.time() if now is None else float(now)
    async with _get_lock():
        want = wanted(ts) if switch_on(ts) else set()
        for sym in [s for s in _mine if s not in want]:
            await _stop(sym, "no lane watches it" if switch_on(ts) else "recording is switched off")
        today = session_key_for_ts(ts)
        recording = set(capture_symbols())
        for sym in sorted(want):
            if sym in _mine or sym in recording or _declined.get(sym) == today:
                continue
            if ts - _failed.get(sym, float("-inf")) < LANES_RECORD_RETRY_SEC:
                continue
            if await _start(sym, ts):
                _last_error = None


async def stop_for(symbol: str) -> None:
    """``symbol``'s lines are about to end: every recording of it ends first, as planned (``reason: "lane"``)."""
    from capture.mode import capture_symbols

    sym = (symbol or "").strip().upper()
    async with _get_lock():
        if sym in _mine or sym in capture_symbols():
            await _stop(sym, "its lane left it")
        _operator.discard(sym)


async def turned_off() -> list[str]:
    """The switch went off: the lanes' recordings stop now (the operator's own are theirs)."""
    async with _get_lock():
        held = sorted(_mine)
        for sym in held:
            await _stop(sym, "recording is switched off")
        return held


def operator_took(symbol: str) -> None:
    """The operator pressed Record on ``symbol``: it is theirs from now on."""
    sym = (symbol or "").strip().upper()
    if sym:
        _mine.pop(sym, None)
        _operator.add(sym)


def operator_stopped(symbol: str | None, now: float | None = None) -> None:
    """The operator stopped a recording by hand (``None``: all of them): not started again this trading day."""
    from market import session_key_for_ts

    day = session_key_for_ts(time.time() if now is None else now)
    targets = [(symbol or "").strip().upper()] if symbol else sorted(set(_mine) | _operator)
    for sym in targets:
        if sym:
            _mine.pop(sym, None)
            _operator.discard(sym)
            _declined[sym] = day


async def _start(sym: str, now: float) -> bool:
    global _last_error
    from capture import feed_hold, keepalive
    from capture.mode import set_capture_mode

    error = await feed_hold.acquire(sym)
    if error:
        _last_error, _failed[sym] = f"{sym}: {error}", now
        logger.warning("LANES recording: could not start %s (%s)", sym, error)
        return False
    out = await asyncio.to_thread(set_capture_mode, True, symbol=sym, protect_active=True)
    if sym not in (out.get("capture_symbols") or []):
        _last_error, _failed[sym] = f"{sym}: {out.get('error') or 'the recorder refused'}", now
        await feed_hold.release(sym)
        logger.warning("LANES recording: the recorder refused %s (%s)", sym, out.get("error"))
        return False
    keepalive.operator_started(sym)
    _mine[sym] = now
    logger.info("LANES recording: recording %s", sym)
    return True


async def _stop(sym: str, why: str) -> None:
    from capture import feed_hold, keepalive
    from capture.mode import set_capture_mode

    keepalive.operator_stopped(sym)   # planned: the keepalive never reads it as a death, never resumes it
    await asyncio.to_thread(set_capture_mode, False, symbol=sym, protect_active=True, reason=CAPTURE_STOP_LANE)
    await feed_hold.release(sym)
    _mine.pop(sym, None)
    logger.info("LANES recording: stopped %s (%s)", sym, why)


def status(now: float | None = None) -> dict[str, Any]:
    from leaderboard import auto_record_switch

    ts = time.time() if now is None else float(now)
    return {"recorded": recorded(), "last_error": _last_error, "switch": auto_record_switch.state(ts)}
