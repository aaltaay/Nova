"""The bot's stock list has one owner: stock mode (ADR 042 F).

``POST /api/bot/allowlist``, ``PATCH /api/bot/session {symbol_allowlist}`` and every desk
button set a stock through ``stock_mode.actions.set_mode`` -- Bot (Nova / Nova) to add it,
Signal only (You / You) to take it off -- so each meets stock mode's rules: the Live lock,
"you hold it", the 50-stock cap, one mode per stock, and a take-over of the exit the bot
holds. A refusal is an error with its reason; nothing is audited as done when it was not.
The list itself is this venue's (``bot.venue_levels``).
"""
from __future__ import annotations

from typing import Any

from constants_stock_mode import STOCK_MODE_SIDE_NOVA, STOCK_MODE_SIDE_YOU


async def set_one(symbol: str, *, on: bool) -> dict[str, Any]:
    """Set one stock to Bot (``on``) or Signal only; raises ``StockModeError`` with the reason."""
    from stock_mode import actions

    side = STOCK_MODE_SIDE_NOVA if on else STOCK_MODE_SIDE_YOU
    return await actions.set_mode(symbol, side, side, None)


async def set_list(symbols: list[str]) -> list[dict[str, Any]]:
    """Make this venue's bot list ``symbols``: each stock off the list goes to Signal only, each new one
    to Bot (removals first, so a replacement list fits). ``[{symbol, reason, error}]`` for each refused."""
    from bot.eligibility import normalize_symbols
    from bot.persist import load_session
    from stock_mode.errors import StockModeError

    current = normalize_symbols(load_session().get("symbol_allowlist"))
    wanted: list[str] = []
    for raw in symbols or []:
        sym = str(raw or "").strip().upper()
        if sym and sym not in wanted:
            wanted.append(sym)
    refused: list[dict[str, Any]] = []
    for sym, on in [(s, False) for s in current if s not in wanted] + [(s, True) for s in wanted if s not in current]:
        try:
            await set_one(sym, on=on)
        except StockModeError as exc:
            refused.append({"symbol": sym, "reason": exc.reason, "error": exc.message})
    return refused
