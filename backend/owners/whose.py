"""Whose an order is (ADR 072 decision 2, ``architecture/schema/traders.md``). Pure.

``by_of`` reads a practice ledger row's own stamps -- never its side, size or time -- in this order: origin
``claude`` or ``loss_limit_claude`` is Claude's; ``brain`` or ``loss_limit_brain`` the brain's; a retired bot's
(source ``bot``, a ``bot_id``, or one of the retired origins and the whole-book closes) Earlier bots'; your own
Flatten and the You line's Auto sell yours. Nova's own closes -- KILL, the day cover, a margin call, the Account
line's Auto sell, a lapsed lease, a flat-by close -- are None: whose shares they close decides (``owners.split``).
Everything else is yours. A ledger written before ADR 072 reads with the same rule, so Claude's past fills are
Claude's and every other bot's are Earlier bots'.

``holder_of`` names who holds what the order opens: ``you``, ``claude``, ``brain``, a retired bot by its origin
(the strategy bot's ``bot`` when it names none) or ``bots`` -- a close of every holder but you (ADR 069's whole
bots' book: the Bots line's Auto sell, the retired Close on a bots' row).
"""
from __future__ import annotations

from typing import Any

from constants_owners import (
    BOTS_BOOK_CLOSE_ORIGINS,
    EARLIER_BOT_HOLDERS,
    HOLDER_BOTS_BOOK,
    HOLDER_NAMES,
    HOLDER_STRATEGY_BOT,
    HOLDER_YOU,
    OWNER_BRAIN,
    OWNER_CLAUDE,
    OWNER_EARLIER_BOTS,
    OWNER_YOU,
    TRADER_LOSS_ORIGINS,
)

_NOVA_SOURCES = frozenset({"flatten", "kill", "cancel_working"})
_EARLIER_ORIGINS = frozenset({*EARLIER_BOT_HOLDERS, *BOTS_BOOK_CLOSE_ORIGINS})
_YOUR_ORIGINS = frozenset({"ticket_flatten", "loss_limit_you"})
_TRADER_ORIGINS = {OWNER_CLAUDE: OWNER_CLAUDE, OWNER_BRAIN: OWNER_BRAIN, **TRADER_LOSS_ORIGINS}


def by_of(row: dict[str, Any]) -> str | None:
    """Whose order a practice ledger row is: ``you`` | ``claude`` | ``brain`` | ``earlier_bots`` | None (one of
    Nova's own closes)."""
    origin = row.get("order_origin")
    if origin in _TRADER_ORIGINS:
        return _TRADER_ORIGINS[origin]
    source = str(row.get("order_source") or "")
    if source == "bot" or row.get("bot_id") is not None or origin in _EARLIER_ORIGINS:
        return OWNER_EARLIER_BOTS
    if origin in _YOUR_ORIGINS:
        return OWNER_YOU
    if source in _NOVA_SOURCES:
        return None
    return OWNER_YOU


def holder_of(row: dict[str, Any]) -> str | None:
    """Who holds what the order opens: ``you``, ``claude``, ``brain``, a retired bot's origin, ``bots`` (a close of
    every holder but you) or None (Nova's own close)."""
    owner = by_of(row)
    if owner in (None, OWNER_YOU, OWNER_CLAUDE, OWNER_BRAIN):
        return owner
    origin = row.get("order_origin")
    if origin in BOTS_BOOK_CLOSE_ORIGINS:
        return HOLDER_BOTS_BOOK
    return origin if origin in EARLIER_BOT_HOLDERS else HOLDER_STRATEGY_BOT


def holder_of_order(source: str | None, origin: str | None, bot_id: str | None = None) -> str | None:
    """``holder_of`` for an order not yet in the ledger, from the command's own stamps."""
    return holder_of({"order_source": source, "order_origin": origin, "bot_id": bot_id})


def book_of(holder: str | None) -> str | None:
    """The book a holder's shares are in: ``you`` | ``claude`` | ``brain`` | ``earlier_bots``; None for Nova's own
    close."""
    if holder is None:
        return None
    if holder in (HOLDER_YOU, OWNER_CLAUDE, OWNER_BRAIN):
        return holder
    return OWNER_EARLIER_BOTS


def bot_of(holder: str | None) -> str | None:
    """The wire's ``bot``: which retired bot, on Earlier bots' rows only (``bot`` for a whole-book close)."""
    if book_of(holder) != OWNER_EARLIER_BOTS:
        return None
    return HOLDER_STRATEGY_BOT if holder == HOLDER_BOTS_BOOK else holder


def name_of(holder: str | None) -> str:
    """The holder in the words Nova says: "You", "Claude", "The brain", "The Live Trader", ..."""
    if holder is None:
        return "Nova"
    return HOLDER_NAMES.get(holder, HOLDER_NAMES[HOLDER_STRATEGY_BOT])
