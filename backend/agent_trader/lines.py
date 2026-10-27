"""Claude's Level 2 and Time & Sales line, and the one line the desk keeps free for it (ADR 068 decisions 2, 3).

While the seat reserves a line (on, not given up), every other subscriber may hold at most
``IBKR_MAX_DEPTH_SYMBOLS - 1`` depth lines **of its own**. A line Claude and a tab both watch is the desk's: it
costs one line, and Claude can still move to another stock. The arithmetic is here, read by ``ibkr.depth``'s
subscribe (the refusal), auto-record and line lending (their free lines); the hold is a viewer reference on both
lines, taken and given back exactly like a Session Record's (``capture.feed_hold``), so it is never idle-evicted
and never lent.

Claude never takes a line from the operator: with all 3 held by the desk, the watcher first has auto-record give
one up (``agent_trader.room``, ADR 068 decision 3 as amended 2026-10-27); with none to give, ``acquire`` answers why
and the watcher asks again; the first line the desk lets go is Claude's, because a desk request is then refused.
"""
from __future__ import annotations

import logging

from constants_ibkr import IBKR_MAX_DEPTH_SYMBOLS

logger = logging.getLogger(__name__)

# symbol -> which lines the seat holds a viewer reference on (one symbol at most).
_held: dict[str, dict[str, bool]] = {}


def reset_for_tests() -> None:
    _held.clear()


def held_symbol() -> str | None:
    return next(iter(_held), None)


def holds(symbol: str) -> bool:
    return (symbol or "").upper() in _held


def _ref(symbol: str, kind: str) -> bool:
    """The seat holds a viewer reference on ``symbol``'s ``kind`` line -- a count, not proof the line is up."""
    return bool((_held.get((symbol or "").upper()) or {}).get(kind))


def holds_depth(symbol: str) -> bool:
    """Claude's Level 2 on ``symbol`` is up on this IBKR session (a reconnect ends lines the reference outlives)."""
    from ibkr import depth

    return _ref(symbol, "depth") and depth.is_live((symbol or "").upper())


def holds_tape(symbol: str) -> bool:
    from ibkr import tape_stream

    return _ref(symbol, "tape") and tape_stream.is_subscribed((symbol or "").upper())


def _reserves() -> bool:
    from agent_trader import seat

    return seat.reserves_line()


def desk_cap() -> int:
    """Depth lines every subscriber but Claude may hold of its own right now."""
    return IBKR_MAX_DEPTH_SYMBOLS - 1 if _reserves() else IBKR_MAX_DEPTH_SYMBOLS


def _own_viewers(symbol: str) -> int:
    from ibkr import depth

    return int(depth.viewer_count(symbol)) - (1 if _ref(symbol, "depth") else 0)


def desk_lines() -> list[str]:
    """Live depth lines someone other than Claude watches (a line both watch is the desk's)."""
    from ibkr import depth

    return [s for s in depth.subscribed_symbols() if _own_viewers(s) > 0]


def claude_only_lines() -> int:
    """0 or 1: the line Claude alone watches."""
    sym = held_symbol()
    return 1 if sym and _ref(sym, "depth") and _own_viewers(sym) <= 0 else 0


def desk_free(busy: int) -> int:
    """Lines a desk taker (auto-record, a loan) may still add, given ``busy`` lines with any viewer."""
    return max(0, desk_cap() - (busy - claude_only_lines()))


def desk_refusal(symbol: str) -> str | None:
    """Why a desk request for ``symbol``'s Level 2 must wait for Claude's line, or None.

    A symbol already on a line costs nothing; otherwise the desk may add one only below ``desk_cap``.
    """
    from ibkr import depth

    if not _reserves():
        return None
    sym = (symbol or "").upper()
    if sym in depth.subscribed_symbols() or _ref(sym, "depth"):
        return None    # a line already up costs nothing; asking again for Claude's own line (a renewal) is Claude's
    mine = desk_lines()
    if len(mine) < desk_cap():
        return None
    return refusal_text(mine)


def refusal_text(desk: list[str]) -> str:
    from agent_trader.constants_agent_trader import AGENT_NAME

    claude = held_symbol()
    yours = " and ".join(desk) if desk else "none"
    whose = f"{claude} is {AGENT_NAME}'s" if claude else f"one is kept for {AGENT_NAME}"
    return (f"All {IBKR_MAX_DEPTH_SYMBOLS} Level 2 lines are in use: {yours} "
            f"{'is' if len(desk) == 1 else 'are'} yours, {whose}. Close one of yours, or take {AGENT_NAME}'s line.")


