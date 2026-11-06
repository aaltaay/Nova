"""No new buys: the order an account refuses after a daily loss line, and the words (ADR 056, ADR 061).

``execution.service`` asks ``buy_refusal`` with the door's own venue for every place, bracket or
exit pair from a non-protective source, yours and the bots' alike: a BUY, and a SELL that opens a
short. Selling what is held, a BUY that covers a short (ADR 048), cancels, Flatten and KILL are
never refused. The bot and stock mode ask ``stopped`` / ``buys_stopped`` for their side.

Which line holds whom (ADR 061): the Account line's trip holds every new buy on the account; the
You line's holds only yours, and the Bots line's only the bots'. Whose an order is comes from its
own source: ``bot`` is the bots' (every bot entry, Auto-entry and the Live Trader bot's steps), any
other source is yours. A buy is refused only while No new buys is checked and a line that holds
that side tripped today; raising a limit, turning a line off or unchecking No new buys clears the
trips (``loss_limit.state.clear``).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from constants_loss_limit import (
    LOSS_LIMIT_LINE_ACCOUNT,
    LOSS_LIMIT_LINE_BOTS,
    LOSS_LIMIT_LINE_YOU,
    LOSS_LIMIT_REASON_NO_NEW_BUYS,
)

_ET = ZoneInfo("America/New_York")
_NAMES = {"live": "Live", "paper": "Paper", "sim": "Sim"}
_PROTECTIVE = frozenset({"kill", "cancel_working", "flatten"})
STILL_WORKS = "Selling what you hold, covering a short, cancels, Flatten and KILL still work."
TO_BUY_AGAIN = "To buy again, raise the limit or uncheck No new buys in Settings > Loss limits."
# Each line in words: what reached it, whose loss, whose limit, who may not buy, who still may.
_LINE_WORDS = {
    LOSS_LIMIT_LINE_ACCOUNT: {"reached": "Daily loss limit reached", "down": "down", "limit": "your",
                              "held": "no new buys", "still": "", "works": STILL_WORKS, "again": TO_BUY_AGAIN},
    LOSS_LIMIT_LINE_YOU: {"reached": "Your trades' daily loss limit reached", "down": "your trades down",
                          "limit": "your", "held": "no new buys of yours", "still": "; the bots still trade",
                          "works": STILL_WORKS,
                          "again": "To buy again, raise your trades' limit or uncheck No new buys in "
                                   "Settings > Loss limits."},
    LOSS_LIMIT_LINE_BOTS: {"reached": "The bots' daily loss limit reached", "down": "the bots' trades down",
                           "limit": "their", "held": "no new bot entries", "still": "; your own buys still work",
                           "works": "A bot's own exits, selling, covering a short, cancels, Flatten and KILL "
                                    "still work.",
                           "again": "To let the bots buy again, raise the bots' limit or uncheck No new buys in "
                                    "Settings > Loss limits."},
}


def account_name(account: str | None) -> str:
    return _NAMES.get(str(account), str(account))


def money(value: float | None) -> str:
    if value is None:
        return "unknown"
    text = f"{abs(float(value)):,.2f}"
    return f"${text[:-3] if text.endswith('.00') else text}"


def actor_of(source: str | None) -> str:
    """Whose order an opening command is, from its own source: ``bots`` for ``bot``, else ``you``."""
    return LOSS_LIMIT_LINE_BOTS if source == "bot" else LOSS_LIMIT_LINE_YOU


def _clock(epoch: Any) -> str | None:
    if not isinstance(epoch, (int, float)) or isinstance(epoch, bool):
        return None
    return f"{datetime.fromtimestamp(float(epoch), tz=_ET):%H:%M} ET"


def _until(epoch: float) -> str:
    end = datetime.fromtimestamp(epoch, tz=_ET)
    return f"{end:%H:%M} ET {end:%a} {end:%b} {end.day}"


def line_stop(account: str, line: str, now: float | None = None) -> dict[str, Any] | None:
    """``{account, line, tripped_at, loss, limit_usd, until, text}`` while ``line`` stops new buys on ``account``."""
    from loss_limit import settings, state

    if not settings.current()["no_new_buys"]:
        return None
    row = state.record(account, now, line=line)
    if not row.get("tripped_at"):
        return None
    words = _LINE_WORDS[line]
    end = state.until(now)
    when = _clock(row.get("tripped_at"))
    said = f"{words['reached']} on {account_name(account)}" + (f" at {when}" if when else "")
    said += (f" ({words['down']} {money(row.get('tripped_loss'))} against {words['limit']} "
             f"{money(row.get('limit_usd'))} limit)")
    return {"account": account, "line": line, "tripped_at": row.get("tripped_at"), "loss": row.get("tripped_loss"),
            "limit_usd": row.get("limit_usd"), "until": end,
            "text": f"{said}: {words['held']} until {_until(end)}{words['still']}. {words['works']} {words['again']}"}


def stopped(account: str | None, now: float | None = None, *, actor: str) -> dict[str, Any] | None:
    """The stop holding ``actor``'s (``you`` | ``bots``) new buys on ``account``, or None while they are open:
    the Account line's trip, which holds everyone, else ``actor``'s own line's."""
    if account is None:
        return None
    for line in (LOSS_LIMIT_LINE_ACCOUNT, actor):
        held = line_stop(account, line, now)
        if held is not None:
            return held
    return None


def buys_stopped(account: str | None, now: float | None = None, *, actor: str) -> bool:
    return stopped(account, now, actor=actor) is not None


def buy_refusal(
    side: str | None,
    source: str | None,
    venue: str | None,
    *,
    short_entry: bool = False,
    covers: bool = False,
    origin: str | None = None,
) -> dict[str, Any] | None:
    """``{code, text}`` when ``venue`` refuses this order under No new buys, else None.

    It refuses what opens or adds: a BUY that covers nothing, or a SELL that opens a short -- held by
    the Account line, or by the line of the side the order's source names. Claude's lane on Paper has its own
    daily max loss (ADR 068, operator 2026-10-26: "a max loss of $500 ... for claude lane"), checked by
    ``agent_trader.rules`` before the door, so the shared lines do not stop Claude's buys there."""
    upper = (side or "").upper()
    opens = (upper == "BUY" and not covers) or (upper == "SELL" and short_entry)
    if not opens or source in _PROTECTIVE:
        return None
    if origin == "claude" and venue == "paper":
        return None
    held = stopped(venue, actor=actor_of(source))
    if held is None:
        return None
    return {"code": LOSS_LIMIT_REASON_NO_NEW_BUYS, "text": held["text"]}
