"""Auto-record the setups and the leaders (ADR 023, ADR 041) -- on free Level 2 lines only.

maintainer: one-concern who holds each auto line (``_auto``) changes only here -- start, stop, rotate, yield

Who gets a line, in order (ADR 041, operator decision 2026-09-30):

1. ``trade`` -- a setup of a template in play whose trigger is inside its
   scoring window (``lane.trade_symbols``): the trade's tape is what the exit
   trials read, so its line is kept past every window until that window ends;
2. ``near`` then ``armed`` -- a setup of a template in play waiting on its
   trigger (``lane.watching``): the tape at the trigger is what the entry
   trials read, and with a line the tape gate is no longer blind there;
3. ``leader`` -- ``ranking.leader_symbols(rows, LEADERS_RULES)`` over the live
   Gainers board, the same call playback makes on the recorded minute.

Two windows (``leaderboard.auto_record_windows``): setups whenever any setup's
arming window is open (07:00-11:30 ET by default), leaders 07:00-10:00 ET. When
the leaders' window closes, a line taken for a leader stops as planned; a setup's
line stays (operator ask 2026-09-30).

A setup takes a line from a leader (one recorded at least
``LEADERBOARD_AUTO_RECORD_SETUP_MIN_KEEP_SEC``) or from a name that left both
lists; never from another setup. A leader takes only a line whose name left
both lists, and only once it held its place ``LEADERBOARD_AUTO_RECORD_MIN_HOLD_SEC``.

Rules the operator set (2026-09-22), unchanged:

* only a FREE line is taken (``IBKR_MAX_DEPTH_SYMBOLS`` counts every line in
  use); the operator never loses Level 2 -- ``make_room_for`` gives back the
  lowest-ranked auto line the moment they open Level 2 on another symbol;
* a symbol the operator recorded by hand is never started, stopped or adopted,
  and one the operator stopped is not taken again that day;
* every auto stop is planned (segment ``reason: "auto"``) -- never the loud
  unrequested stop.

A line given back to the operator (#698) -- for Level 2, a Record, or a Time &
Sales IBKR refused for its tick-by-tick cap -- is cancelled at once (no 16 s
linger) and kept for them ``LEADERBOARD_AUTO_RECORD_YIELD_HOLD_SEC``. Slots a
restart's resumes are bringing back are left to them (``auto_record_state``).

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
    LEADERBOARD_AUTO_RECORD_MIN_HOLD_SEC,
    LEADERBOARD_AUTO_RECORD_SETUP_MIN_KEEP_SEC,
    LEADERBOARD_AUTO_RECORD_TICK_SEC,
    LEADERBOARD_AUTO_RECORD_YIELD_HOLD_SEC,
    LEADERBOARD_BOARD_GAINERS,
)
from leaderboard import auto_record_state
from leaderboard.auto_record_picks import SETUP_TIERS as _SETUP_TIERS
from leaderboard.auto_record_picks import TIERS as _TIERS
from leaderboard.auto_record_picks import WHY_LEADER, WHY_LEFT, WHY_TRADE, pick_leaders, pick_setups
from leaderboard.auto_record_windows import OPEN_NONE, window_label, window_state
from leaderboard.rows import ET

logger = logging.getLogger(__name__)

AUTO_RECORD_ENV = "NOVA_AUTO_RECORD"
_RETRY_AFTER_FAILURE_SEC = 300.0

_lock = asyncio.Lock()
_auto: dict[str, float] = {}             # symbol -> when auto-record started it
_wanted_as: dict[str, str] = {}          # symbol -> the last reason it was wanted (never ``left``)
_candidate_since: dict[str, float] = {}  # symbol -> when it entered the leaders
_declined: dict[str, str] = {}           # symbol -> session date the operator stopped it
_failed: dict[str, float] = {}           # symbol -> when a start failed
_yielded: list[dict[str, Any]] = []
_leaders: list[str] = []
_setups: list[tuple[str, str]] = []      # (symbol, why) for setups, best first
_setups_error: str | None = None         # the setup scanner could not be read (never "no setups")
_last_error: str | None = None
_reserved: dict[str, tuple[float, str]] = {}  # symbol -> (until, "depth" | "record" | "tape"): given back to the operator


def enabled() -> bool:
    return (os.environ.get(AUTO_RECORD_ENV) or "1").strip().lower() not in ("0", "false", "off", "no")


def _live_gainers() -> list[dict]:
    from runtime_state import get_runtime_state
    from scanner_surface import surface_rows

    state = get_runtime_state()
    if getattr(state.gainer_table, "state", None) != "live":
        return []
    return surface_rows(list(state.gainer_cache or []), LEADERBOARD_BOARD_GAINERS)


def _live_setup_lanes() -> list[Any]:
    from setup_scanner.engine import get_engine

    return get_engine().playing_lanes()


def _read_setups(now: float) -> list[tuple[str, str]]:
    global _setups_error
    try:
        found = pick_setups(_live_setup_lanes(), now)
        _setups_error = None
        return found
    except Exception as exc:  # the leaders still get their lines; the failure is stated
        _setups_error = f"{type(exc).__name__}: {exc}"
        logger.warning("AUTO-RECORD: could not read the setup scanner", exc_info=True)
        return []


def _busy_lines() -> list[str]:
    from ibkr import depth

    return [s for s in depth.subscribed_symbols() if depth.viewer_count(s) > 0]


def _recording() -> list[str]:
    from capture.mode import capture_symbols

    return capture_symbols()


def _resuming() -> list[str]:
    from capture import keepalive

    return keepalive.pending_symbols()


def _tape_up(symbol: str) -> bool:
    from ibkr import tape_stream

    return tape_stream.is_subscribed(symbol)


def free_lines(now: float | None = None) -> int:
    """Lines auto-record may take: never one given back to the operator whose subscribe has not
    landed, nor a slot a restart's resume is bringing back (#698)."""
    ts = time.time() if now is None else now
    busy, recording = _busy_lines(), _recording()
    held = [(s, kind) for s, (until, kind) in _reserved.items() if until > ts]
    if any(kind == "tape" and not _tape_up(s) for s, kind in held):
        return 0  # every start takes a tick-by-tick line: the operator's Time & Sales is waiting for one
    return max(0, min(
        IBKR_MAX_DEPTH_SYMBOLS - len(busy) - sum(1 for s, _ in held if s not in busy),
        CAPTURE_MAX_CONCURRENT - len(recording) - sum(1 for s, kind in held if kind == "record" and s not in recording)
        - sum(1 for s in _resuming() if s not in recording),
    ))