async def acquire(symbol: str) -> str | None:
    """Hold ``symbol``'s Level 2 and Time & Sales for Claude; return why not, or None.

    Moving to a new stock lets the old lines go first (the AllLast line at once, #698). A line the seat already
    references but that is not up -- an IBKR reconnect ended it -- is asked for again without a second reference.
    Without a free depth line nothing new is held and the answer says so; the watcher asks again.
    """
    from ibkr import depth

    sym = (symbol or "").strip().upper()
    if not sym:
        return "no stock named"
    for old in [s for s in _held if s != sym]:
        if why := keep_shared(old, sym):
            return why
        await release(old, at_once=True)
    hold = _held.setdefault(sym, {"tape": False, "depth": False})
    if not depth.is_live(sym):
        result = await depth.subscribe_async(sym, live=True, agent=True)
        if not result.get("ok") or not depth.is_live(sym):
            if not hold["depth"] and not hold["tape"]:
                _held.pop(sym, None)     # nothing referenced yet: the seat holds nothing on it
            return _depth_why(sym, result)
    if not hold["depth"]:
        depth.ws_viewer_opened(sym)
        hold["depth"] = True
    if not holds_tape(sym):
        await _take_tape(sym)
    logger.info("AGENT lines: holding %s (%s)", sym, hold)
    return None


def keep_shared(old: str, new: str) -> str | None:
    """Why the seat keeps its reference on ``old`` instead of moving to ``new`` yet, or None.

    A line Claude shares with a tab is the desk's, so letting it go frees nothing: with every line in use the
    desk would be left holding 3 of its own and Claude none (SXTP -> AIOK, 2026-10-27). The seat keeps its slot
    on ``old`` until a line is free for ``new`` -- the desk closes one, or auto-record gives one up (``room``).
    """
    from agent_trader import room

    if not (_ref(old, "depth") and _own_viewers(old) > 0) or not room.lines_full(new):
        return None
    return (f"all {IBKR_MAX_DEPTH_SYMBOLS} Level 2 lines are in use and {old}'s is shared with your tab: Claude "
            f"keeps its line on {old} and moves to {new} once one frees")


def _depth_why(sym: str, result: dict) -> str:
    """Why Claude has no Level 2 on ``sym`` yet, in Nova's own words (the door's detail goes to the log)."""
    from ibkr import depth

    if result.get("cap"):
        held = ", ".join(sorted(depth.subscribed_symbols())) or "lines Nova cannot name"
        return (f"all {IBKR_MAX_DEPTH_SYMBOLS} Level 2 lines are in use ({held}): Claude waits for the first one "
                "the desk lets go")
    logger.warning("AGENT lines: no Level 2 line for %s yet: %s", sym, result.get("error"))
    return f"IBKR has not opened {sym}'s Level 2 line yet; Claude asks again"


async def _take_tape(sym: str) -> str | None:
    from ibkr import tape_stream

    if not tape_stream.is_subscribed(sym):
        result = await tape_stream.subscribe_async(sym)
        if not result.get("ok"):
            logger.warning("AGENT lines: Time & Sales for %s refused (%s); asked again", sym, result.get("error"))
            return f"IBKR has not opened {sym}'s Time & Sales yet; Claude asks again"
    if not _held[sym]["tape"]:
        tape_stream.ws_viewer_opened(sym)
        _held[sym]["tape"] = True
    return None


async def release(symbol: str | None = None, *, at_once: bool = False) -> None:
    """Give back the seat's references; a line still watched by a tab stays."""
    from ibkr import depth, tape_line, tape_stream

    for sym in ([symbol.upper()] if symbol else list(_held)):
        hold = _held.pop(sym, None)
        if hold is None:
            continue
        if hold.get("tape") and tape_stream.ws_viewer_closed(sym):
            if not (at_once and tape_line.release_now(sym, "Claude moved its line to another stock")):
                tape_stream.unsubscribe(sym)
        if hold.get("depth") and depth.ws_viewer_closed(sym):
            try:
                if at_once or await depth.release_when_idle(sym):
                    from l2 import recorder as l2_recorder

                    if depth.viewer_count(sym) <= 0 and not l2_recorder.is_recording(sym):
                        depth.unsubscribe(sym)
            except Exception:
                logger.exception("AGENT lines: depth release failed for %s", sym)
        logger.info("AGENT lines: released %s", sym)
