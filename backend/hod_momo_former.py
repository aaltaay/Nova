"""Former Momo list — manual-only watchlist + gate helpers (REQ-HOD-005/006).

``former_momo_list`` on strategy 1 is a user-edited watchlist only (default
seed: SPRC) — never auto-mutated by alert firings or alert-history bootstrap.
Members get guaranteed HOD active-set admission (see
``former_momo_priority_symbols()``) regardless of Top Gainers rank, reusing
the same live-L1 pipeline every Top Gainer already flows through.
"""
from __future__ import annotations

import logging

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


def former_momo_priority_symbols() -> list[str]:
    """Manual Former Momo list only (REQ-HOD-006).

    Used both as HOD active-set ``priority_symbols`` (guaranteed live L1 +
    tracking regardless of Top Gainers rank) and as extra watch-universe
    symbols. No alert-history or sticky-memory input — manual list only.
    """
    state = _state.get_state()
    cfg = state.configs.get(HOD_MOMO_FORMER_MOMO_STRATEGY_ID)
    if cfg is None:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for raw in cfg.former_momo_list or []:
        sym = (raw or "").strip().upper()
        if sym and sym not in seen:
            seen.add(sym)
            out.append(sym)
    return out
