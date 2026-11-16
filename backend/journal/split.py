"""Each trader's beside each Reports total (ADR 072, ``architecture/schema/journal.md``). Pure.

A journal trade's book is its ``owner``: ``you``, ``claude``, ``brain`` or ``earlier_bots``; one left null -- every
trade from before, an import, a demo row -- reads as yours (ADR 063's rule). A row stored before ADR 072 with owner
``bots`` reads as Claude's when its ``bot`` is ``claude``, else as Earlier bots' (the next Paper sync rewrites it).
``by_owner`` runs one Reports figure over each book's trades, and ``holders`` counts each holder's for the switch.
"""
from __future__ import annotations

from collections import Counter
from typing import Any, Callable, Iterable

from constants_owners import BOOKS, OWNER_CLAUDE, OWNER_EARLIER_BOTS, OWNER_YOU

LEGACY_BOTS = "bots"   # ADR 069's owner for every bot's trade, Claude's included


def book_of_trade(trade: dict) -> str:
    """The trade's book: its ``owner``, a stored ``bots`` row by its ``bot``, null and anything else yours."""
    owner = trade.get("owner")
    if owner == LEGACY_BOTS:
        return OWNER_CLAUDE if trade.get("bot") == OWNER_CLAUDE else OWNER_EARLIER_BOTS
    return owner if owner in BOOKS else OWNER_YOU


def bot_of_trade(trade: dict) -> str | None:
    """The retired holder inside Earlier bots; null for every other book."""
    return trade.get("bot") if book_of_trade(trade) == OWNER_EARLIER_BOTS else None


def by_owner(trades: list[dict], figure: Callable[[list[dict]], dict[str, Any]],
             keys: Iterable[str]) -> dict[str, dict[str, Any]]:
    """``figure`` over each book's trades, each kept to ``keys``."""
    wanted = tuple(keys)
    out: dict[str, dict[str, Any]] = {}
    for book in BOOKS:
        result = figure([t for t in trades if book_of_trade(t) == book])
        out[book] = {key: result[key] for key in wanted}
    return out


def holders(trades: Iterable[dict]) -> list[dict[str, Any]]:
    """Every holder with a trade: ``{owner, bot, trade_count}``, in the books' order, then by count."""
    counts = Counter((book_of_trade(t), bot_of_trade(t)) for t in trades)
    order = sorted(counts, key=lambda k: (BOOKS.index(k[0]), -counts[k], k[1] or ""))
    return [{"owner": owner, "bot": bot, "trade_count": counts[(owner, bot)]} for owner, bot in order]
