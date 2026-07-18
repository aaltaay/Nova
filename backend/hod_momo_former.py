"""Former Momo list — Warrior-style remember + gate helpers.

Warrior's "Former Momo Stock" tags names that already hit HOD Momentum.
Nova keeps an explicit ``former_momo_list`` on strategy 1. When any *other*
strategy fires, we remember the ticker so Former Momo can fire on later HODs
without scraping Warrior into the engine.
"""
from __future__ import annotations

import logging

import hod_momo_persist as _persist
import hod_momo_state as _state
from constants import HOD_MOMO_FORMER_MOMO_STRATEGY_ID
from hod_momo_models import StrategyConfig

logger = logging.getLogger(__name__)


def former_momo_block_reason(
    strategy_id: int,
    symbol: str,
    config: StrategyConfig,
) -> str | None:
    """Return a block reason when Former Momo list rules reject this eval."""
    sym = (symbol or "").strip().upper()
    if not sym:
        return "former_momo:empty_symbol"

    if strategy_id == HOD_MOMO_FORMER_MOMO_STRATEGY_ID:
        if not config.former_momo_list:
            return "former_momo_list_empty"
        allowed = {item.upper() for item in config.former_momo_list}
        if sym not in allowed:
            return "not_in_former_momo_list"
        return None

    # Optional per-strategy whitelist (defaults empty = no filter).
    if config.former_momo_list:
        allowed = {item.upper() for item in config.former_momo_list}
        if sym not in allowed:
            return "not_in_former_momo_list"
    return None


def remember_former_momo(symbol: str, *, persist: bool = True) -> bool:
    """Add symbol to strategy-1 Former Momo list. Returns True if changed."""
    sym = (symbol or "").strip().upper()
    if not sym:
        return False
    state = _state.get_state()
    cfg = state.configs.get(HOD_MOMO_FORMER_MOMO_STRATEGY_ID)
    if cfg is None:
        return False
    current = [s.upper() for s in cfg.former_momo_list]
    if sym in current:
        return False
    cfg.former_momo_list = [*current, sym]
    if persist:
        _persist.save_configs()
        logger.info(
            "HOD Momo: remembered Former Momo symbol %s (list=%d)",
            sym,
            len(cfg.former_momo_list),
        )
    return True


def bootstrap_former_momo_from_alerts() -> int:
    """Seed Former Momo list from today's non-Former alerts (session heal)."""
    state = _state.get_state()
    added = 0
    for alert in state.today_alerts:
        if int(getattr(alert, "strategy_id", 0) or 0) == HOD_MOMO_FORMER_MOMO_STRATEGY_ID:
            continue
        ticker = getattr(alert, "ticker", None) or getattr(alert, "symbol", None)
        if remember_former_momo(str(ticker or ""), persist=False):
            added += 1
    if added:
        _persist.save_configs()
        logger.info("HOD Momo: bootstrapped %d Former Momo symbol(s) from today alerts", added)
    return added


def session_focus_extra_symbols() -> list[str]:
    """Compat: alerts + sticky evals + Former list → focus universe."""
    import hod_momo_session_focus as _focus

    return _focus.session_focus_extra_symbols()


def session_focus_active_priority() -> list[str]:
    """Compat: alerts → sticky → Former (last) for reserved L1 slots."""
    import hod_momo_session_focus as _focus

    return _focus.session_focus_active_priority()
