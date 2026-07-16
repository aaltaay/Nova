"""Capacity-bounded HOD active evaluation set + fair reqTickersAsync scheduler.

Discovery watch set (scanners + seeds) may be large; only the active set is kept
within quote/evaluation SLOs. Uncovered discovery symbols are explicit.
Never opens reqMktData for the whole universe.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Iterable

from constants import (
    HOD_MOMO_ACTIVE_EXPLORE_SLOTS,
    HOD_MOMO_ACTIVE_HOT_PER_TICK,
    HOD_MOMO_ACTIVE_MOVER_SLOTS,
    HOD_MOMO_ACTIVE_SEED_SLOTS,
    HOD_MOMO_ACTIVE_SET_CAPACITY,
    HOD_MOMO_INTEGRITY_ACTIVE_EVAL_MAX_SEC,
    HOD_MOMO_INTEGRITY_ACTIVE_QUOTE_MAX_SEC,
    IBKR_TABLE_REPRICE_CHUNK_SIZE,
)

# Per-symbol live timestamps (unix seconds)
_last_quote_ts: dict[str, float] = {}
_last_eval_ts: dict[str, float] = {}
_universe_entry_ts: dict[str, float] = {}
_priority_reason: dict[str, str] = {}
_active_symbols: list[str] = []
_uncovered_symbols: list[str] = []
_tail_rotate = 0


@dataclass
class ActiveMember:
    symbol: str
    priority: int
    reason: str


@dataclass
class ActiveSetSnapshot:
    active: list[str]
    uncovered: list[str]
    reasons: dict[str, str] = field(default_factory=dict)
    capacity: int = HOD_MOMO_ACTIVE_SET_CAPACITY


def note_quote(symbol: str, ts: float | None = None) -> None:
    sym = (symbol or "").strip().upper()
    if sym:
        _last_quote_ts[sym] = float(ts if ts is not None else time.time())


def note_evaluation(symbol: str, ts: float | None = None) -> None:
    sym = (symbol or "").strip().upper()
    if sym:
        _last_eval_ts[sym] = float(ts if ts is not None else time.time())


def note_universe_entries(symbols: Iterable[str], ts: float | None = None) -> None:
    now = float(ts if ts is not None else time.time())
    for raw in symbols:
        sym = (raw or "").strip().upper()
        if sym and sym not in _universe_entry_ts:
            _universe_entry_ts[sym] = now


def clear_session_state() -> None:
    global _tail_rotate, _active_symbols, _uncovered_symbols
    _last_quote_ts.clear()
    _last_eval_ts.clear()
    _universe_entry_ts.clear()
    _priority_reason.clear()
    _active_symbols = []
    _uncovered_symbols = []
    _tail_rotate = 0


def _row_score(row: dict) -> float:
    for key in ("change_pct", "gap_percent", "change_abs"):
        val = row.get(key)
        if val is None:
            continue
        try:
            return abs(float(val))
        except (TypeError, ValueError):
            continue
    return 0.0


def _ordered_unique(symbols: Iterable[str]) -> list[str]:
    """Preserve first-seen rank order (do not alphabetically sort seeds)."""
    out: list[str] = []
    seen: set[str] = set()
    for raw in symbols:
        sym = (raw or "").strip().upper()
        if not sym or sym in seen:
            continue
        seen.add(sym)
        out.append(sym)
    return out


def build_active_set(
    *,
    discovery: Iterable[str],
    gainer_rows: Iterable[dict] | None = None,
    loser_rows: Iterable[dict] | None = None,
    gapper_rows: Iterable[dict] | None = None,
    afterhours_rows: Iterable[dict] | None = None,
    seed_symbols: Iterable[str] | None = None,
    detail_symbols: Iterable[str] | None = None,
    capacity: int = HOD_MOMO_ACTIVE_SET_CAPACITY,
    mover_slots: int = HOD_MOMO_ACTIVE_MOVER_SLOTS,
    seed_slots: int = HOD_MOMO_ACTIVE_SEED_SLOTS,
    explore_slots: int = HOD_MOMO_ACTIVE_EXPLORE_SLOTS,
) -> ActiveSetSnapshot:
    """Capacity-bounded active set with reserved quotas.

    Open tickers always win. Remaining slots are split so IBKR volume seeds
    (HOT_BY_VOLUME / TOP_VOLUME_RATE / MOST_ACTIVE) cannot be starved by a
    full gainer/gapper table. Uncovered discovery symbols stay explicit.
    """
    global _active_symbols, _uncovered_symbols, _tail_rotate

    cap = max(1, int(capacity))
    active: list[str] = []
    reasons: dict[str, str] = {}
    seen: set[str] = set()

    def _take(sym: str, reason: str) -> bool:
        s = (sym or "").strip().upper()
        if not s or s in seen or len(active) >= cap:
            return False
        seen.add(s)
        active.append(s)
        reasons[s] = reason
        return True

    for raw in detail_symbols or []:
        _take(raw, "open_ticker")

    mover_ranked: list[tuple[str, str, float]] = []
    for rows, reason in (
        (gainer_rows, "top_gainer"),
        (gapper_rows, "gapper"),
        (afterhours_rows, "afterhours"),
        (loser_rows, "top_loser"),
    ):
        for row in rows or []:
            sym = (row.get("symbol") or "").strip().upper()
            if sym:
                mover_ranked.append((sym, reason, _row_score(row)))
    mover_ranked.sort(key=lambda t: (-t[2], t[0]))

    seeds = _ordered_unique(seed_symbols or [])
    disco = _ordered_unique(discovery)

    # Quota budget after open tickers.
    remaining = cap - len(active)
    m_slots = max(0, min(int(mover_slots), remaining))
    s_slots = max(0, min(int(seed_slots), remaining - m_slots))
    e_slots = max(0, min(int(explore_slots), remaining - m_slots - s_slots))
    # Spill unused quota forward so capacity stays fully used.
    spill = remaining - m_slots - s_slots - e_slots

    taken_m = 0
    for sym, reason, _score in mover_ranked:
        if taken_m >= m_slots:
            break
        if _take(sym, reason):
            taken_m += 1
    spill += m_slots - taken_m

    taken_s = 0
    seed_budget = s_slots + spill
    for sym in seeds:
        if taken_s >= seed_budget:
            break
        if _take(sym, "volume_seed"):
            taken_s += 1
    spill = seed_budget - taken_s

    # Rotating exploration tail from discovery not already selected.
    explore_pool = [s for s in disco if s not in seen]
    taken_e = 0
    explore_budget = e_slots + spill
    if explore_pool and explore_budget > 0:
        start = _tail_rotate % len(explore_pool)
        rotated = explore_pool[start:] + explore_pool[:start]
        _tail_rotate += 1
        for sym in rotated:
            if taken_e >= explore_budget:
                break
            if _take(sym, "discovery"):
                taken_e += 1

    # Fill any leftover from remaining movers then seeds then discovery.
    if len(active) < cap:
        for sym, reason, _score in mover_ranked:
            if len(active) >= cap:
                break
            _take(sym, reason)
    if len(active) < cap:
        for sym in seeds:
            if len(active) >= cap:
                break
            _take(sym, "volume_seed")
    if len(active) < cap:
        for sym in disco:
            if len(active) >= cap:
                break
            _take(sym, "discovery")

    all_candidates = _ordered_unique(
        list(active)
        + [t[0] for t in mover_ranked]
        + seeds
        + disco
        + [(s or "").strip().upper() for s in (detail_symbols or []) if s],
    )
    uncovered = [s for s in all_candidates if s not in seen]

    _priority_reason.clear()
    _priority_reason.update(reasons)
    note_universe_entries(active + uncovered)

    _active_symbols = active
    _uncovered_symbols = uncovered
    return ActiveSetSnapshot(
        active=active,
        uncovered=uncovered,
        reasons=reasons,
        capacity=cap,
    )


def get_active_symbols() -> list[str]:
    return list(_active_symbols)


def get_uncovered_symbols() -> list[str]:
    return list(_uncovered_symbols)


def select_fair_batch(
    active: list[str] | None = None,
    *,
    hot: Iterable[str] | None = None,
    chunk_size: int = IBKR_TABLE_REPRICE_CHUNK_SIZE,
    hot_n: int = HOD_MOMO_ACTIVE_HOT_PER_TICK,
    now: float | None = None,
) -> list[str]:
    """Hot priority every tick + rotating/age-fair tail under chunk budget."""
    global _tail_rotate
    symbols = [s for s in (active if active is not None else _active_symbols) if s]
    if not symbols:
        return []
    size = max(1, int(chunk_size))
    hot_set = {(s or "").strip().upper() for s in (hot or []) if s}
    # Always treat top-of-list (open ticker / highest priority) as hot.
    hot_cap = max(1, min(int(hot_n), size))
    preferred_hot = [s for s in symbols if s in hot_set][:hot_cap]
    if len(preferred_hot) < hot_cap:
        for s in symbols:
            if s not in preferred_hot:
                preferred_hot.append(s)
            if len(preferred_hot) >= hot_cap:
                break

    remaining_slots = size - len(preferred_hot)
    if remaining_slots <= 0:
        return preferred_hot[:size]

    ts_now = float(now if now is not None else time.time())
    tail_pool = [s for s in symbols if s not in preferred_hot]
    if not tail_pool:
        return preferred_hot

    # Prefer symbols with oldest (or missing) quotes; rotate for fairness when tied.
    def age_key(sym: str) -> tuple[float, int]:
        q = _last_quote_ts.get(sym)
        age = ts_now - q if q else 1e9
        return (-age, symbols.index(sym) if sym in symbols else 0)

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


def age_stats(timestamps: dict[str, float], symbols: list[str], now: float | None = None) -> dict[str, Any]:
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


def coverage_pct(symbols: list[str], now: float | None = None) -> float:
    """Percent of symbols with recent quote AND evaluation within max SLO."""
    if not symbols:
        return 100.0
    ts_now = float(now if now is not None else time.time())
    ok = 0
    for sym in symbols:
        q = _last_quote_ts.get(sym)
        e = _last_eval_ts.get(sym)
        if q is None or e is None:
            continue
        if (ts_now - q) <= HOD_MOMO_INTEGRITY_ACTIVE_QUOTE_MAX_SEC and (
            ts_now - e
        ) <= HOD_MOMO_INTEGRITY_ACTIVE_EVAL_MAX_SEC:
            ok += 1
    return 100.0 * ok / len(symbols)


def metrics_snapshot() -> dict[str, Any]:
    active = list(_active_symbols)
    uncovered = list(_uncovered_symbols)
    q = age_stats(_last_quote_ts, active)
    e = age_stats(_last_eval_ts, active)
    return {
        "active_set_size": len(active),
        "active_set_capacity": HOD_MOMO_ACTIVE_SET_CAPACITY,
        "uncovered_count": len(uncovered),
        "uncovered_symbols": uncovered[:40],
        "active_symbols": active,
        "priority_reasons": {s: _priority_reason.get(s, "") for s in active[:40]},
        "active_coverage_pct": coverage_pct(active),
        "active_quote_age_p50": q["p50"],
        "active_quote_age_p95": q["p95"],
        "active_quote_age_max": q["max"],
        "active_quote_missing": q["missing"][:20],
        "active_eval_age_p50": e["p50"],
        "active_eval_age_p95": e["p95"],
        "active_eval_age_max": e["max"],
        "active_eval_missing": e["missing"][:20],
        "universe_entry_count": len(_universe_entry_ts),
    }
