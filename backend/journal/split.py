"""Yours and the bots' beside each Reports total (ADR 069 decision 6, ``architecture/schema/journal.md``). Pure.

A journal trade's book is its ``owner``; one left null -- every trade from before, an import, a demo row --
reads as yours (ADR 063's rule). ``by_owner`` runs one Reports figure over each book's trades, and ``holders``
counts each holder's for the switch's Bots menu.
"""
from __future__ import annotations

from collections import Counter
from typing import Any, Callable, Iterable

from constants_owners import OWNER_BOTS, OWNER_YOU, OWNERS


def book_of_trade(trade: dict) -> str:
    """``bots`` for a bots' trade, ``you`` for every other."""
    return OWNER_BOTS if trade.get("owner") == OWNER_BOTS else OWNER_YOU


def bot_of_trade(trade: dict) -> str | None:
    """The holder inside the bots' book; null for yours."""
    return trade.get("bot") if book_of_trade(trade) == OWNER_BOTS else None


def by_owner(trades: list[dict], figure: Callable[[list[dict]], dict[str, Any]],
             keys: Iterable[str]) -> dict[str, dict[str, Any]]:
    """``figure`` over yours and over the bots' trades, each kept to ``keys``."""
    wanted = tuple(keys)
    out: dict[str, dict[str, Any]] = {}
    for book in OWNERS:
        result = figure([t for t in trades if book_of_trade(t) == book])
        out[book] = {key: result[key] for key in wanted}
    return out


def holders(trades: Iterable[dict]) -> list[dict[str, Any]]:
    """Every holder with a trade: ``{owner, bot, trade_count}``, yours first, then the bots by count."""
    counts = Counter((book_of_trade(t), bot_of_trade(t)) for t in trades)
    order = sorted(counts, key=lambda k: (k[0] != OWNER_YOU, -counts[k], k[1] or ""))
    return [{"owner": owner, "bot": bot, "trade_count": counts[(owner, bot)]} for owner, bot in order]
