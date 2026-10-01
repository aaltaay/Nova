"""Activate: one control, one meaning, never silently carried (ADR 042 B).

Activate (``POST /api/bot/session/arm``) says the bot may trade the go triggers of the
setups at Strategy on this venue. It refuses, with a plain reason the desk shows before
the press and after it:

- ``BOT_LIVE_NOT_BUILT`` on Live, ``BOT_REPLAY_DESK`` on Sim off the live edge,
  ``BOT_VENUE_UNKNOWN`` when the venue cannot be read;
- ``BOT_LEVEL_NOT_STRATEGY`` with the master below Strategy;
- ``BOT_NO_SETUP_AT_STRATEGY`` with no setup at effective Strategy;
- ``BOT_PADLOCK_LOCKED`` while the desk's padlock is locked;
- ``BOT_TRIP_LATCHED`` while this venue's bot trip holds, unless re-enable is asked.

The backend clears Activate -- with a ``deactivate`` audit line and the session's
``deactivated: {at, reason, text}`` -- on every process start (``clear_on_load`` /
``note_start``: spend arming never survives a start either, ADR 018), when anyone locks
the padlock (``on_disarm``, called from ``ibkr.safety``), on a venue change
(``bot.venue_levels``), with the master below Strategy or no setup left at Strategy
(``bot.autonomy``), on a trip (``bot.autonomy.drop_to_l0``) and by the operator.

Owner: this module (the rules; the session file is ``bot.persist``'s).
"""
from __future__ import annotations

import logging
import time
from typing import Any

from bot.errors import BotError
from constants_bot import (
    BOT_LEVEL_STRATEGY,
    BOT_LIVE_NOT_BUILT_TEXT,
    BOT_REASON_LEVEL_NOT_STRATEGY,
    BOT_REASON_LIVE_NOT_BUILT,
    BOT_REASON_NO_SETUP_AT_STRATEGY,
    BOT_REASON_PADLOCK_LOCKED,
    BOT_REASON_REPLAY_DESK,
    BOT_REASON_TRIP_LATCHED,
    BOT_REASON_VENUE_UNKNOWN,
    BOT_TZ,
)

logger = logging.getLogger(__name__)

_TEXT = {
    "restart": "Nova restarted: Activate never survives a restart -- press Activate again",
    "padlock": "the padlock was locked: Activate needs it unlocked -- unlock it, then Activate again",
    "venue": "the desk moved to another venue: Activate never carries into another venue",
    "level": "the master level left Strategy",
    "no_setup": "no setup is at Strategy any more",
    "bot_trip": "the bot trip fired: the bot went to Off",
    "all_stop": "the all-stop fired: the bot went to Off and buys are locked for the day",
    "operator": "you deactivated the bot",
}
# Set when the first load of this process found Activate on and cleared it (in memory);
# ``note_start`` writes the file and the audit line from the API process only.
_cleared_on_load: dict[str, Any] | None = None


# -- reads ---------------------------------------------------------------------------
def venue_state() -> tuple[str | None, bool, bool]:
    """``(venue, live_edge, readable)``: the desk venue, whether Sim follows the wall clock, and
    whether both could be read (an unreadable venue counts as Live)."""
    try:
        from sim.mode import is_replay_desk, venue

        current = venue()
    except Exception:
        logger.warning("bot: the desk venue is unreadable -- it counts as Live", exc_info=True)
        return None, False, False
    try:
        edge = not bool(is_replay_desk())
    except Exception:
        logger.warning("bot: the Sim live edge is unreadable -- it counts as a replay", exc_info=True)
        return current, False, True
    return current, edge, True


def venue_block(venue: str | None, live_edge: bool, readable: bool = True) -> tuple[str, str] | None:
    """``(code, text)`` when Nova's bot cannot trade on this venue, else None."""
    from constants_sim import DESK_PRACTICE_VENUES

    if not readable or venue is None:
        return BOT_REASON_VENUE_UNKNOWN, "Nova cannot read the desk's venue, so it counts as Live: the bot trades nothing"
    if venue not in DESK_PRACTICE_VENUES:
        return BOT_REASON_LIVE_NOT_BUILT, BOT_LIVE_NOT_BUILT_TEXT
    if not live_edge:
        return BOT_REASON_REPLAY_DESK, ("Sim is off its live edge -- a replay: the bot trades live triggers only. "
                                        "Follow the wall clock to come back to the live edge")
    return None


def padlock() -> tuple[bool, str | None]:
    """Whether the desk's padlock is unlocked (spend armed on this venue), and why not."""
    try:
        from ibkr.trading_allowed import places_allowed

        ok, reason = places_allowed()
    except Exception:
        logger.warning("bot: the padlock is unreadable -- it counts as locked", exc_info=True)
        return False, "the padlock could not be read (the backend log has the error): it counts as locked"
    return bool(ok), None if ok else (reason or "the padlock is locked")


def hhmm(ts: Any) -> str:
    from datetime import datetime
    from zoneinfo import ZoneInfo

    try:
        return datetime.fromtimestamp(float(ts), ZoneInfo(BOT_TZ)).strftime("%H:%M")
    except (TypeError, ValueError, OverflowError, OSError):
        return "?"


