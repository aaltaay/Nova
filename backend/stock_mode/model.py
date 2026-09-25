"""The stock-mode rules (ADR 037), pure: the four modes, the locks, the size, the approval's binding."""
from __future__ import annotations

import math
from typing import Any

from constants_sim import DESK_PRACTICE_VENUES
from constants_stock_mode import (
    STOCK_MODE_APPROVE,
    STOCK_MODE_AUTO_ENTRY,
    STOCK_MODE_BOT,
    STOCK_MODE_INVALID,
    STOCK_MODE_PRICE_TOLERANCE,
    STOCK_MODE_RISK,
    STOCK_MODE_RISK_MAX_USD,
    STOCK_MODE_RISK_MIN_USD,
    STOCK_MODE_SIDE_NOVA,
    STOCK_MODE_SIDES,
    STOCK_MODE_SIGNAL,
    STOCK_MODE_SYMBOL_MAX_LEN,
    STOCK_MODE_WHY_LIVE_BUY,
    STOCK_MODE_WHY_LIVE_SELL,
    STOCK_MODE_WHY_REPLAY,
    STOCK_MODE_WHY_VENUE_UNKNOWN,
)
from stock_mode.errors import StockModeError

EPS = 1e-9


def mode_of(buy: str, sell: str) -> str:
    """You / you is Signal only; you / Nova Approve; Nova / you Auto-entry; Nova / Nova the bot."""
    if buy == STOCK_MODE_SIDE_NOVA:
        return STOCK_MODE_BOT if sell == STOCK_MODE_SIDE_NOVA else STOCK_MODE_AUTO_ENTRY
    return STOCK_MODE_APPROVE if sell == STOCK_MODE_SIDE_NOVA else STOCK_MODE_SIGNAL


def symbol(raw: str | None) -> str:
    sym = (raw or "").strip().upper()
    if not sym or len(sym) > STOCK_MODE_SYMBOL_MAX_LEN:
        raise StockModeError(STOCK_MODE_INVALID, f"a symbol, up to {STOCK_MODE_SYMBOL_MAX_LEN} characters",
                             status=400, field="symbol")
    return sym


def side(raw: Any, field: str) -> str:
    value = str(raw or "").strip().lower()
    if value not in STOCK_MODE_SIDES:
        raise StockModeError(STOCK_MODE_INVALID, f"{field} is 'you' or 'nova'", status=400, field=field)
    return value


def risk_usd(raw: Any, *, required: bool) -> float | None:
    """The desk's risk per trade: required where Nova sizes a buy by itself (Auto-entry)."""
    if raw is None:
        if required:
            raise StockModeError(STOCK_MODE_RISK, "Auto-entry needs your risk per trade to size the buy",
                                 status=400, field="risk_usd")
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        raise StockModeError(STOCK_MODE_RISK, "risk_usd is a dollar amount", status=400, field="risk_usd") from None
    if not math.isfinite(value) or not STOCK_MODE_RISK_MIN_USD <= value <= STOCK_MODE_RISK_MAX_USD:
        raise StockModeError(
            STOCK_MODE_RISK,
            f"risk per trade is ${STOCK_MODE_RISK_MIN_USD:g} to ${STOCK_MODE_RISK_MAX_USD:,.0f}",
            status=400, field="risk_usd")
    return value


def locks(venue: str | None, replay: bool) -> dict[str, str | None]:
    """Why Nova cannot take each side now (None: it can). A venue Nova cannot read counts as Live."""
    if venue is None:
        return {"buy": STOCK_MODE_WHY_VENUE_UNKNOWN, "sell": STOCK_MODE_WHY_VENUE_UNKNOWN}
    if venue not in DESK_PRACTICE_VENUES:
        return {"buy": STOCK_MODE_WHY_LIVE_BUY, "sell": STOCK_MODE_WHY_LIVE_SELL}
    if replay:
        return {"buy": STOCK_MODE_WHY_REPLAY, "sell": STOCK_MODE_WHY_REPLAY}
    return {"buy": None, "sell": None}


def size(risk: float | None, entry: Any, stop: Any) -> int:
    """Whole shares of the risk per trade over the risk per share; 0 when either is unknown."""
    try:
        per_share = float(entry) - float(stop)
    except (TypeError, ValueError):
        return 0
    if risk is None or per_share <= EPS or not math.isfinite(per_share):
        return 0
    return max(0, int(math.floor(float(risk) / per_share + EPS)))


def same_price(a: Any, b: Any, tolerance: float = STOCK_MODE_PRICE_TOLERANCE) -> bool:
    try:
        return abs(float(a) - float(b)) <= tolerance + EPS
    except (TypeError, ValueError):
        return False


def plan_matches(approved: dict[str, Any], levels: dict[str, Any] | None) -> bool:
    """An approval binds to the lane's own entry, stop and target (within a cent)."""
    if not levels:
        return False
    return (same_price(approved.get("entry"), levels.get("entry"))
            and same_price(approved.get("stop"), levels.get("stop"))
            and same_price(approved.get("target"), levels.get("target1")))


def levels_text(levels: dict[str, Any]) -> str:
    def fmt(v: Any) -> str:
        try:
            return f"{float(v):.2f}"
        except (TypeError, ValueError):
            return "?"

    return f"{fmt(levels.get('entry'))} / {fmt(levels.get('stop'))} / {fmt(levels.get('target1', levels.get('target')))}"
