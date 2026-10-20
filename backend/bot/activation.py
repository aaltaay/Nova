"""Activate: one control, one meaning, never silently carried (ADR 042 B).

Activate (``POST /api/bot/session/arm``) says the bot may trade the go triggers of the
setups at Strategy on this venue. It refuses, with a plain reason the desk shows before
the press and after it:

- ``BOT_LIVE_NOT_BUILT`` on Live, ``BOT_REPLAY_DESK`` on Sim off the live edge with nothing loaded
  (a loaded replay is traded like Paper, ADR 052), ``BOT_VENUE_UNKNOWN`` when the venue cannot be read;
- ``BOT_LEVEL_NOT_STRATEGY`` with the master below Strategy;
- ``BOT_NO_SETUP_AT_STRATEGY`` with no setup at effective Strategy;
- ``BOT_PADLOCK_LOCKED`` while the desk's padlock is locked (``bot.padlock_gate``: no bot turns on over it).

No loss limit turns the bot off (ADR 056): the daily loss limit's No new buys refuses entries at the
execution door, and the ``loss_limit`` gate says so.

The backend clears Activate -- with a ``deactivate`` audit line and the session's
``deactivated: {at, reason, text}`` -- on every process start (``clear_on_load`` /
``note_start``: spend arming never survives a start either, ADR 018), on a venue change
(``bot.venue_levels``), with the master below Strategy (``bot.autonomy``) and by the operator. No setup
left at Strategy no longer clears it (2026-10-15): the Bot switch is the top of three keys, and with any key off no
bot places an order, so a lower key must not flip it (bot.md, "The three keys"). Older lines may read ``no_setup``,
and ``padlock`` (until 2026-10-16 locking the padlock turned the bot off; the padlock is separate now and blocks
every order itself).

ADR 044: the desk shows one Bot switch per venue instead of the master dial and Activate
(``bot.switch``): ON is the master at Strategy and Activate in one step, refused with
Activate's own codes (``refusal``); OFF leaves the master at Eyes.

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
    BOT_REASON_REPLAY_DESK,
    BOT_REASON_VENUE_UNKNOWN,
    BOT_REPLAY_NOTHING_LOADED_TEXT,
    BOT_TZ,
)

logger = logging.getLogger(__name__)

_TEXT = {
    "restart": "Nova restarted: the bot never stays on across a restart -- turn the Bot switch on again",
    # Only rows written before 2026-10-16, when locking the padlock turned the bot off (``stamp_text``).
    "padlock": "the padlock was locked, so the bot went off (the rule before 2026-10-16) -- turn the Bot switch on "
               "again; the padlock is separate now and stays as you set it",
    "venue": "the desk moved to another venue: the bot never carries into another venue",
    "level": "the master level left Strategy",
    "no_setup": "no setup is at Strategy any more",
    "operator": "you turned the bot off",
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
    """``(code, text)`` when Nova's bot cannot trade on this venue, else None.

    Sim off its live edge is a replay: the bot trades the loaded replay's go triggers there (ADR 052), so
    only a replay desk with nothing loaded refuses."""
    from constants_sim import DESK_PRACTICE_VENUES

    if not readable or venue is None:
        return BOT_REASON_VENUE_UNKNOWN, "Nova cannot read the desk's venue, so it counts as Live: the bot trades nothing"
    if venue not in DESK_PRACTICE_VENUES:
        return BOT_REASON_LIVE_NOT_BUILT, BOT_LIVE_NOT_BUILT_TEXT
    if not live_edge:
        from bot.replay_desk import desk

        if desk() is None:
            return BOT_REASON_REPLAY_DESK, BOT_REPLAY_NOTHING_LOADED_TEXT
    return None


def live_trader_keys(venue: str | None = None) -> list[str]:
    """The Live Trader hosts whose key is on: on Paper each counts as a strategy On (ADR 055)."""
    if venue is None:
        venue = venue_state()[0]
    if venue != "paper":
        return []
    try:
        from bot.live_trader import settings

        return settings.hosts_on()
    except Exception:  # maintainer: allow-swallow unreadable keys count none On: the safe side, said in the log
        logger.warning("bot: the Live Trader keys are unreadable -- none counts as On", exc_info=True)
        return []


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


# -- Activate ------------------------------------------------------------------------
def refusal(row: dict[str, Any]) -> BotError | None:
    """Why Activate (and the Bot switch) refuses now (the first rule that fails), else None. The padlock's rule is
    ``bot.padlock_gate``'s, the one every bot's ON obeys (operator decision 2026-10-20)."""
    from bot.setup_levels import at_strategy, master

    venue, edge, readable = venue_state()
    blocked = venue_block(venue, edge, readable)
    if blocked is not None:
        return BotError(blocked[1], 409, blocked[0])
    if master(row) < BOT_LEVEL_STRATEGY:
        return BotError("the master level is below Strategy -- raise it to Strategy, then Activate", 409,
                        BOT_REASON_LEVEL_NOT_STRATEGY)
    if not at_strategy(row) and not live_trader_keys(venue):
        return BotError("no setup is at Strategy and no Live Trader key is on -- set at least one setup to "
                        "Strategy or turn a host's key on, then Activate", 409, BOT_REASON_NO_SETUP_AT_STRATEGY)
    from bot.padlock_gate import refusal as padlock_refusal

    return padlock_refusal()


def assert_can_activate(row: dict[str, Any]) -> None:
    refused = refusal(row)
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


def stamp_text(stamp: dict[str, Any]) -> str | None:
    """The words of a ``deactivated`` stamp. A ``padlock`` stamp is from before 2026-10-16 and its saved words said
    the Bot switch unlocks the padlock, which it no longer does: it reads today's words (Codex review, PR #1019)."""
    if stamp.get("reason") == "padlock":
        return _TEXT["padlock"]
    text = stamp.get("text")
    return str(text) if text else None


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
