"""Whose an order is (ADR 063 decision 2, ADR 069 decision 1). Pure.

``by_of`` reads a practice ledger row's own stamps -- never its side, size or time: the bots' when its
source is ``bot``, it carries a ``bot_id``, or it is a bot's own close (sent as source ``flatten`` with the
bot's origin, ``BOT_CLOSE_ORIGINS``); a side line's Auto sell is that side's; your own Flatten is yours.
Nova's own closes -- KILL, all stop, the day cover, a margin call, the Account line's Auto sell, a flatten
with no origin -- are None: whose shares they close decides (``owners.split``). Everything else is yours.

``holder_of`` names who inside the book: ``you``, the bot's origin (``BOT_HOLDERS``; a bots' order with no
origin it can name is the strategy bot's ``bot``), or ``bots`` -- a close of the whole bots' book (the Bots
line's Auto sell, the operator's Close on a bots' row).
"""
from __future__ import annotations

from typing import Any

from constants_loss_limit import LOSS_LIMIT_SIDE_ORIGINS
from constants_owners import (
    BOT_CLOSE_ORIGINS,
    BOT_HOLDERS,
    BOTS_BOOK_CLOSE_ORIGINS,
    HOLDER_BOTS_BOOK,
    HOLDER_NAMES,
    HOLDER_STRATEGY_BOT,
    HOLDER_YOU,
    OWNER_BOTS,
    OWNER_YOU,
)

_SIDE_OF_ORIGIN = {origin: side for side, origin in LOSS_LIMIT_SIDE_ORIGINS.items()}
_NOVA_SOURCES = frozenset({"flatten", "kill", "cancel_working"})


def by_of(row: dict[str, Any]) -> str | None:
    """Whose order a practice ledger row is: ``you`` | ``bots`` | None (one of Nova's own closes)."""
    source = str(row.get("order_source") or "")
    origin = row.get("order_origin")
    if source == "bot" or row.get("bot_id") is not None or origin in BOT_CLOSE_ORIGINS:
        return OWNER_BOTS
    if origin in _SIDE_OF_ORIGIN:
        return _SIDE_OF_ORIGIN[origin]
    if origin == "ticket_flatten":
        return OWNER_YOU          # your own Flatten
    if source in _NOVA_SOURCES:
        return None
    return OWNER_YOU


def holder_of(row: dict[str, Any]) -> str | None:
    """Who in the book holds what the order opens: ``you``, a bot's origin, ``bots`` (the whole bots' book's
    close) or None (Nova's own close)."""
    owner = by_of(row)
    if owner is None:
        return None
    if owner == OWNER_YOU:
        return HOLDER_YOU
    origin = row.get("order_origin")
    if origin in BOTS_BOOK_CLOSE_ORIGINS:
        return HOLDER_BOTS_BOOK
    return origin if origin in BOT_HOLDERS else HOLDER_STRATEGY_BOT


def holder_of_order(source: str | None, origin: str | None, bot_id: str | None = None) -> str | None:
    """``holder_of`` for an order not yet in the ledger, from the command's own stamps."""
    return holder_of({"order_source": source, "order_origin": origin, "bot_id": bot_id})


def book_of(holder: str | None) -> str | None:
    """The book a holder's shares are in: ``you`` | ``bots``; None for Nova's own close."""
    if holder is None:
        return None
    return OWNER_YOU if holder == HOLDER_YOU else OWNER_BOTS


def bot_of(holder: str | None) -> str | None:
    """The wire's ``bot``: the holder inside the bots' book, null for yours and for Nova's own close."""
    return holder if book_of(holder) == OWNER_BOTS else None


def name_of(holder: str | None) -> str:
    """The holder in the words Nova says: "You", "The Live Trader", ..."""
    if holder is None:
        return "Nova"
    return HOLDER_NAMES.get(holder, HOLDER_NAMES[HOLDER_STRATEGY_BOT])
