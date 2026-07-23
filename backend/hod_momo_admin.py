"""HOD Momo config, blocklist, and debug administration boundary."""
from __future__ import annotations

import time
from typing import Callable

import cache as _cache
import hod_momo_debug as _debug
import hod_momo_former as _former
import hod_momo_market as _market
import hod_momo_persist as _persist
import hod_momo_state as _state
import hod_momo_high as _high
from constants import (
    HOD_MOMO_ACTIVE_SET_CAPACITY,
    HOD_MOMO_FORMER_MOMO_STRATEGY_ID,
    HOD_MOMO_HOD_EPSILON_ABS,
    HOD_MOMO_HOD_EPSILON_PCT,
    HOD_MOMO_NEW_HOD_GRACE_SEC,
    HOD_MOMO_RVOL_WARMUP_GRACE_SEC,
    HOD_MOMO_STRATEGY_ID_MAX,
)
from hod_momo_filters import evaluate_strategy
from hod_momo_filters import fails_hod_gate
from hod_momo_filters import passes_master_gate
from hod_momo_filters import price_surge
from hod_momo_models import (
    MasterGateConfig,
    build_default_config,
    build_default_configs,
    config_to_dict,
    master_to_dict,
)


def get_configs() -> dict:
    state = _state.get_state()
    return {
        "master": master_to_dict(state.master),
        "strategies": {
            str(sid): config_to_dict(config)
            for sid, config in state.configs.items()
        },
    }


def update_config(strategy_id: int, patch: dict) -> dict | None:
    config = _state.get_state().configs.get(strategy_id)
    if config is None:
        return None
    if strategy_id == HOD_MOMO_FORMER_MOMO_STRATEGY_ID and "former_momo_list" in patch:
        raw_list = patch.get("former_momo_list") or []
        if len(raw_list) > HOD_MOMO_ACTIVE_SET_CAPACITY:
            # Every registered Former Momo symbol is guaranteed a HOD active
            # slot (ADR 008) — reject outright rather than silently truncate
            # or let later admissions get starved.
            return {
                "error": (
                    f"former_momo_list has {len(raw_list)} symbols, exceeding the "
                    f"HOD active-set capacity ({HOD_MOMO_ACTIVE_SET_CAPACITY}). "
                    "Remove some symbols before saving — every entry is guaranteed "
                    "a live slot, so the list cannot exceed capacity."
                ),
            }
    for key, value in patch.items():
        if hasattr(config, key) and key != "strategy_id":
            setattr(config, key, value)
    _persist.save_configs()
    return config_to_dict(config)


def reset_config(strategy_id: int) -> dict | None:
    if strategy_id not in range(1, HOD_MOMO_STRATEGY_ID_MAX + 1):
        return None
    state = _state.get_state()
    state.configs[strategy_id] = build_default_config(strategy_id)
    _persist.save_configs()
    return config_to_dict(state.configs[strategy_id])


def reset_all() -> dict:
    state = _state.get_state()
    state.configs = build_default_configs()
    state.master = MasterGateConfig()
    _persist.save_configs()
    return get_configs()


def get_master() -> dict:
    return master_to_dict(_state.get_state().master)


def update_master(patch: dict) -> dict:
    master = _state.get_state().master
    for key, value in patch.items():
        if hasattr(master, key):
            setattr(master, key, value)
    _persist.save_configs()
    return master_to_dict(master)


def get_blocklist() -> list[str]:
    return sorted(_state.get_state().blocklist)


def is_blocked(symbol: str) -> bool:
    return symbol.upper() in _state.get_state().blocklist


def set_blocklist_changed_hook(callback: Callable[[], None] | None) -> None:
    _state.get_state().on_blocklist_changed = callback


def add_block(symbol: str) -> list[str]:
    state = _state.get_state()
    state.blocklist.add(symbol.upper())
    _cache.save_hod_momo_blocklist(list(state.blocklist))
    if state.on_blocklist_changed:
        state.on_blocklist_changed()
    return get_blocklist()


