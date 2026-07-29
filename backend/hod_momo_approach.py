"""Approaching HOD latch — re-touch of a stale session high after a pullback.

Strategy 13 fires once when price returns to within the HOD epsilon of a
*seeded* session high that is no longer in the new-HOD grace window, and only
after the symbol has dipped ``HOD_MOMO_REAPPROACH_RESET_PCT`` below that high.
The latch stays cleared while price hovers at the high (no spam).
"""
from __future__ import annotations

from constants import (
    HOD_MOMO_HOD_EPSILON_ABS,
    HOD_MOMO_HOD_EPSILON_PCT,
    HOD_MOMO_NEW_HOD_GRACE_SEC,
    HOD_MOMO_REAPPROACH_RESET_PCT,
)
import hod_momo_state as _state


def reset_threshold(session_high: float, reset_pct: float | None = None) -> float:
    """Price at/below which the approach latch re-arms."""
    pct = float(HOD_MOMO_REAPPROACH_RESET_PCT if reset_pct is None else reset_pct)
    return float(session_high) * (1.0 - pct)


def update_latch(
    symbol: str,
    price: float,
    session_high: float,
    *,
    high_seeded: bool,
    reset_pct: float | None = None,
) -> None:
    """Arm the approach latch when price dips far enough below the session high."""
    sym = (symbol or "").upper()
    if not sym or not high_seeded or session_high <= 0:
        return
    try:
        px = float(price)
        hod = float(session_high)
    except (TypeError, ValueError):
        return
    if px <= reset_threshold(hod, reset_pct):
        _state.get_state().approach_armed[sym] = True


def is_armed(symbol: str) -> bool:
    sym = (symbol or "").upper()
    if not sym:
        return False
    return bool(_state.get_state().approach_armed.get(sym, False))


def mark_fired(symbol: str) -> None:
    sym = (symbol or "").upper()
    if not sym:
        return
    _state.get_state().approach_armed[sym] = False


def approach_block_reason(
    price: float,
    session_high: float,
    *,
    high_seeded: bool,
    armed: bool,
    new_hod_age_sec: float | None,
    epsilon_abs: float = HOD_MOMO_HOD_EPSILON_ABS,
    epsilon_pct: float = HOD_MOMO_HOD_EPSILON_PCT,
    new_hod_grace_sec: float = HOD_MOMO_NEW_HOD_GRACE_SEC,
) -> str | None:
    """Return a block reason, or None when an Approaching HOD alert should fire.

    Does not fire during a fresh new-HOD grace window (that belongs to
    strategy 10/11 breakouts). Does not fire when unseeded or not armed.
    """
    if not high_seeded or session_high <= 0:
        return "approach:high_unseeded"
    try:
        px = float(price)
        hod = float(session_high)
    except (TypeError, ValueError):
        return "approach:high_unseeded"
    grace = float(new_hod_grace_sec or 0.0)
    if grace > 0 and new_hod_age_sec is not None and float(new_hod_age_sec) <= grace:
        return "approach:fresh_new_hod"
    eps = max(float(epsilon_abs), float(hod) * float(epsilon_pct))
    if px + eps < hod:
        return f"approach:below_hod(price={px:.4g}<hod={hod:.4g})"
    if not armed:
        return "approach:not_armed"
    return None
