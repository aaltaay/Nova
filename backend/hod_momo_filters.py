"""
HOD Momo alert-strategy filter/gate evaluation — pure functions, no module state.

Split out of hod_momo.py (backend-modularity rule). Every function here
receives all the data it needs as arguments (strategy config, ticker
snapshot, master gate settings, price history) and returns a decision;
none of them read or mutate module-level globals. The stateful
orchestration — reading the live caches, calling these with the right
values, and recording results — stays in hod_momo.py (on_trade_update /
_would_fire_now), which is where the tests exercise it end-to-end.

Kept deliberately dependency-free of hod_momo.py itself to avoid a
circular import (hod_momo.py imports these functions).
"""

from __future__ import annotations

from collections import deque
from typing import Callable

from hod_momo_models import MasterGateConfig, StrategyConfig, TickerSnap


def passes_range(value: float | None, min_val: float, max_val: float) -> tuple[bool, str]:
    """Generic min/max check. 0 = disabled.
    Returns (True, '') on pass, (False, '<detail>') on fail.
    """
    if value is None:
        if min_val == 0 and max_val == 0:
            return True, ""
        return False, f"value_unknown(min={min_val},max={max_val})"
    if min_val > 0 and value < min_val:
        return False, f"below_min({value:.4g}<{min_val})"
    if max_val > 0 and value > max_val:
        return False, f"above_max({value:.4g}>{max_val})"
    return True, ""


def price_surge(
    buffer: "deque[tuple[float, float]] | None",
    window_min: int,
    method: str,
) -> float | None:
    """Compute the surge % over the last `window_min` minutes of a price buffer.

    low_to_current: (current - min_in_window) / min_in_window * 100
    fixed_start:    (current - price_at_window_start) / price_at_window_start * 100

    Returns None if there is insufficient data.
    """
    buf = buffer
    if not buf:
        return None
    now_ts = buf[-1][0]
    current_price = buf[-1][1]
    cutoff = now_ts - window_min * 60
    window_prices = [p for t, p in buf if t >= cutoff]
    if len(window_prices) < 2:
        return None
    if method == "fixed_start":
        start_price = window_prices[0]
    else:
        start_price = min(window_prices)
    if start_price <= 0:
        return None
    return (current_price - start_price) / start_price * 100.0


def evaluate_strategy(
    cfg: StrategyConfig,
    snap: TickerSnap,
    surge_pct: float | None,
    request_fundamentals: Callable[[], None],
) -> tuple[bool, str]:
    """Returns (passed, blocked_by_reason). blocked_by_reason is '' on pass.

    ``request_fundamentals`` is called (no args) when float/52wk data is
    missing and needs to be queued for enrichment — the caller decides
    which symbol that maps to.
    """
    if not cfg.enabled:
        return False, "disabled"

    ok, reason = passes_range(snap.price, cfg.min_price, cfg.max_price)
    if not ok:
        return False, f"price:{reason}"

    float_val = snap.float_shares
    if cfg.min_float > 0 or cfg.max_float > 0:
        if float_val is None:
            request_fundamentals()
            return False, "float:unknown"
        if cfg.min_float > 0 and float_val < cfg.min_float:
            return False, f"float:below_min({float_val:.3g}<{cfg.min_float:.3g})"
        if cfg.max_float > 0 and float_val > cfg.max_float:
            return False, f"float:above_max({float_val:.3g}>{cfg.max_float:.3g})"

    if cfg.min_volume > 0 and (snap.volume is None or snap.volume < cfg.min_volume):
        return False, f"volume:below_min({snap.volume}<{cfg.min_volume})"

    ok, reason = passes_range(snap.rvol, cfg.min_rvol, cfg.max_rvol)
    if not ok:
        return False, f"rvol:{reason}"

    ok, reason = passes_range(snap.gap_pct, cfg.min_gap_pct, cfg.max_gap_pct)
    if not ok:
        return False, f"gap_pct:{reason}"

    ok, reason = passes_range(snap.change_pct, cfg.min_change_pct, cfg.max_change_pct)
    if not ok:
        return False, f"change_pct:{reason}"

    if cfg.surge_pct > 0 and cfg.surge_window_min > 0:
        if surge_pct is None or surge_pct < cfg.surge_pct:
            return False, f"surge:{surge_pct} < {cfg.surge_pct}% in {cfg.surge_window_min}min"

    if cfg.proximity_52wk_pct > 0:
        high52 = snap.fifty_two_week_high
        if high52 is None or high52 <= 0:
            request_fundamentals()
            return False, "52wk_high:unknown"
        proximity = ((high52 - snap.price) / high52) * 100.0
        if proximity > cfg.proximity_52wk_pct:
            return False, f"52wk_proximity:{proximity:.2f}%>{cfg.proximity_52wk_pct}%"

    return True, ""


