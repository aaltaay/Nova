"""HOD Momo active-set fair-batch selection and SLO coverage/age metrics.

Extracted from ``hod_momo_active.py`` along the batching/telemetry seam (ADR 004).
"""
from __future__ import annotations

import time
from typing import Any, Iterable

from constants import (
    HOD_MOMO_ACTIVE_HOT_PER_TICK,
    HOD_MOMO_ACTIVE_SET_CAPACITY,
    HOD_MOMO_INTEGRITY_ACTIVE_EVAL_MAX_SEC,
    HOD_MOMO_INTEGRITY_ACTIVE_QUOTE_MAX_SEC,
    IBKR_TABLE_REPRICE_CHUNK_SIZE,
)

_tail_rotate = 0


def reset_tail_rotate() -> None:
    """Reset the fair-batch rotation counter on session rollover."""
    global _tail_rotate
    _tail_rotate = 0


def select_fair_batch_from(
    symbols: list[str],
    last_quote_ts: dict[str, float],
    *,
    hot: Iterable[str] | None = None,
    chunk_size: int = IBKR_TABLE_REPRICE_CHUNK_SIZE,
    hot_n: int = HOD_MOMO_ACTIVE_HOT_PER_TICK,
    now: float | None = None,
) -> list[str]:
    """Hot priority every tick + rotating/age-fair tail under chunk budget."""
    global _tail_rotate
    ordered = [s for s in symbols if s]
    if not ordered:
        return []
    size = max(1, int(chunk_size))
    hot_set = {(s or "").strip().upper() for s in (hot or []) if s}
    # Always treat top-of-list (open ticker / highest priority) as hot.
    hot_cap = max(1, min(int(hot_n), size))
    preferred_hot = [s for s in ordered if s in hot_set][:hot_cap]
    if len(preferred_hot) < hot_cap:
        for s in ordered:
            if s not in preferred_hot:
                preferred_hot.append(s)
            if len(preferred_hot) >= hot_cap:
                break

    remaining_slots = size - len(preferred_hot)
    if remaining_slots <= 0:
        return preferred_hot[:size]

    ts_now = float(now if now is not None else time.time())
    tail_pool = [s for s in ordered if s not in preferred_hot]
    if not tail_pool:
        return preferred_hot

    # Prefer symbols with oldest (or missing) quotes; rotate for fairness when tied.
    def age_key(sym: str) -> tuple[float, int]:
        q = last_quote_ts.get(sym)
        age = ts_now - q if q else 1e9
        return (-age, ordered.index(sym) if sym in ordered else 0)

    stale_first = sorted(tail_pool, key=age_key)
    # Rotate so a permanently-stale symbol cannot starve the rest forever.
    if stale_first:
        start = _tail_rotate % len(stale_first)
        rotated = stale_first[start:] + stale_first[:start]
        _tail_rotate += 1
    else:
        rotated = []
    return preferred_hot + rotated[:remaining_slots]


def merge_with_scanner_chunk(
    active_batch: list[str],
    scanner_chunk: list[str],
    *,
    chunk_size: int = IBKR_TABLE_REPRICE_CHUNK_SIZE,
) -> list[str]:
    """Prefer active-set freshness; fill leftover slots with scanner UI symbols."""
    out: list[str] = []
    seen: set[str] = set()
    size = max(1, int(chunk_size))
    for sym in list(active_batch) + list(scanner_chunk):
        s = (sym or "").strip().upper()
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
        if len(out) >= size:
            break
    return out


def _percentile(sorted_vals: list[float], p: float) -> float | None:
    if not sorted_vals:
        return None
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    idx = int(round((p / 100.0) * (len(sorted_vals) - 1)))
    idx = max(0, min(len(sorted_vals) - 1, idx))
    return sorted_vals[idx]


def age_stats(
    timestamps: dict[str, float],
    symbols: list[str],
    now: float | None = None,
) -> dict[str, Any]:
    ts_now = float(now if now is not None else time.time())
    ages = []
    missing = []
    for sym in symbols:
        t = timestamps.get(sym)
        if t is None:
            missing.append(sym)
            continue
        ages.append(max(0.0, ts_now - float(t)))
    ages_sorted = sorted(ages)
    return {
        "count": len(symbols),
        "sampled": len(ages_sorted),
        "missing": missing,
        "p50": _percentile(ages_sorted, 50),
        "p95": _percentile(ages_sorted, 95),
        "max": max(ages_sorted) if ages_sorted else None,
    }


def coverage_pct_from(
    symbols: list[str],
    last_quote_ts: dict[str, float],
    last_eval_ts: dict[str, float],
    now: float | None = None,
) -> float:
    """Percent of symbols with recent quote AND evaluation within max SLO."""
    if not symbols:
        return 100.0
    ts_now = float(now if now is not None else time.time())
    ok = 0
    for sym in symbols:
        q = last_quote_ts.get(sym)
        e = last_eval_ts.get(sym)
        if q is None or e is None:
            continue
        if (ts_now - q) <= HOD_MOMO_INTEGRITY_ACTIVE_QUOTE_MAX_SEC and (
            ts_now - e
        ) <= HOD_MOMO_INTEGRITY_ACTIVE_EVAL_MAX_SEC:
            ok += 1
    return 100.0 * ok / len(symbols)


def build_metrics_snapshot(
    active: list[str],
    uncovered: list[str],
    priority_reason: dict[str, str],
    last_quote_ts: dict[str, float],
    last_eval_ts: dict[str, float],
    universe_entry_count: int,
) -> dict[str, Any]:
    q = age_stats(last_quote_ts, active)
    e = age_stats(last_eval_ts, active)
    return {
        "active_set_size": len(active),
        "active_set_capacity": HOD_MOMO_ACTIVE_SET_CAPACITY,
        "uncovered_count": len(uncovered),
        "uncovered_symbols": uncovered[:40],
        "active_symbols": active,
        "priority_reasons": {s: priority_reason.get(s, "") for s in active[:40]},
        "active_coverage_pct": coverage_pct_from(active, last_quote_ts, last_eval_ts),
        "active_quote_age_p50": q["p50"],
        "active_quote_age_p95": q["p95"],
        "active_quote_age_max": q["max"],
        "active_quote_missing": q["missing"][:20],
        "active_eval_age_p50": e["p50"],
        "active_eval_age_p95": e["p95"],
        "active_eval_age_max": e["max"],
        "active_eval_missing": e["missing"][:20],
        "universe_entry_count": universe_entry_count,
    }
