"""The stock-mode rules (ADR 037, ADR 042), pure: the four modes, the locks, the approval's binding.

A Nova automatic buy is sized by the venue's sleeve (``bot.sizing``), not here.
"""
from __future__ import annotations

from typing import Any

from constants_sim import DESK_PRACTICE_VENUES
from constants_stock_mode import (
    STOCK_MODE_APPROVE,
    STOCK_MODE_AUTO_ENTRY,
    STOCK_MODE_BOT,
    STOCK_MODE_INVALID,
    STOCK_MODE_PRICE_TOLERANCE,
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


def mode_of(buy: str | None, sell: str | None) -> str:
    """Entry · Exit (``buy`` / ``sell`` before shorts): You / you is Signal only; you / Nova Approve; Nova / you
    Auto-entry; Nova / Nova the bot."""
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


def locks(venue: str | None, replay: bool) -> dict[str, Any]:
    """Why Nova cannot take each side now (None: it can). A venue Nova cannot read counts as Live.
    ``entry`` / ``exit`` are the switch's names since shorts (ADR 048); ``buy`` / ``sell`` stay one release.
    ``modes`` says it per mode: on a Sim replay Bot is open and the modes that split the sides are not (ADR 052),
    so neither side is locked on its own there."""
    if venue is None:
        entry, exit_ = STOCK_MODE_WHY_VENUE_UNKNOWN, STOCK_MODE_WHY_VENUE_UNKNOWN
    elif venue not in DESK_PRACTICE_VENUES:
        entry, exit_ = STOCK_MODE_WHY_LIVE_BUY, STOCK_MODE_WHY_LIVE_SELL
    else:
        entry, exit_ = None, None
    if replay and venue in DESK_PRACTICE_VENUES:
        modes = {STOCK_MODE_BOT: None, STOCK_MODE_AUTO_ENTRY: STOCK_MODE_WHY_REPLAY,
                 STOCK_MODE_APPROVE: STOCK_MODE_WHY_REPLAY}
    else:
        modes = {STOCK_MODE_BOT: entry or exit_, STOCK_MODE_AUTO_ENTRY: entry, STOCK_MODE_APPROVE: exit_}
    return {"entry": entry, "exit": exit_, "buy": entry, "sell": exit_, "modes": modes}


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


def lane_side(lane: dict[str, Any]) -> str:
    """``"short"`` for a short setup's lane (ADR 049), else ``"long"``: its own ``side``, else its setup's."""
    from constants_bot import setup_side

    return str(lane.get("side") or setup_side(lane.get("setup_type")))


def lane_verdict(lane: dict[str, Any], spread: Any = None) -> dict[str, Any]:
    """NOT A TRADE on a scanner lane (``setup_scanner.trade_verdict``): grade, filter, the tape at its
    trigger, a played-out setup, the spread against its risk and a stock too thin to trade."""
    from setup_scanner.grade import pillar_count
    from setup_scanner.trade_verdict import verdict

    state = lane.get("state")
    phase = lane.get("phase") or state
    setup = lane.get("setup") or {}
    outcome = lane.get("outcome")
    played = None
    if outcome in ("target_first", "stop_first"):
        played = "target 1 printed first" if outcome == "target_first" else "the stop printed first"
    return verdict(grade=lane.get("grade"), pillars=pillar_count((lane.get("pillars") or {}).get("checks")),
                   filtered=(str(lane.get("reason") or "") or True) if state == "filtered" else None,
                   triggered=phase == "triggered", tape=lane.get("trigger_tape"), played_out=played,
                   spread=spread, risk=setup.get("risk"), liquidity=lane.get("liquidity"))


__all__ = ["STOCK_MODE_APPROVE", "STOCK_MODE_AUTO_ENTRY", "STOCK_MODE_BOT", "STOCK_MODE_SIGNAL", "lane_side",
           "lane_verdict", "levels_text", "locks", "mode_of", "plan_matches", "same_price", "side", "symbol"]
