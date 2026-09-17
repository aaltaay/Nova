"""Symbol gate: allowlist AND live Trader focus."""
from __future__ import annotations

from typing import Any

from bot.errors import BotError
from constants_bot import BOT_REASON_SYMBOL_BLOCKED, BOT_SYMBOL_ALLOWLIST_CAP


def normalize_symbols(raw: Any) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in raw or []:
        sym = str(item or "").strip().upper()
        if not sym or sym in seen:
            continue
        seen.add(sym)
        out.append(sym)
        if len(out) >= BOT_SYMBOL_ALLOWLIST_CAP:
            break
    return out


def eligible_symbols(row: dict[str, Any]) -> list[str]:
    allow = set(normalize_symbols(row.get("symbol_allowlist")))
    live = set(normalize_symbols(row.get("trader_live")))
    return sorted(allow & live)


def assert_symbol_eligible(symbol: str, row: dict[str, Any]) -> str:
    sym = (symbol or "").strip().upper()
    if not sym:
        raise BotError("symbol is required", 400, "SYMBOL_MISSING")
    if sym not in set(eligible_symbols(row)):
        raise BotError(
            f"{sym} is not on the bot allowlist and live Trader focus",
            409,
            BOT_REASON_SYMBOL_BLOCKED,
        )
    return sym


def add_symbol(row: dict[str, Any], symbol: str) -> list[str]:
    current = normalize_symbols(row.get("symbol_allowlist"))
    sym = (symbol or "").strip().upper()
    if not sym:
        raise BotError("symbol is required", 400, "SYMBOL_MISSING")
    if sym not in current and len(current) < BOT_SYMBOL_ALLOWLIST_CAP:
        current.append(sym)
    row["symbol_allowlist"] = current
    return current


def remove_symbol(row: dict[str, Any], symbol: str) -> list[str]:
    sym = (symbol or "").strip().upper()
    current = [s for s in normalize_symbols(row.get("symbol_allowlist")) if s != sym]
    row["symbol_allowlist"] = current
    return current