def held_symbols() -> list[str]:
    """The symbols auto-record holds a line for now."""
    return sorted(_auto)


def lines_lock() -> asyncio.Lock:
    """Held while a line changes hands outside auto-record -- a loan (ADR 044, ``line_lending``) --
    so a tick never takes the line between its release and its new holder's subscribe."""
    return _lock


def why(symbol: str) -> str:
    """Why ``symbol`` holds (or wants) an auto line now."""
    for sym, reason in _setups:
        if sym == symbol:
            return reason
    return WHY_LEADER if symbol in _leaders else WHY_LEFT


def _rank(symbol: str) -> tuple[int, int]:
    reason = why(symbol)
    within = _leaders.index(symbol) if reason == WHY_LEADER else 0
    return _TIERS.index(reason), within


def _note_wanted() -> None:
    """Remember why each held line was last wanted: a leader's line ends with the leaders' window."""
    for sym in _auto:
        reason = why(sym)
        if reason != WHY_LEFT:
            _wanted_as[sym] = reason


async def _start(symbol: str, reason: str) -> bool:
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
    _wanted_as[symbol] = reason
    logger.info("AUTO-RECORD: recording %s (%s)", symbol, reason)
    await _save()
    return True


async def _save() -> None:
    await auto_record_state.save(_auto, _wanted_as, _declined)


