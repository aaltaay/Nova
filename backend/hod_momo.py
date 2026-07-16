"""Compatibility facade for the modular HOD Momo engine.

Phase 10 implements ADR 003/004. Mutable data is owned only by
``hod_momo_state``; focused modules resolve that owner at call time. This facade
keeps the long-lived public import path deployable while callers migrate.

Removal criterion: no production caller imports ``hod_momo`` instead of the
focused public boundary it needs. No mutable state aliases are exposed here.
"""
from __future__ import annotations

import cache as _cache
from hod_momo_admin import (
    add_block,
    get_blocklist,
    get_configs,
    get_debug_counters,
    get_debug_recent,
    get_debug_snaps,
    get_debug_symbol,
    get_master,
    is_blocked,
    remove_block,
    reset_all,
    reset_config,
    set_blocklist_changed_hook,
    update_config,
    update_master,
    would_fire_now as _would_fire_now,
)
from hod_momo_alerts import (
    add_ws_client,
    clear_today_alerts,
    flush_consolidated_loop,
    get_broadcast_queue,
    get_today_alerts,
    get_ws_clients,
    get_ws_initial_payload,
    remove_ws_client,
)
from hod_momo_market import (
    active_symbol as _active_symbol,
    effective_min_rvol as _effective_min_rvol,
    get_flow_stats,
    get_fundamentals_queue,
    get_ticker_snapshot,
    in_afterhours_et as _in_afterhours_et,
    in_premarket_et as _in_premarket_et,
    mark_needs_fundamentals,
    mark_surge_seed_attempted,
    peek_rvol_5min,
    pop_fundamentals_request,
    pop_pending_surge_seeds,
    reevaluate_after_surge_seed,
    request_surge_seed,
    seed_price_buffer,
    update_price_buffer as _update_price_buffer,
    update_ticker_snapshot,
)
from hod_momo_models import AlertObject, DecisionRecord, MasterGateConfig, StrategyConfig
from hod_momo_models import TickerSnap as _TickerSnap
from hod_momo_models import (
    alert_from_dict as _alert_from_dict,
    alert_to_dict as _alert_to_dict,
    build_default_config as _build_default_config,
    build_default_configs as _build_default_configs,
    config_from_dict as _config_from_dict,
    config_to_dict as _config_to_dict,
    master_from_dict as _master_from_dict,
    master_to_dict as _master_to_dict,
)
from hod_momo_persist import (
    _load_configs_from_disk,
    _migrate_loaded_configs,
    flush_pending_alert_save,
    get_history_alerts,
    save_alerts as _save_alerts,
    save_configs as _save_configs,
)
from hod_momo_session import (
    check_and_reset_session as _check_and_reset_session,
    current_date_et as _current_date_et,
    load_state,
    session_reset_loop,
)
from hod_momo_state import HodMomoState, get_state, replace_state
from hod_momo_trade import on_trade_update

__all__ = [
    "AlertObject",
    "DecisionRecord",
    "HodMomoState",
    "MasterGateConfig",
    "StrategyConfig",
    "add_block",
    "add_ws_client",
    "clear_today_alerts",
    "flush_consolidated_loop",
    "flush_pending_alert_save",
    "get_blocklist",
    "get_broadcast_queue",
    "get_configs",
    "get_debug_counters",
    "get_debug_recent",
    "get_debug_snaps",
    "get_debug_symbol",
    "get_flow_stats",
    "get_fundamentals_queue",
    "get_history_alerts",
    "get_master",
    "get_state",
    "get_ticker_snapshot",
    "get_today_alerts",
    "get_ws_clients",
    "get_ws_initial_payload",
    "is_blocked",
    "load_state",
    "mark_needs_fundamentals",
    "mark_surge_seed_attempted",
    "on_trade_update",
    "peek_rvol_5min",
    "pop_fundamentals_request",
    "pop_pending_surge_seeds",
    "reevaluate_after_surge_seed",
    "remove_block",
    "remove_ws_client",
    "replace_state",
    "request_surge_seed",
    "reset_all",
    "reset_config",
    "seed_price_buffer",
    "session_reset_loop",
    "set_blocklist_changed_hook",
    "update_config",
    "update_master",
    "update_ticker_snapshot",
]
