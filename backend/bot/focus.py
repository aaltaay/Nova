"""Bot focus shares the Trader max-3 live L2 slots."""
from __future__ import annotations

from typing import Any

from bot.autonomy import assert_not_dark
from bot.persist import load_session, save_session
from constants import IBKR_MAX_DEPTH_SYMBOLS
from constants_bot import BOT_LEVEL_OFF


def _norm(symbol: str) -> str:
    return (symbol or "").strip().upper()


def snapshot() -> dict[str, Any]:
    row = load_session()
    focus = [_norm(s) for s in list(row.get("focus") or []) if _norm(s)]
    live = [_norm(s) for s in list(row.get("trader_live") or []) if _norm(s)]
    return {
        "focus": focus,
        "trader_live": live[: IBKR_MAX_DEPTH_SYMBOLS],
        "live_cap": IBKR_MAX_DEPTH_SYMBOLS,
        "level": int(row.get("level") or BOT_LEVEL_OFF),
    }


def set_focus(symbols: list[str]) -> dict[str, Any]:
    assert_not_dark()
    row = load_session()
    cleaned: list[str] = []
    for raw in symbols:
        sym = _norm(raw)
        if sym and sym not in cleaned:
            cleaned.append(sym)
    row["focus"] = cleaned
    save_session(row)
    return snapshot()


def add_focus(symbol: str) -> dict[str, Any]:
    assert_not_dark()
    row = load_session()
    focus = [_norm(s) for s in list(row.get("focus") or []) if _norm(s)]
    sym = _norm(symbol)
    if not sym:
        return snapshot()
    if sym not in focus:
        focus.append(sym)
    row["focus"] = focus
    save_session(row)
    return snapshot()


def sync_trader_live(symbols: list[str]) -> dict[str, Any]:
    """UI reports the actual live L2 tabs so Eyes stay honest."""
    row = load_session()
    cleaned: list[str] = []
    for raw in symbols:
        sym = _norm(raw)
        if sym and sym not in cleaned:
            cleaned.append(sym)
    row["trader_live"] = cleaned[: IBKR_MAX_DEPTH_SYMBOLS]
    save_session(row)
    return snapshot()
