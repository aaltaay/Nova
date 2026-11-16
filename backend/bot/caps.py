"""Your risk per trade on each venue (ADR 042 E), the one write left on the bot session after ADR 072.

The Trader's plan card and the Setups board size "Stage ticket" by the venue sleeve's ``risk_usd``; the sleeve is
stored on the bot session, so ``PATCH /api/bot/session {caps: {venue?, risk_usd?, ...}}`` stays for it alone. Every
other key a PATCH sends (a level, a setup's level, the stocks, Activate) belongs to the retired bots and is refused in
words. Only the desk writes it: a brain cannot.
"""
from __future__ import annotations

import logging
from typing import Any

from bot.errors import BotError
from bot.persist import load_session, save_session
from constants_bot import (
    BOT_REASON_CAPS_INVALID,
    BOT_REASON_STRATEGIES_WATCH,
    BOT_STRATEGIES_WATCH_TEXT,
    BOT_VENUES,
)

logger = logging.getLogger(__name__)

# Keys a PATCH may carry besides ``caps``: the desk's own token is accepted and ignored.
_IGNORED = frozenset({"desk_arm_token"})


def apply(body: dict[str, Any]) -> dict[str, Any]:
    """Apply ``body["caps"]`` to the named venue's sleeve (default: the desk's venue) and return the saved row."""
    retired = sorted(k for k in body if k not in _IGNORED and k != "caps")
    if retired:
        raise BotError(f"{BOT_STRATEGIES_WATCH_TEXT} Only caps (your risk per trade) is set here; "
                       f"refused: {', '.join(retired)}.", 410, BOT_REASON_STRATEGIES_WATCH)
    patch = body.get("caps")
    if not isinstance(patch, dict) or not patch:
        raise BotError("send caps: {venue?, risk_usd?, ...}", 400, BOT_REASON_CAPS_INVALID)
    from bot.door import current_venue
    from bot.sleeve import apply as apply_sleeve
    from bot.venue_levels import dial_of, put

    venue = patch.get("venue") or current_venue()
    if venue not in BOT_VENUES:
        raise BotError(f"caps.venue is one of {', '.join(BOT_VENUES)}", 400, BOT_REASON_CAPS_INVALID)
    row = load_session()
    # The desk venue's sleeve is the session's own fields; any other venue's is its stored dial (``venue_levels``).
    after, changed = apply_sleeve(dial_of(row, venue).get("caps"), patch)
    put(row, venue, "caps", after)
    saved = save_session(row)
    if changed:
        _audit(venue, changed)
    return saved


def _audit(venue: str, changed: dict[str, tuple[Any, Any]]) -> None:
    """The audit stream keeps every change to a venue's sleeve (ADR 042 E)."""
    from bot.audit import record

    try:
        record(action="caps", outcome=venue,
               reason=f"{venue} sleeve: " + ", ".join(f"{k} {a!r} -> {b!r}" for k, (a, b) in sorted(changed.items())),
               inputs={"venue": venue, "changed": {k: {"from": a, "to": b} for k, (a, b) in changed.items()}})
    except Exception:
        logger.warning("bot audit: sleeve change not recorded", exc_info=True)