async def _stop(symbol: str, reason: str, *, at_once: bool = False) -> None:
    from capture import feed_hold, keepalive
    from capture.mode import set_capture_mode

    # Planned: keepalive must never read this as a death, and never resume it.
    keepalive.operator_stopped(symbol)
    await asyncio.to_thread(set_capture_mode, False, symbol=symbol, protect_active=True, reason=CAPTURE_STOP_AUTO)
    await feed_hold.release(symbol, at_once=at_once)
    _auto.pop(symbol, None)
    _wanted_as.pop(symbol, None)
    logger.info("AUTO-RECORD: stopped %s (%s)", symbol, reason)
    await _save()


def _lowest_ranked(exclude: str | None = None) -> str | None:
    owned = [s for s in _auto if s != exclude]
    if not owned:
        return None
    # Off both lists first, then the lowest leader, then armed, near, a trade; the newest start on a tie.
    return max(owned, key=lambda s: (_rank(s), _auto[s]))


def _victim_for(candidate_why: str, ts: float) -> str | None:
    """The auto line a candidate may take when none is free, or ``None``."""
    if candidate_why in _SETUP_TIERS:
        allowed = [s for s in _auto if why(s) == WHY_LEFT
                   or (why(s) == WHY_LEADER and ts - _auto[s] >= LEADERBOARD_AUTO_RECORD_SETUP_MIN_KEEP_SEC)]
    else:
        allowed = [s for s in _auto if why(s) == WHY_LEFT]
    if not allowed:
        return None
    return max(allowed, key=lambda s: (_rank(s), _auto[s]))


async def make_room_for(symbol: str, *, for_record: bool = False, tape_refused: bool = False) -> str | None:
    """The operator wants Level 2 (or a Record) on ``symbol``: give back an auto line if none is free.

    ``tape_refused``: IBKR refused their Time & Sales on ``symbol`` for its tick-by-tick cap -- the
    lines are full whatever Nova counts, so one is given back (#698).
    """
    sym = (symbol or "").strip().upper()
    async with _lock:
        busy = _busy_lines()
        lines_full = sym not in busy and len(busy) >= IBKR_MAX_DEPTH_SYMBOLS
        recording = _recording()
        slots_full = for_record and sym not in recording and len(recording) >= CAPTURE_MAX_CONCURRENT
        if not sym or not (lines_full or slots_full or tape_refused):
            return None
        victim = _lowest_ranked(exclude=sym)
        if victim is None:
            return None
        await _stop(victim, f"yielded its line to {sym}", at_once=True)
        # Kept for the operator while their subscribe lands: on 2026-10-02 the next tick took
        # TNON back before AIXI's Level 2 had its line.
        kind = "tape" if tape_refused else "record" if for_record else "depth"
        _reserved[sym] = (time.time() + LEADERBOARD_AUTO_RECORD_YIELD_HOLD_SEC, kind)
        _yielded.append({"symbol": victim, "for": sym, "at": time.time()})
        del _yielded[:-10]
        return victim


def operator_took(symbol: str) -> None:
    """The operator pressed Record on a symbol auto-record holds: it is theirs now."""
    sym = (symbol or "").strip().upper()
    _auto.pop(sym, None)
    _wanted_as.pop(sym, None)
    auto_record_state.forget(sym)
    auto_record_state.save_soon(_auto, _wanted_as, _declined)


def operator_stopped(symbol: str | None, now: float | None = None) -> None:
    """The operator stopped a recording by hand: never take that symbol again today."""
    day = datetime.fromtimestamp(time.time() if now is None else now, ET).date().isoformat()
    targets = [(symbol or "").strip().upper()] if symbol else list(_auto)
    for sym in targets:
        if sym:
            _auto.pop(sym, None)
            _wanted_as.pop(sym, None)
            auto_record_state.forget(sym)
            _declined[sym] = day
    auto_record_state.save_soon(_auto, _wanted_as, _declined)


