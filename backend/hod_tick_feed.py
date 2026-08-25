"""Feed one L1 tick into HOD Momo's active-set trade-update path.

Extracted from ``ibkr_bridge.apply_l1_quote`` (see ``.cursor/rules/
file-size-limits.mdc``) -- this tail has no scanner-table-cache side effects
of its own, so it is a clean, low-risk boundary to isolate from the
table-reprice blocks it used to sit beside, and it freed the headroom
``ibkr_bridge.py`` needed for the Large Cap branch (ADR 014).
"""
from __future__ import annotations

import logging

import hod_momo as _hod_momo
import hod_momo_active as _hod_active

logger = logging.getLogger(__name__)


def feed_hod_on_tick(sym: str, price: float, volume: int | None, now: float) -> None:
    """Route one L1 tick to HOD Momo if *sym* is in the current active set."""
    active = set(_hod_active.get_active_symbols())
    if not active:
        # Lazy import -- ibkr_bridge imports this module, so importing it back
        # at module load time would be circular. Bootstrap-only path (first
        # tick before any active-set has been built yet).
        import ibkr_bridge as _bridge

        active = {sym}
        _bridge.refresh_hod_active_set()
        active = set(_hod_active.get_active_symbols()) or {sym}
    if sym not in active:
        return
    try:
        from ibkr import ticks as _ticks
        from ibkr_bridge import _archive_l1_tick

        day_high = _ticks.get_day_high(sym)
        _hod_active.note_quote(sym, now)
        _hod_momo.on_trade_update(
            sym,
            float(price),
            now,
            volume=int(volume) if volume is not None else None,
            day_high=day_high,
        )
        _archive_l1_tick(
            sym,
            float(price),
            now,
            volume=float(volume) if volume is not None else None,
            day_high=day_high,
        )
    except Exception:
        logger.exception("HOD Momo: IBKR L1 tick failed for %s", sym)
