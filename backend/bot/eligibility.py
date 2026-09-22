"""Symbol gates.

Eyes (watch / propose) see **allowlist AND live Trader focus** -- the tabs the
UI reports through ``POST /api/bot/focus/sync``. A bot **fires** only on a
symbol that is on its allowlist AND whose depth line the backend itself holds
(ADR 020 second pass, 2026-09-21): the backend cannot see UI tabs, so the held
line -- an open Trader Level 2 or a Session Record line, per
``ibkr.depth.state`` -- is the server-side fact. No line budget.
"""
from __future__ import annotations

from typing import Any

from bot.errors import BotError
from constants_bot import (
    BOT_NO_DEPTH_LINE_HINT,
    BOT_REASON_NO_DEPTH_LINE,
    BOT_REASON_SYMBOL_BLOCKED,
    BOT_SYMBOL_ALLOWLIST_CAP,
)


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


def _require_symbol(symbol: str) -> str:
    sym = (symbol or "").strip().upper()
    if not sym:
        raise BotError("symbol is required", 400, "SYMBOL_MISSING")
    return sym


def assert_symbol_eligible(symbol: str, row: dict[str, Any]) -> str:
    """Eyes gate: allowlist AND the live Trader focus the UI reported."""
    sym = _require_symbol(symbol)
    if sym not in set(eligible_symbols(row)):
        raise BotError(
            f"{sym} is not on the bot allowlist and live Trader focus",
            409,
            BOT_REASON_SYMBOL_BLOCKED,
        )
    return sym


def holds_depth_line(symbol: str) -> bool:
    """True when the backend holds this symbol's depth line right now.

    ``is_subscribed`` covers a Trader Level 2 tab (a real IBKR line, or the
    replay slot a Sim desk serves); ``is_live`` covers the real line Session
    Record holds even with no tab open. Anything else -- including a depth
    module that cannot be read -- is "no line": the gate fails closed.
    """
    sym = (symbol or "").strip().upper()
    if not sym:
        return False
    try:
        from ibkr.depth import state as _depth

        return bool(_depth.is_subscribed(sym) or _depth.is_live(sym))
    except Exception:
        return False


def assert_depth_line(symbol: str) -> str:
    sym = _require_symbol(symbol)
    if not holds_depth_line(sym):
        raise BotError(
            f"{sym} holds no depth line -- {BOT_NO_DEPTH_LINE_HINT}",
            409,
            BOT_REASON_NO_DEPTH_LINE,
        )
    return sym


def assert_symbol_can_fire(symbol: str, row: dict[str, Any]) -> str:
    """Fire gate, enforced in one place: allowlist AND a held depth line.

    The allowlist stays fail-closed (empty list fires nothing). The UI's
    reported focus is not consulted here -- a Session Record line counts, and
    a tab the UI forgot to report does not matter, because the line itself is
    the fact.
    """
    sym = _require_symbol(symbol)
    if sym not in set(normalize_symbols(row.get("symbol_allowlist"))):
        raise BotError(
            f"{sym} is not on the bot allowlist",
            409,
            BOT_REASON_SYMBOL_BLOCKED,
        )
    return assert_depth_line(sym)


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
