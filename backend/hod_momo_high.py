"""HOD session-high truth — seed from bars / IBKR tick-6, never invent from last.

Cold-start bug: ``session_highs[sym]`` started at 0 and first last-price became
"HOD". This module seeds from historical bar highs and L1 day High (tick 6),
marks ``session_high_seeded``, and only then allows HOD strategies to pass.

Warrior parity (BA101 / KB): requires_hod strategies need a *new* high-of-day,
not a retest of an already-seeded high (Running Up covers that). Initial bar /
tick-6 seed sets the floor without opening the alert grace window; only an
observed last (or a later tick-6 raise above that floor) opens it.
"""
from __future__ import annotations

import logging
import time
from typing import Any

import hod_momo_state as _state

logger = logging.getLogger(__name__)


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
    open_alert_window: bool | None = None,
    now_ts: float | None = None,
) -> float | None:
    """Raise session high from a trusted source; mark seeded.

    Never lowers an existing high. Returns the new session high or None.

    ``open_alert_window``:
      - None (default): open only when high rises above a prior floor via
        ``observed`` or ``tick6`` (not the first bars/tick6 seed from 0).
      - True/False: force.
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
    raised = False
    if h > prev:
        state.session_highs[sym] = h
        raised = True
        if open_alert_window is None:
            # First seed establishes the floor only — not a live HOD break.
            open_alert_window = prev > 0 and source in ("observed", "tick6")
        if open_alert_window:
            state.session_high_raised_ts[sym] = (
                float(now_ts) if now_ts is not None else time.time()
            )
        prev = h
    state.session_high_seeded.add(sym)
    state.session_high_source[sym] = _merge_source(
        state.session_high_source.get(sym), source,
    )
    _persist_highs()
    return prev


def _persist_highs() -> None:
    """Throttled disk persist so a restart doesn't re-blind an already-seeded
    symbol (see PROBLEM_LOG 2026-07-23 — session highs were in-memory only)."""
    try:
        import hod_momo_persist as _persist

        _persist.save_highs()
    except Exception:
        logger.debug("HOD Momo: session-high persist skipped", exc_info=True)


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


def raise_observed_high(symbol: str, price: float, *, now_ts: float | None = None) -> bool:
    """After seeded, allow last prints to raise the tracked high (true new HOD).

    Returns True when this print raised the session high (opens alert grace).
    """
    sym = (symbol or "").strip().upper()
    if not sym or not is_high_seeded(sym):
        return False
    try:
        px = float(price)
    except (TypeError, ValueError):
        return False
    if px <= 0:
        return False
    state = _state.get_state()
    prev = float(state.session_highs.get(sym, 0.0) or 0.0)
    if px <= prev:
        return False
    apply_session_high(
        sym, px, source="observed", open_alert_window=True, now_ts=now_ts,
    )
    return True


def last_new_hod_age_sec(symbol: str, *, now_ts: float | None = None) -> float | None:
    """Seconds since session high last rose via observed/tick6 (None if never)."""
    sym = (symbol or "").strip().upper()
    if not sym:
        return None
    raised = _state.get_state().session_high_raised_ts.get(sym)
    if raised is None:
        return None
    now = float(now_ts) if now_ts is not None else time.time()
    return max(0.0, now - float(raised))


def high_debug(symbol: str) -> dict[str, Any]:
    sym = (symbol or "").strip().upper()
    state = _state.get_state()
    return {
        "session_high": state.session_highs.get(sym),
        "day_high": state.day_highs.get(sym),
        "high_seeded": sym in state.session_high_seeded,
        "session_high_source": state.session_high_source.get(sym),
        "session_high_raised_ts": state.session_high_raised_ts.get(sym),
        "new_hod_age_sec": last_new_hod_age_sec(sym),
    }
