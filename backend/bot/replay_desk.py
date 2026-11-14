"""The Sim replay as the bot API reads it (ADR 052): which replay is loaded, its clock, and its book.

On the Sim desk off its live edge with a replay loaded (``sim.practice.loaded``: a Session Record or a historical
window) this says which replay it is (``desk``), its clock (``venue_now``: the playhead, which stands still while
paused), the stamp a bot audit line written there carries (``audit_stamp``), and what the replay shows at the
playhead -- its book (``holds_book``) and its quote (``quote``).

ADR 072 retired the strategy bot that traded a replay, and with it the memory of its trade that went back with the
playhead: no strategy trades a replay (the brain may, in a later build). Owner: none -- every read is the Sim's.
"""
from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


# -- which replay, and its clock -------------------------------------------------------------
def desk() -> dict[str, Any] | None:
    """The replay the Sim desk trades now: ``{key, symbol, kind}``; None at the live edge, on another
    venue, or with nothing loaded. An unreadable desk is no replay (the venue gate refuses it)."""
    try:
        from sim.mode import is_replay_desk

        if not is_replay_desk():
            return None
        from sim import practice

        loaded = practice.loaded()
    except Exception:
        logger.warning("bot: the Sim replay could not be read", exc_info=True)
        return None
    if loaded is None:
        return None
    return {"key": list(loaded.key), "symbol": str(loaded.symbol).upper(), "kind": loaded.source}


def venue_now() -> float:
    """The bot's clock: the Sim playhead on the Sim venue (at its live edge it is the wall clock), else
    the wall clock. An unreadable venue is the wall clock."""
    try:
        from sim.mode import venue

        if venue() == "sim":
            from sim import session_clock

            return session_clock.now_et().timestamp()
    except Exception:
        logger.warning("bot: the venue clock could not be read -- the wall clock stands in", exc_info=True)
    return time.time()


def audit_stamp() -> dict[str, Any] | None:
    """``{key, playhead_ts}`` for a bot audit line written on a replay; None off one. Never raises."""
    here = desk()
    if here is None:
        return None
    return {"key": here["key"], "playhead_ts": venue_now()}



# -- what the replay shows the bot ----------------------------------------------------------
def holds_book(symbol: str) -> bool:
    """On a replay the depth-line rule is met by the replay's own book: the loaded symbol, with recorded
    Level 2, a window's NBBO, or a book Nova recorded that day (``sim.history_depth``). An IBKR download
    has no bid or ask of its own."""
    here = desk()
    if here is None or here["symbol"] != (symbol or "").strip().upper():
        return False
    try:
        from sim import session_clock

        at = session_clock.now_et().timestamp()
        if here["kind"] == "capture":
            from sim import capture_player

            return capture_player.book_at(at) is not None
        from sim import history_depth, history_playback

        selected = history_playback.selected()
        if selected is not None and selected.quotes is not None and len(selected.quotes) > 0:
            return True
        return history_depth.book_at(here["symbol"], at) is not None
    except Exception:
        logger.warning("bot: the replay's book could not be read for %s -- it counts as none", symbol, exc_info=True)
        return False


def book_missing(symbol: str) -> str | None:
    """On a replay, why ``symbol`` has no book there (None off a replay: the live hint stands)."""
    here = desk()
    if here is None:
        return None
    sym = (symbol or "").strip().upper()
    if here["symbol"] != sym:
        return f"the Sim replay is {here['symbol']}: the bot trades only the loaded replay"
    if here["kind"] == "capture":
        return "the Session Record holds no Level 2 at the playhead"
    return "an IBKR download has no bid or ask: load the day from the Massive files for its NBBO"


def quote(symbol: str) -> dict[str, Any] | None:
    """``{last, bid, ask}`` of the loaded replay at the playhead -- what its practice orders fill against."""
    if desk() is None:
        return None
    from sim import practice

    ref = practice.reference((symbol or "").strip().upper())
    return {"last": ref.last, "bid": ref.bid, "ask": ref.ask}