def money(value: Any) -> str:
    """``-$55.00`` / ``$12.50``."""
    v = float(value)
    return f"{'-' if v < 0 else ''}${abs(v):,.2f}"


def trip_text(row: dict[str, Any]) -> str:
    at, pnl = row.get("soft_breaker_at"), row.get("soft_breaker_pnl")
    when = f" at {hhmm(at)} ET" if at else " today"
    said = f" (P&L {money(pnl)})" if isinstance(pnl, (int, float)) else ""
    return f"The bot trip fired{when}{said}. Activate with re-enable to trade again today."


# -- Activate ------------------------------------------------------------------------
def refusal(row: dict[str, Any], *, reenable: bool = False) -> BotError | None:
    """Why Activate refuses now (the first rule that fails), else None."""
    from bot.clock import soft_latched
    from bot.setup_levels import at_strategy, master

    venue, edge, readable = venue_state()
    blocked = venue_block(venue, edge, readable)
    if blocked is not None:
        return BotError(blocked[1], 409, blocked[0])
    if master(row) < BOT_LEVEL_STRATEGY:
        return BotError("the master level is below Strategy -- raise it to Strategy, then Activate", 409,
                        BOT_REASON_LEVEL_NOT_STRATEGY)
    if not at_strategy(row):
        return BotError("no setup is at Strategy -- set at least one setup to Strategy, then Activate", 409,
                        BOT_REASON_NO_SETUP_AT_STRATEGY)
    ok, why = padlock()
    if not ok:
        return BotError(f"the desk padlock is locked ({why}) -- unlock it, then Activate", 409,
                        BOT_REASON_PADLOCK_LOCKED)
    if soft_latched(row) and not reenable:
        return BotError(trip_text(row), 409, BOT_REASON_TRIP_LATCHED)
    return None


def assert_can_activate(row: dict[str, Any], *, reenable: bool = False) -> None:
    refused = refusal(row, reenable=reenable)
    if refused is not None:
        raise refused


# -- deactivate ------------------------------------------------------------------------
def deactivate(row: dict[str, Any], reason: str, text: str | None = None, *, now: float | None = None) -> bool:
    """Clear Activate on ``row`` (the caller saves it). Stamps ``deactivated`` when it was on.

    Returns whether it was on (the caller writes the ``deactivate`` audit line then)."""
    from bot.arming import clear_arm_fields, is_desk_active

    was = is_desk_active(row)
    clear_arm_fields(row)
    if was:
        row["deactivated"] = {"at": time.time() if now is None else float(now), "reason": reason,
                              "text": text or _TEXT.get(reason, reason)}
    return was


def record(reason: str, text: str | None = None, **inputs: Any) -> None:
    """The ``deactivate`` audit line: who cleared Activate and why."""
    from bot.audit import record as audit

    try:
        audit(action="deactivate", outcome="ok", reason=text or _TEXT.get(reason, reason),
              inputs={"reason": reason, **inputs})
    except Exception:
        logger.warning("bot audit: deactivate (%s) not recorded", reason, exc_info=True)


def deactivate_now(reason: str, text: str | None = None, **inputs: Any) -> bool:
    """Load, clear, save and record. Returns whether Activate was on."""
    from bot.persist import load_session, save_session

    row = load_session()
    was = deactivate(row, reason, text)
    if was:
        save_session(row)
        record(reason, text, **inputs)
    return was


def on_disarm(reason: str = "") -> None:
    """``ibkr.safety.set_armed``: the padlock went from unlocked to locked, by anyone.

    A disarm that is part of a venue change is the venue's (``bot.venue_levels``, reason
    ``venue``): at that moment the desk already shows the new venue while the session still
    holds the old venue's dial."""
    try:
        from bot.persist import load_session
        from sim.mode import venue

        row = load_session()
        if row.get("level_venue") not in (None, venue()):
            return
        deactivate_now("padlock", f"the padlock was locked ({reason or 'disarmed'}): Activate needs it unlocked",
                       disarm=reason or None)
    except Exception:
        # The padlock is locked whatever happens here; the bot reads the padlock before every
        # send too, so an unreadable session cannot fire. Said, never swallowed.
        logger.exception("bot: Activate could not be cleared after the padlock was locked")


def clear_on_load(row: dict[str, Any]) -> None:
    """``bot.persist``'s first load in this process: Activate never survives a start.

    In memory only (any reader of this process sees it cleared at once); ``note_start`` writes
    the file and the audit line from the API process, so a tool that only reads the session
    never rewrites the desk's file."""
    global _cleared_on_load
    if deactivate(row, "restart"):
        _cleared_on_load = dict(row["deactivated"])


def note_start() -> None:
    """The API process started its bot (``bot.first_pullback.runner.run``): save and record a
    clear made on load."""
    global _cleared_on_load
    if _cleared_on_load is None:
        return
    stamp, _cleared_on_load = _cleared_on_load, None
    try:
        from bot.persist import save_session

        save_session()
        record("restart", stamp.get("text"))
    except Exception:
        logger.exception("bot: the restart's deactivation was not saved")


def reset_for_tests() -> None:
    global _cleared_on_load
    _cleared_on_load = None
