"""Characterization tests for the explicit scanner runtime-state owner."""
from __future__ import annotations

import ticker
from routes import strategy as strategy_routes
from runtime_state import (
    ScannerRuntimeState,
    get_runtime_state,
    reset_runtime_state,
    set_runtime_state_for_testing,
)


def test_rebinding_owner_is_visible_to_existing_consumers():
    first = ScannerRuntimeState()
    previous = set_runtime_state_for_testing(first)
    try:
        first.gapper_cache = [{"symbol": "OLD", "price": 1.0}]
        assert ticker._find_ibkr_cache_row("OLD") is not None

        replacement = ScannerRuntimeState()
        replacement.gapper_cache = [{"symbol": "NEW", "price": 2.0}]
        set_runtime_state_for_testing(replacement)

        assert ticker._find_ibkr_cache_row("OLD") is None
        assert ticker._find_ibkr_cache_row("NEW") is replacement.gapper_cache[0]
        assert strategy_routes._gapper_cache() is replacement.gapper_cache
    finally:
        set_runtime_state_for_testing(previous)


def test_reset_runtime_state_clears_all_mutable_scanner_values():
    state = ScannerRuntimeState()
    previous = set_runtime_state_for_testing(state)
    try:
        state.assets_cache = ["ABC"]
        state.gapper_cache = [{"symbol": "ABC"}]
        state.avg_volume_cache = {"ABC": 100.0}
        state.cached_health = {"status": "connected", "latency_ms": 1}
        state.current_mode = "market"
        state.hod_momo_universe = {"ABC"}

        reset = reset_runtime_state(config=state.config)

        assert reset is get_runtime_state()
        assert reset.assets_cache == []
        assert reset.gapper_cache == []
        assert reset.avg_volume_cache == {}
        assert reset.cached_health == {
            "status": "loading",
            "latency_ms": 0,
            "health_source": "alpaca_account_api",
            "latency_source": "alpaca_account_http",
        }
        assert reset.current_mode == "closed"
        assert reset.hod_momo_universe == set()
    finally:
        set_runtime_state_for_testing(previous)
