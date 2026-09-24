"""The loss breakers' thresholds: the operator's, per venue (operator ask 2026-09-24).

"I want us to be able to change this stuff ... move that slider ... and make sure
these changes are persistent." The bot trip (soft: flatten, drop the bot to L0)
and the all-stop (hard: flatten, lock bot and manual buys until the next ET
midnight) compare the whole account's day P&L on the desk's venue
(``bot.day_pnl``). They were the product constants -$50 / -$200; now each venue
keeps its own in the bot session -- ``breakers: {VENUE: {soft_usd, hard_usd}}``,
saved with every other session field (``bot.persist``, ``bot-session.json``) and
read back at every start. Each venue has its own so loosening Paper never
loosens Live. A venue with none reads the defaults. A venue Nova cannot read
reads Live's.

Bounds: the bot trip between ``BOT_SOFT_BREAKER_LOOSEST_USD`` and
``BOT_SOFT_BREAKER_TIGHTEST_USD``, the all-stop between
``BOT_HARD_BREAKER_LOOSEST_USD`` and ``BOT_HARD_BREAKER_TIGHTEST_USD``, and the
bot trip always above the all-stop. A breaker that already fired stays fired:
moving the slider never clears the bot trip's latch or the day lock.

Owner: this module (the rules; the session file is ``bot.persist``'s).
"""
from __future__ import annotations

from typing import Any

from bot.errors import BotError
from constants_bot import (
    BOT_BREAKER_STEP_USD,
    BOT_BREAKER_VENUES,
    BOT_HARD_BREAKER_LOOSEST_USD,
    BOT_HARD_BREAKER_TIGHTEST_USD,
    BOT_HARD_BREAKER_USD,
    BOT_REASON_BREAKER_INVALID,
    BOT_SOFT_BREAKER_LOOSEST_USD,
    BOT_SOFT_BREAKER_TIGHTEST_USD,
    BOT_SOFT_BREAKER_USD,
)

_LIVE = "live"


def venue_key(venue: str | None) -> str:
    """The venue whose thresholds apply: Live for one Nova cannot read."""
    return venue if venue in BOT_BREAKER_VENUES else _LIVE


def defaults() -> dict[str, float]:
    return {"soft_usd": BOT_SOFT_BREAKER_USD, "hard_usd": BOT_HARD_BREAKER_USD}


def _stored(row: dict[str, Any]) -> dict[str, dict[str, float]]:
    raw = row.get("breakers")
    out: dict[str, dict[str, float]] = {}
    if not isinstance(raw, dict):
        return out
    for venue, entry in raw.items():
        if venue not in BOT_BREAKER_VENUES or not isinstance(entry, dict):
            continue
        try:
            soft, hard = float(entry["soft_usd"]), float(entry["hard_usd"])
        except (KeyError, TypeError, ValueError):
            continue
        if _problem(soft, hard) is None:
            out[venue] = {"soft_usd": soft, "hard_usd": hard}
    return out


def limits(row: dict[str, Any], venue: str | None) -> dict[str, float]:
    """``{soft_usd, hard_usd}`` for ``venue`` (its own, else the defaults)."""
    return dict(_stored(row).get(venue_key(venue)) or defaults())


def _problem(soft: float, hard: float) -> str | None:
    if not (BOT_SOFT_BREAKER_LOOSEST_USD <= soft <= BOT_SOFT_BREAKER_TIGHTEST_USD):
        return (f"the bot trip is between ${BOT_SOFT_BREAKER_TIGHTEST_USD:,.0f} and "
                f"${BOT_SOFT_BREAKER_LOOSEST_USD:,.0f}")
    if not (BOT_HARD_BREAKER_LOOSEST_USD <= hard <= BOT_HARD_BREAKER_TIGHTEST_USD):
        return (f"the all-stop is between ${BOT_HARD_BREAKER_TIGHTEST_USD:,.0f} and "
                f"${BOT_HARD_BREAKER_LOOSEST_USD:,.0f}")
    if soft <= hard:
        return "the bot trip must sit above the all-stop -- it trips first"
    return None


def apply(row: dict[str, Any], patch: Any, current_venue: str | None) -> tuple[str, dict, dict] | None:
    """``PATCH {breakers: {venue?, soft_usd?, hard_usd?}}`` -- the named venue's (else the
    desk's). Returns ``(venue, before, after)`` when anything changed."""
    if not isinstance(patch, dict):
        raise BotError("breakers is an object: {venue?, soft_usd?, hard_usd?}", 400, BOT_REASON_BREAKER_INVALID)
    venue = patch.get("venue") or current_venue
    if venue not in BOT_BREAKER_VENUES:
        raise BotError(f"breakers are per venue: one of {', '.join(BOT_BREAKER_VENUES)}", 400,
                       BOT_REASON_BREAKER_INVALID)
    before = limits(row, venue)
    after = dict(before)
    for key in ("soft_usd", "hard_usd"):
        if key not in patch or patch[key] is None:
            continue
        try:
            value = float(patch[key])
        except (TypeError, ValueError):
            raise BotError(f"{key} is a dollar amount", 400, BOT_REASON_BREAKER_INVALID) from None
        if value != value:                  # NaN
            raise BotError(f"{key} is a dollar amount", 400, BOT_REASON_BREAKER_INVALID)
        after[key] = round(round(value / BOT_BREAKER_STEP_USD) * BOT_BREAKER_STEP_USD, 2)
    why = _problem(after["soft_usd"], after["hard_usd"])
    if why:
        raise BotError(why, 400, BOT_REASON_BREAKER_INVALID)
    if after == before:
        return None
    stored = _stored(row)
    if after == defaults():
        stored.pop(venue, None)             # back on the defaults: nothing of the operator's to keep
    else:
        stored[venue] = after
    row["breakers"] = stored
    return venue, before, after


def view(row: dict[str, Any], venue: str | None) -> dict[str, Any]:
    """What the Bots page draws: the desk's venue's thresholds, every venue's, and the bounds."""
    here = venue_key(venue)
    stored = _stored(row)
    return {
        "venue": here, **limits(row, here), "custom": here in stored, "defaults": defaults(),
        "by_venue": {v: stored.get(v) or defaults() for v in BOT_BREAKER_VENUES},
        "bounds": {"soft_usd": [BOT_SOFT_BREAKER_LOOSEST_USD, BOT_SOFT_BREAKER_TIGHTEST_USD],
                   "hard_usd": [BOT_HARD_BREAKER_LOOSEST_USD, BOT_HARD_BREAKER_TIGHTEST_USD],
                   "step_usd": BOT_BREAKER_STEP_USD},
    }
