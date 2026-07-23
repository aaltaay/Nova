"""Capacity-bounded HOD active evaluation set (ADR 008).

HOD eligibility is exactly the current-session displayed union: Gappers,
Gainers, Afterhours, and the manually curated Former Momo list — nothing
else. No volume seeds, no open-ticker priority, no Losers, no rotating
"explore" tail. Admission order: Former Momo first (every registered symbol
guaranteed a slot — see ``hod_momo_admin.update_config``'s capacity check),
then a deterministic round-robin across ranked Gappers / Gainers /
Afterhours queues so no single category can monopolize the active set.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Iterable

from constants import (
    HOD_MOMO_ACTIVE_HOT_PER_TICK,
    HOD_MOMO_ACTIVE_SET_CAPACITY,
    HOD_MOMO_INTEGRITY_ACTIVE_EVAL_MAX_SEC,
    HOD_MOMO_INTEGRITY_ACTIVE_QUOTE_MAX_SEC,
    HOD_MOMO_L1_SUBSCRIBE_FAIL_COOLDOWN_SEC,
    IBKR_TABLE_REPRICE_CHUNK_SIZE,
)

# Per-symbol live timestamps (unix seconds)
_last_quote_ts: dict[str, float] = {}
_last_eval_ts: dict[str, float] = {}
_universe_entry_ts: dict[str, float] = {}
_priority_reason: dict[str, str] = {}
_active_symbols: list[str] = []
_uncovered_symbols: list[str] = []
# symbol → unix deadline; set when IBKR L1 subscribe/qualify fails
_l1_fail_until: dict[str, float] = {}
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


def quote_age_sec(symbol: str, now: float | None = None) -> float | None:
    """Seconds since last note_quote, or None if never quoted."""
    sym = (symbol or "").strip().upper()
    ts = _last_quote_ts.get(sym)
    if ts is None:
        return None
    return float(now if now is not None else time.time()) - float(ts)


def eval_age_sec(symbol: str, now: float | None = None) -> float | None:
    """Seconds since last note_evaluation, or None if never evaluated."""
    sym = (symbol or "").strip().upper()
    ts = _last_eval_ts.get(sym)
    if ts is None:
        return None
    return float(now if now is not None else time.time()) - float(ts)


def note_universe_entries(symbols: Iterable[str], ts: float | None = None) -> None:
    now = float(ts if ts is not None else time.time())
    for raw in symbols:
        sym = (raw or "").strip().upper()
        if sym and sym not in _universe_entry_ts:
            _universe_entry_ts[sym] = now


def note_l1_subscribe_failed(
    symbols: Iterable[str],
    *,
    cooldown_sec: float | None = None,
    now: float | None = None,
) -> None:
    """Cooldown symbols that IBKR cannot stream (qualify/reqMktData failed)."""
    until = float(now if now is not None else time.time()) + float(
        cooldown_sec
        if cooldown_sec is not None
        else HOD_MOMO_L1_SUBSCRIBE_FAIL_COOLDOWN_SEC
    )
    for raw in symbols:
        sym = (raw or "").strip().upper()
        if sym:
            _l1_fail_until[sym] = until


def is_l1_subscribe_blocked(symbol: str, now: float | None = None) -> bool:
    sym = (symbol or "").strip().upper()
    if not sym:
        return False
    deadline = _l1_fail_until.get(sym)
    if deadline is None:
        return False
    ts = float(now if now is not None else time.time())
    if ts >= deadline:
        _l1_fail_until.pop(sym, None)
        return False
    return True


def clear_session_state() -> None:
    global _tail_rotate, _active_symbols, _uncovered_symbols
    _last_quote_ts.clear()
    _last_eval_ts.clear()
    _universe_entry_ts.clear()
    _priority_reason.clear()
    _l1_fail_until.clear()
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
    """Preserve first-seen rank order (do not alphabetically sort)."""
    out: list[str] = []
    seen: set[str] = set()
    for raw in symbols:
        sym = (raw or "").strip().upper()
        if not sym or sym in seen:
            continue
        seen.add(sym)
        out.append(sym)
    return out


def _ranked_symbols(rows: Iterable[dict] | None) -> list[str]:
    """Rows ranked by magnitude of move, hottest first (ties by symbol)."""
    ranked: list[tuple[float, str]] = []
    seen: set[str] = set()
    for row in rows or []:
        sym = (row.get("symbol") or "").strip().upper()
        if not sym or sym in seen:
            continue
        seen.add(sym)
        ranked.append((_row_score(row), sym))
    ranked.sort(key=lambda t: (-t[0], t[1]))
    return [sym for _score, sym in ranked]


def build_active_set(
    *,
    gapper_rows: Iterable[dict] | None = None,
    gainer_rows: Iterable[dict] | None = None,
    afterhours_rows: Iterable[dict] | None = None,
    priority_symbols: Iterable[str] | None = None,
    capacity: int = HOD_MOMO_ACTIVE_SET_CAPACITY,
) -> ActiveSetSnapshot:
    """Deterministic bounded admission — the ADR 008 HOD union.

    1. Manual Former Momo (``priority_symbols``) admitted first, in list
       order. ``hod_momo_admin.update_config`` rejects a list longer than
       ``capacity`` outright, so every registered symbol is guaranteed a
       slot here — this function never has to silently drop one for space.
    2. Remaining capacity fills via deterministic round-robin across ranked
       Gappers / Gainers / Afterhours queues (hottest-in-category first),
       so no single table can monopolize every slot.
    """
    global _active_symbols, _uncovered_symbols

    cap = max(1, int(capacity))
    active: list[str] = []
    reasons: dict[str, str] = {}
    seen: set[str] = set()

    def _take(sym: str, reason: str) -> bool:
        s = (sym or "").strip().upper()
        if not s or s in seen or len(active) >= cap:
            return False
        if is_l1_subscribe_blocked(s):
            return False
        seen.add(s)
        active.append(s)
        reasons[s] = reason
        return True

    for sym in _ordered_unique(priority_symbols or []):
        _take(sym, "former_momo")

    queues: dict[str, list[str]] = {
        "gapper": _ranked_symbols(gapper_rows),
        "top_gainer": _ranked_symbols(gainer_rows),
        "afterhours": _ranked_symbols(afterhours_rows),
    }
    order = list(queues.keys())
    idx = 0
    guard = 0
    max_guard = 3 * sum(len(q) for q in queues.values()) + len(order) + 1
    while len(active) < cap and guard <= max_guard:
        guard += 1
        name = order[idx % len(order)]
        idx += 1
        q = queues[name]
        while q and q[0] in seen:
            q.pop(0)
        if q:
            _take(q.pop(0), name)
        if not any(queues.values()):
            break

    all_candidates = _ordered_unique(
        list(active)
        + list(priority_symbols or [])
        + _ranked_symbols(gapper_rows)
        + _ranked_symbols(gainer_rows)
        + _ranked_symbols(afterhours_rows)
    )
    uncovered = [s for s in all_candidates if s not in seen]

    _priority_reason.clear()
    _priority_reason.update(reasons)
    note_universe_entries(active + uncovered)

    # Drop quote/eval ages for demoted symbols. Keeping them makes a symbol
    # that later re-enters report a stale, hours-old age from before it was
    # dropped.
    prev_active = set(_active_symbols)
    next_active = set(active)
    for sym in prev_active - next_active:
        _last_quote_ts.pop(sym, None)
        _last_eval_ts.pop(sym, None)

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


def get_priority_reason(symbol: str) -> str | None:
    sym = (symbol or "").strip().upper()
    return _priority_reason.get(sym)


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