def remove_block(symbol: str) -> list[str]:
    state = _state.get_state()
    state.blocklist.discard(symbol.upper())
    _cache.save_hod_momo_blocklist(list(state.blocklist))
    if state.on_blocklist_changed:
        state.on_blocklist_changed()
    return get_blocklist()


def get_debug_counters() -> dict:
    state = _state.get_state()
    return _debug.build_debug_counters(
        state.total_trades_seen,
        state.ticker_snaps,
        state.gate_counters,
        state.session_highs,
        state.fundamentals_queue,
        state.pending_consolidation,
        state.today_alerts,
    )


def get_debug_symbol(symbol: str) -> dict:
    state = _state.get_state()
    sym = symbol.upper()
    snap = state.ticker_snaps.get(sym)
    decisions = [
        {
            "ts": record.ts,
            "price": record.price,
            "snap": record.snap,
            "gate_blocked": record.gate_blocked,
            "strategies": record.strategies,
            "would_fire": record.would_fire,
        }
        for record in list(state.per_symbol_decisions.get(sym, []))
    ]
    would_fire = would_fire_now(sym) if snap else None
    payload = _debug.build_debug_symbol(
        sym,
        snap,
        decisions,
        state.session_highs.get(sym),
        would_fire,
    )
    payload.update(_high.high_debug(sym))
    return payload


def would_fire_now(symbol: str) -> dict:
    state = _state.get_state()
    snap = state.ticker_snaps.get(symbol)
    if not snap:
        return {"gate": "no_snap", "strategies": []}
    in_warmup_grace = bool(state.startup_ts) and (
        time.monotonic() - state.startup_ts
    ) < HOD_MOMO_RVOL_WARMUP_GRACE_SEC
    gate_ok, gate_reason = passes_master_gate(
        snap,
        state.master,
        _market.effective_min_rvol(),
        in_warmup_grace,
        state.price_buffer.get(symbol),
    )
    if not gate_ok:
        return {"gate": gate_reason, "strategies": []}
    results = []
    for strategy_id, config in state.configs.items():
        if not config.enabled:
            continue
        former_block = _former.former_momo_block_reason(strategy_id, symbol, config)
        if former_block:
            results.append(
                {
                    "id": strategy_id,
                    "name": config.name,
                    "passed": False,
                    "blocked_by": former_block,
                }
            )
            continue
        hod_block = fails_hod_gate(
            float(snap.price or 0.0),
            state.session_highs.get(symbol, 0.0),
            config,
            state.master.hod_required,
            high_seeded=_high.is_high_seeded(symbol),
            epsilon_abs=HOD_MOMO_HOD_EPSILON_ABS,
            epsilon_pct=HOD_MOMO_HOD_EPSILON_PCT,
            new_hod_age_sec=_high.last_new_hod_age_sec(symbol),
            new_hod_grace_sec=HOD_MOMO_NEW_HOD_GRACE_SEC,
        )
        if hod_block:
            results.append(
                {
                    "id": strategy_id,
                    "name": config.name,
                    "passed": False,
                    "blocked_by": hod_block,
                }
            )
            continue
        surge = (
            price_surge(
                state.price_buffer.get(symbol),
                config.surge_window_min,
                config.surge_method,
            )
            if config.surge_window_min > 0
            else None
        )
        passed, reason = evaluate_strategy(
            config,
            snap,
            surge,
            lambda: _market.mark_needs_fundamentals(symbol),
        )
        results.append(
            {
                "id": strategy_id,
                "name": config.name,
                "passed": passed,
                "blocked_by": reason,
            }
        )
    # Soft master_rvol keeps the reason on the gate label so debug shows why
    # float strategies are blocked while Squeeze/Running-Up still evaluate.
    return {
        "gate": "passed" if gate_ok else gate_reason,
        "strategies": results,
    }


def get_debug_recent(limit: int = 100) -> list[dict]:
    return _debug.build_debug_recent(_state.get_state().recent_decisions, limit)


def get_debug_snaps(limit: int = 50) -> list[dict]:
    return _debug.build_debug_snaps(_state.get_state().ticker_snaps, limit)
