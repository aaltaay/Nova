"""The three lanes at run time: the only code that opens or ends a live Level 2 or AllLast line (ADR 071).

maintainer: one-concern which stock each lane is on, and the lines that follow it, change only here

``put`` moves one lane under one lock. The recordings of a stock no lane will be on end first (planned, through the
``before_close`` hooks), then its two lines end at once -- every socket still on it reads one lane frame and closes
(``ibkr.depth.push_lane`` / ``ibkr.tape_stream.push_lane``) -- and only then are the new stock's lines asked for. A
stock two lanes are on is one pair of lines (``table.put``). The lane holds one viewer reference on each of its
stock's lines, so a socket, a Record or the seat letting go never ends it: only a lane leaving does.

``refusal`` is the gate: ``ibkr.depth.subscribe_async`` and ``ibkr.tape_stream.subscribe_async`` open a live line
only for a stock a lane is on. ``ensure`` asks again for a lane's line that is down (IBKR ended it, a reconnect, a
refusal); IBKR's 15 s rule on a tape is the tape module's own guard.

Memory only: a restart starts with three empty lanes.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Awaitable, Callable

from line_lanes.constants_lanes import LANE_EMPTIED_WORDS, LANE_LEFT_WORDS, NO_LANE_WORDS, YOUR_LANE_WORDS
from line_lanes.table import OWNERS, Lanes, Move
from line_lanes.table import put as table_put

logger = logging.getLogger(__name__)

DEPTH = "depth"
TAPE = "tape"

_lanes = Lanes()
_since: dict[str, float] = {}                 # owner -> when its lane came onto its stock
_refs: dict[str, dict[str, bool]] = {}       # stock -> which of its lines the lanes hold a reference on
_errors: dict[str, str] = {}                 # stock -> why its lines are not both up
_lock: asyncio.Lock | None = None
_enforced = True
_before_close: list[Callable[[str], Awaitable[None]]] = []
_after_move: list[Callable[[], Awaitable[None]]] = []


def reset_for_tests() -> None:
    global _lanes, _lock, _enforced
    _lanes = Lanes()
    _since.clear()
    _refs.clear()
    _errors.clear()
    _lock = None
    _enforced = True


def enforce(on: bool) -> None:
    """Tests only: the gate open (False) for a test that drives a line without a lane."""
    global _enforced
    _enforced = bool(on)


def enforced() -> bool:
    return _enforced


def on_before_close(hook: Callable[[str], Awaitable[None]]) -> None:
    """``hook(stock)`` runs before a stock's lines end (the lanes' recording ends there first)."""
    if hook not in _before_close:
        _before_close.append(hook)


def on_after_move(hook: Callable[[], Awaitable[None]]) -> None:
    """``hook()`` runs after every move, outside the lock (the lanes' recording starts there)."""
    if hook not in _after_move:
        _after_move.append(hook)


def table() -> Lanes:
    return _lanes


def stocks() -> tuple[str, ...]:
    return _lanes.stocks()


def on_lane(symbol: str | None) -> bool:
    return _sym(symbol) in _lanes.stocks()


def since(owner: str) -> float | None:
    return _since.get(owner)


def error(symbol: str | None) -> str | None:
    return _errors.get(_sym(symbol))


def lines_up(symbol: str | None) -> dict[str, bool]:
    """Whether the stock's Level 2 and AllLast lines are up on this IBKR session."""
    from ibkr import depth, tape_stream

    sym = _sym(symbol)
    return {DEPTH: bool(sym) and depth.is_live(sym), TAPE: bool(sym) and tape_stream.is_subscribed(sym)}


def refusal(symbol: str | None) -> str | None:
    """Why a live line for ``symbol`` may not open (no lane is on it), or None."""
    sym = _sym(symbol)
    if not _enforced or not sym or sym in _lanes.stocks():
        return None
    if _lanes.you:
        return YOUR_LANE_WORDS.format(lane=_lanes.you, symbol=sym)
    return NO_LANE_WORDS.format(symbol=sym)


def wire() -> dict[str, Any]:
    """Who is on what, for a frame: ``{you, claude, bots}``."""
    return {owner: _lanes.on(owner) for owner in OWNERS}


def _get_lock() -> asyncio.Lock:
    global _lock
    if _lock is None:
        _lock = asyncio.Lock()
    return _lock


async def put(owner: str, symbol: str | None) -> Move:
    """Put ``owner``'s lane on ``symbol`` (None empties it); the lines that ended and opened."""
    global _lanes
    async with _get_lock():
        after, move = table_put(_lanes, owner, symbol)
        if after == _lanes:
            return move
        for sym in move.close:
            for hook in list(_before_close):
                try:
                    await hook(sym)
                except Exception:
                    logger.exception("LANES: a hook failed before %s's lines ended -- they end anyway", sym)
        before, _lanes = _lanes, after
        if after.on(owner):
            _since[owner] = time.time()
        else:
            _since.pop(owner, None)
        for sym in move.close:
            _end(sym)
        for sym in move.open:
            await _ask(sym)
        logger.info("LANES: %s's lane %s -> %s (lines ended %s, opened %s)", owner, before.on(owner),
                    after.on(owner), list(move.close) or "none", list(move.open) or "none")
    if move or after != before:
        for hook in list(_after_move):
            try:
                await hook()
            except Exception:
                logger.exception("LANES: a hook failed after %s's lane moved", owner)
    return move


async def ensure() -> dict[str, str]:
    """Ask again for every lane's line that is down; ``{stock: why}`` for those still not up."""
    async with _get_lock():
        for sym in _lanes.stocks():
            up = lines_up(sym)
            refs = _refs.get(sym) or {}
            if not (up[DEPTH] and up[TAPE] and refs.get(DEPTH) and refs.get(TAPE)):
                await _ask(sym)
    return dict(_errors)


async def _ask(sym: str) -> None:
    """Open (or join) ``sym``'s two lines and hold one reference on each; a failure is kept in ``_errors``."""
    from ibkr import depth, tape_stream

    refs = _refs.setdefault(sym, {DEPTH: False, TAPE: False})
    why: list[str] = []
    try:
        if not depth.is_live(sym):
            result = await depth.subscribe_async(sym, live=True)
            if not result.get("ok") and not depth.is_live(sym):
                why.append(f"Level 2: {result.get('error') or 'not opened'}")
        if depth.is_live(sym) and not refs[DEPTH]:
            depth.ws_viewer_opened(sym)
            refs[DEPTH] = True
            _start_snapshots(sym)
    except Exception as exc:
        logger.exception("LANES: could not open %s's Level 2", sym)
        why.append(f"Level 2: {type(exc).__name__}: {exc}")
    try:
        if not tape_stream.is_subscribed(sym):
            result = await tape_stream.subscribe_async(sym)
            if not result.get("ok") and not tape_stream.is_subscribed(sym):
                why.append(f"Time & Sales: {result.get('error') or 'not opened'}")
        if tape_stream.is_subscribed(sym) and not refs[TAPE]:
            tape_stream.ws_viewer_opened(sym)
            refs[TAPE] = True
    except Exception as exc:
        logger.exception("LANES: could not open %s's Time & Sales", sym)
        why.append(f"Time & Sales: {type(exc).__name__}: {exc}")
    if why:
        _errors[sym] = "; ".join(why)
    else:
        _errors.pop(sym, None)


def _end(sym: str) -> None:
    """End both of ``sym``'s lines now: every socket still on it reads the lane frame and closes."""
    from ibkr import depth, tape_line, tape_stream

    _refs.pop(sym, None)
    _errors.pop(sym, None)
    message = LANE_LEFT_WORDS.format(lane=_lanes.you) if _lanes.you else LANE_EMPTIED_WORDS.format(symbol=sym)
    lane = wire()
    try:
        depth.push_lane(sym, message, lane)
        depth.forget_viewers(sym)
        _stop_snapshots(sym)
        if depth.is_subscribed(sym):
            depth.unsubscribe(sym)
    except Exception:
        logger.exception("LANES: could not end %s's Level 2 line", sym)
    try:
        tape_stream.push_lane(sym, message, lane)
        tape_stream.forget_viewers(sym)
        tape_line.drop_line(sym, "no lane is on it")
    except Exception:
        logger.exception("LANES: could not end %s's Time & Sales line", sym)


def _start_snapshots(sym: str) -> None:
    """The Level 2 pane's own session (``l2.continuous``) follows the lane, not a socket (ADR 071 decision 8)."""
    try:
        from l2 import continuous

        continuous.start(sym)
    except Exception:
        logger.exception("LANES: could not start the Level 2 snapshots of %s", sym)


def _stop_snapshots(sym: str) -> None:
    try:
        from l2 import continuous

        task = continuous.stop(sym)
        if asyncio.iscoroutine(task):
            asyncio.get_running_loop().create_task(task)
    except RuntimeError:
        pass  # maintainer: allow-swallow no running loop (a test's sync call): nothing to stop on
    except Exception:
        logger.exception("LANES: could not stop the Level 2 snapshots of %s", sym)


def _sym(symbol: str | None) -> str:
    return (symbol or "").strip().upper()
