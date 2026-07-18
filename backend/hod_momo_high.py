"""HOD session-high truth — seed from bars / IBKR tick-6, never invent from last.

Cold-start bug: ``session_highs[sym]`` started at 0 and first last-price became
"HOD". This module seeds from historical bar highs and L1 day High (tick 6),
marks ``session_high_seeded``, and only then allows HOD strategies to pass.
"""
from __future__ import annotations

from typing import Any

import hod_momo_state as _state


def bars_session_high(bars: list[dict] | None) -> float | None:
    """Max bar high from OHLCV dicts (keys ``h``)."""
    best = 0.0
    for bar in bars or []:
        try:
            high = float(bar["h"])
        except (KeyError, TypeError, ValueError):
            continue
        if high > best:
            best = high
    return best if best > 0 else None


def _merge_source(prev: str | None, addition: str) -> str:
    if not prev:
        return addition
    parts = set(prev.split("+"))
    parts.add(addition)
    order = ["bars", "tick6", "observed"]
    return "+".join(p for p in order if p in parts)


def apply_session_high(
    symbol: str,
    high: float,
    *,
    source: str,
) -> float | None:
    """Raise session high from a trusted source; mark seeded.

    Never lowers an existing high. Returns the new session high or None.
    """
    sym = (symbol or "").strip().upper()
    if not sym:
        return None
    try:
        h = float(high)
    except (TypeError, ValueError):
        return None
    if h <= 0:
        return None
    state = _state.get_state()
    prev = float(state.session_highs.get(sym, 0.0) or 0.0)
    if h > prev:
        state.session_highs[sym] = h
        prev = h
    state.session_high_seeded.add(sym)
    state.session_high_source[sym] = _merge_source(
        state.session_high_source.get(sym), source,
    )
    return prev


def apply_day_high(symbol: str, day_high: float | None) -> float | None:
    """Apply IBKR L1 tick-6 day High as a floor for session highs."""
    sym = (symbol or "").strip().upper()
    if not sym or day_high is None:
        return None
    try:
        h = float(day_high)
    except (TypeError, ValueError):
        return None
    if h <= 0:
        return None
    state = _state.get_state()
    state.day_highs[sym] = h
    return apply_session_high(sym, h, source="tick6")


def seed_session_high_from_bars(symbol: str, bars: list[dict] | None) -> float | None:
    """Seed session high from max(bar.h); marks seeded when bars have highs."""
    high = bars_session_high(bars)
    if high is None:
        return None
    return apply_session_high(symbol, high, source="bars")


def is_high_seeded(symbol: str) -> bool:
    sym = (symbol or "").strip().upper()
    return bool(sym) and sym in _state.get_state().session_high_seeded


def raise_observed_high(symbol: str, price: float) -> None:
    """After seeded, allow last prints to raise the tracked high (true new HOD)."""
    sym = (symbol or "").strip().upper()
    if not sym or not is_high_seeded(sym):
        return
    try:
        px = float(price)
    except (TypeError, ValueError):
        return
    if px <= 0:
        return
    state = _state.get_state()
    prev = float(state.session_highs.get(sym, 0.0) or 0.0)
    if px > prev:
        state.session_highs[sym] = px
        state.session_high_source[sym] = _merge_source(
            state.session_high_source.get(sym), "observed",
        )


def high_debug(symbol: str) -> dict[str, Any]:
    sym = (symbol or "").strip().upper()
    state = _state.get_state()
    return {
        "session_high": state.session_highs.get(sym),
        "day_high": state.day_highs.get(sym),
        "high_seeded": sym in state.session_high_seeded,
        "session_high_source": state.session_high_source.get(sym),
    }
