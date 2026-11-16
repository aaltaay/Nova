"""Bot focus shares the Trader max-3 live L2 slots: what ``/ws/bot/eyes`` streams.

ADR 072 retired ``POST /api/bot/focus/sync`` and the focus writes with the Bots page: the snapshot reads what the
session file holds.
"""
from __future__ import annotations

from typing import Any

from bot.persist import load_session
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