async def _after_window(ts: float) -> None:
    """Outside both windows: a trade being scored keeps its tape to the end of its window; the rest stop."""
    global _leaders, _setups
    _candidate_since.clear()
    _leaders = []
    _setups = [(s, w) for s, w in (_read_setups(ts) if enabled() and _auto else []) if w == WHY_TRADE]
    for sym in list(_auto):
        if why(sym) != WHY_TRADE:
            await _stop(sym, "auto-record window closed")


async def _leaders_closed() -> None:
    """The leaders' window closed while a setup's is open: a line taken for a leader stops as
    planned, as it did at 10:00 before setups had their own window; a setup's line stays."""
    for sym in list(_auto):
        if why(sym) == WHY_LEFT and _wanted_as.get(sym) == WHY_LEADER:
            await _stop(sym, "the leaders' window closed")


async def tick(now: float | None = None) -> None:
    global _leaders, _setups, _last_error
    ts = time.time() if now is None else float(now)
    async with _lock:
        for sym in [s for s, (until, _) in _reserved.items() if until <= ts]:
            _reserved.pop(sym, None)
        await auto_record_state.restore(ts, auto=_auto, wanted_as=_wanted_as, declined=_declined,
                                        recording=_recording(), resuming=_resuming())
        state = window_state(ts)
        if not enabled() or state["open"] == OPEN_NONE:
            await _after_window(ts)
            return
        from ibkr import client as _client

        if not _client.is_ready():
            return
        today = datetime.fromtimestamp(ts, ET).date().isoformat()
        _setups = _read_setups(ts)
        if state["leaders"]["open"]:
            _leaders = pick_leaders(_live_gainers(), ts)
            for sym in list(_candidate_since):
                if sym not in _leaders:
                    _candidate_since.pop(sym)
            for sym in _leaders:
                _candidate_since.setdefault(sym, ts)
        else:
            _leaders = []
            _candidate_since.clear()
        _note_wanted()
        if not state["leaders"]["open"]:
            await _leaders_closed()
        wanted = list(_setups) + [(s, WHY_LEADER) for s in _leaders if s not in dict(_setups)]
        recording = set(_recording())
        for sym, reason in wanted:
            if sym in _auto or sym in recording or _declined.get(sym) == today:
                continue
            if ts - _failed.get(sym, 0.0) < _RETRY_AFTER_FAILURE_SEC:
                continue
            if free_lines() <= 0:
                # A leader rotates in only once it held its place; a setup does not wait.
                if reason == WHY_LEADER and ts - _candidate_since.get(sym, ts) < LEADERBOARD_AUTO_RECORD_MIN_HOLD_SEC:
                    continue
                victim = _victim_for(reason, ts)
                if victim is None:
                    continue
                await _stop(victim, f"gave its line to {sym} ({reason})")
                if free_lines() <= 0:
                    continue
            if await _start(sym, reason):
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
    state = window_state(ts)
    return {
        "active": bool(enabled() and state["open"] != OPEN_NONE),
        "window": window_label(state),
        "windows": state,
        "symbols": sorted(_auto),
        "why": {sym: why(sym) for sym in sorted(_auto)},
        "setups": [{"symbol": sym, "why": reason} for sym, reason in _setups],
        "setups_error": _setups_error,
        "leaders": list(_leaders),
        "yielded": [entry["symbol"] for entry in _yielded],
        "last_error": _last_error,
    }


def reset_for_tests() -> None:
    global _leaders, _setups, _setups_error, _last_error
    _auto.clear()
    _wanted_as.clear()
    _candidate_since.clear()
    _declined.clear()
    _failed.clear()
    _yielded.clear()
    _reserved.clear()
    auto_record_state.reset_for_tests()
    _leaders = []
    _setups = []
    _setups_error = None
    _last_error = None