def passes_master_gate(
    snap: TickerSnap,
    master: MasterGateConfig,
    eff_min_rvol: float,
    in_rvol_warmup_grace: bool,
    surge_buffer: "deque[tuple[float, float]] | None",
) -> tuple[bool, str]:
    """Global pre-check: data-ready + optional master surge.

    Master RVOL was retired (2026-07-17) — per-strategy ``min_rvol`` is the
    RVOL gate. ``eff_min_rvol`` / ``in_rvol_warmup_grace`` kept for call-site
    compatibility; unused.

    HOD is per-strategy via ``fails_hod_gate`` (Running Up can skip HOD).
    """
    del eff_min_rvol, in_rvol_warmup_grace  # master RVOL retired
    if snap.price is None or float(snap.price or 0) <= 0:
        return False, "master_data:no_price"

    if master.surge_pct > 0 and master.surge_window_min > 0:
        surge = price_surge(surge_buffer, master.surge_window_min, "low_to_current")
        if surge is None:
            return False, f"master_surge:insufficient_data(window={master.surge_window_min}min)"
        if surge < master.surge_pct:
            return False, f"master_surge({surge:.2f}%<{master.surge_pct}%)"

    return True, ""


def is_master_rvol_soft_block(gate_ok: bool, gate_reason: str) -> bool:
    """Retired — always False. Kept so older callers/tests import cleanly."""
    del gate_ok, gate_reason
    return False


def strategy_ignores_master_rvol(cfg: StrategyConfig) -> bool:
    """Retired with master RVOL — always False."""
    del cfg
    return False


def fails_hod_gate(
    price: float,
    session_high: float,
    cfg: StrategyConfig,
    master_hod_required: bool,
    *,
    high_seeded: bool = True,
    epsilon_abs: float = 0.01,
    epsilon_pct: float = 0.001,
    new_hod_age_sec: float | None = None,
    new_hod_grace_sec: float = 60.0,
) -> str | None:
    """Return a block reason if this strategy requires a fresh new HOD.

    Unseeded highs always block (kills cold-start invent-from-first-tick).
    Being merely *at* a seeded high is not enough — Warrior HOD Momentum needs
    a new high-of-day (Running Up covers pullback squeezes without new HOD).
    ``new_hod_age_sec`` is seconds since the session high last rose via an
    observed print or post-seed tick-6; must be within ``new_hod_grace_sec``.
    """
    if not (cfg.requires_hod and master_hod_required):
        return None
    if not high_seeded or session_high <= 0:
        return "hod:high_unseeded"
    try:
        px = float(price)
        hod = float(session_high)
    except (TypeError, ValueError):
        return "hod:high_unseeded"
    eps = max(float(epsilon_abs), float(hod) * float(epsilon_pct))
    if px + eps < hod:
        return f"hod(price={px:.4g}<hod={hod:.4g})"
    grace = float(new_hod_grace_sec or 0.0)
    if grace > 0:
        if new_hod_age_sec is None:
            return "hod:not_new"
        if float(new_hod_age_sec) > grace:
            return f"hod:stale_new({float(new_hod_age_sec):.0f}s>{grace:.0f}s)"
    return None
