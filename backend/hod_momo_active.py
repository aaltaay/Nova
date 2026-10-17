"""Capacity-bounded HOD active evaluation set (ADR 008).

HOD eligibility is exactly the current-session displayed union: Gappers,
Gainers, Afterhours, and the manually curated Former Momo list -- plus
the bot's stocks and today's hot list (ADR 044), nothing else. No volume seeds,
no open-ticker priority, no Losers, no rotating "explore" tail. Admission order:
a reserved block of ``HOD_MOMO_FORMER_MOMO_MAX_SLOTS`` (``hod_momo_reserved``:
the bot's stocks, the hot list, then Former Momo -- each gets an L1 line, a
snapshot and bars, so the setup scanner follows it), so those lists together
can never starve live movers, then a deterministic round-robin
across ranked Gappers / Gainers / Afterhours queues so no single category
can monopolize the active set. Rows are ordered by ``hod_momo_active_rank``
(pure). Batching and SLO coverage telemetry live in ``hod_momo.active_metrics``
(ADR 004).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Iterable

from constants import (
    HOD_MOMO_ACTIVE_DISCOVERY_SLOTS,
    HOD_MOMO_ACTIVE_HOT_PER_TICK,
    HOD_MOMO_ACTIVE_SET_CAPACITY,
    HOD_MOMO_DISCOVERY_HOLD_SEC,
    HOD_MOMO_FORMER_MOMO_MAX_SLOTS,
    HOD_MOMO_L1_SUBSCRIBE_FAIL_COOLDOWN_SEC,
    IBKR_TABLE_REPRICE_CHUNK_SIZE,
)
from hod_momo.active_metrics import (
    _percentile as _percentile,  # noqa: F401 -- compatibility re-export
    age_stats as age_stats,  # noqa: F401 -- compatibility re-export
    build_metrics_snapshot,
    coverage_pct_from,
    merge_with_scanner_chunk as merge_with_scanner_chunk,  # noqa: F401 -- compatibility re-export
    reset_tail_rotate,
    select_fair_batch_from,
)
from hod_momo_active_rank import discovery_candidates, ordered_unique, ranked_symbols
from hod_momo_reserved import admit_reserved

# Per-symbol live timestamps (unix seconds)
_last_quote_ts: dict[str, float] = {}
_last_eval_ts: dict[str, float] = {}
_universe_entry_ts: dict[str, float] = {}
_priority_reason: dict[str, str] = {}
_active_symbols: list[str] = []
_uncovered_symbols: list[str] = []
# symbol -> unix deadline; set when IBKR L1 subscribe/qualify fails
_l1_fail_until: dict[str, float] = {}
# Discovery-quota bookkeeping (score=0.0 rows only, see build_active_set):
# symbol -> when it first took a discovery slot, and symbol -> cooldown
# deadline once it has yielded that slot without ever pricing up.
_discovery_since: dict[str, float] = {}
_discovery_cooldown_until: dict[str, float] = {}


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
    global _active_symbols, _uncovered_symbols
    _last_quote_ts.clear()
    _last_eval_ts.clear()
    _universe_entry_ts.clear()
    _priority_reason.clear()
    _l1_fail_until.clear()
    _discovery_since.clear()
    _discovery_cooldown_until.clear()
    _active_symbols = []
    _uncovered_symbols = []
    reset_tail_rotate()


def build_active_set(
    *,
    gapper_rows: Iterable[dict] | None = None,
    gainer_rows: Iterable[dict] | None = None,
    afterhours_rows: Iterable[dict] | None = None,
    priority_symbols: Iterable[str] | None = None,
    hot_symbols: Iterable[str] | None = None,
    bot_symbols: Iterable[str] | None = None,
    capacity: int = HOD_MOMO_ACTIVE_SET_CAPACITY,
    now: float | None = None,
) -> ActiveSetSnapshot:
    """Deterministic bounded admission -- the ADR 008 HOD union.

    1. The reserved block, ``HOD_MOMO_FORMER_MOMO_MAX_SLOTS`` slots: the
       bot's stocks (``bot_symbols``), today's hot list (``hot_symbols``),
       then manual Former Momo (``priority_symbols``) -- ``hod_momo_reserved``
       says who takes them and the reason for each name left out; live movers
       keep the rest of the pool.
    2. Up to ``HOD_MOMO_ACTIVE_DISCOVERY_SLOTS`` still-unpriced rows admitted
       next, ranked by IB scan rank, so a fully-priced roster can never
       permanently starve a brand-new name of its first L1 tick (2026-08-31
       XAIR: 40 already-priced rows filled every ordinary slot before an
       unpriced row -- however it was ranked -- was ever reached).
    3. Remaining capacity fills via deterministic round-robin across ranked
       Gappers / Gainers / Afterhours queues (hottest-in-category first),
       so no single table can monopolize every slot.
    """
    global _active_symbols, _uncovered_symbols

    wall = float(now if now is not None else time.time())
    cap = max(1, int(capacity))
    reserved = max(0, min(int(HOD_MOMO_FORMER_MOMO_MAX_SLOTS), cap))
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

    reasons.update(admit_reserved(bot_symbols=bot_symbols, hot_symbols=hot_symbols,
                                  priority_symbols=priority_symbols, slots=reserved, take=_take,
                                  blocked=is_l1_subscribe_blocked))

    candidates = discovery_candidates((gapper_rows, gainer_rows, afterhours_rows))
    candidate_set = set(candidates)
    for sym in list(_discovery_since):
        if sym not in candidate_set:
            _discovery_since.pop(sym, None)
    discovery_slots = max(0, min(int(HOD_MOMO_ACTIVE_DISCOVERY_SLOTS), cap - len(active)))
    discovery_taken = 0
    for sym in candidates:
        if discovery_taken >= discovery_slots:
            break
        if sym in seen or is_l1_subscribe_blocked(sym):
            continue
        cooldown = _discovery_cooldown_until.get(sym)
        if cooldown is not None:
            if wall < cooldown:
                continue
            _discovery_cooldown_until.pop(sym, None)
        since = _discovery_since.get(sym)
        if since is not None and (wall - since) > float(HOD_MOMO_DISCOVERY_HOLD_SEC):
            # Held a slot this long with no price ever landing -- yield it to
            # the next candidate and cool down before trying again.
            _discovery_since.pop(sym, None)
            _discovery_cooldown_until[sym] = wall + float(HOD_MOMO_DISCOVERY_HOLD_SEC)
            continue
        if _take(sym, "discovery"):
            if since is None:
                _discovery_since[sym] = wall
            discovery_taken += 1

    queues: dict[str, list[str]] = {
        "gapper": ranked_symbols(gapper_rows),
        "top_gainer": ranked_symbols(gainer_rows),
        "afterhours": ranked_symbols(afterhours_rows),
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

    all_candidates = ordered_unique(
        list(active)
        + list(bot_symbols or [])
        + list(hot_symbols or [])
        + list(priority_symbols or [])
        + ranked_symbols(gapper_rows)
        + ranked_symbols(gainer_rows)
        + ranked_symbols(afterhours_rows)
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
    symbols = list(active if active is not None else _active_symbols)
    return select_fair_batch_from(
        symbols,
        _last_quote_ts,
        hot=hot,
        chunk_size=chunk_size,
        hot_n=hot_n,
        now=now,
    )


def coverage_pct(symbols: list[str], now: float | None = None) -> float:
    """Percent of symbols with recent quote AND evaluation within max SLO."""
    return coverage_pct_from(symbols, _last_quote_ts, _last_eval_ts, now=now)


def metrics_snapshot() -> dict[str, Any]:
    return build_metrics_snapshot(
        list(_active_symbols),
        list(_uncovered_symbols),
        _priority_reason,
        _last_quote_ts,
        _last_eval_ts,
        len(_universe_entry_ts),
    )
