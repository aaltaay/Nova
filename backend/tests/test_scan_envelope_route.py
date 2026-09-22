"""GET /api/scan/envelope (QA C48) and ASCII integration details (QA C63)."""
from __future__ import annotations

from integrations_health import build_integrations_status
from routes.scan import get_scan_envelope
from runtime_state import get_runtime_state
from runtime_state.state import TABLE_STATE_FROZEN, TABLE_STATE_LIVE


def test_envelope_carries_mode_health_feed_error_and_table_state_without_rows():
    state = get_runtime_state()
    prev = (
        state.current_mode, state.ibkr_bridge_last_error, state.gapper_table.state,
        state.gapper_table.roster_ts, state.gapper_cache_ts, state.gainer_table.state,
    )
    try:
        state.current_mode = "market"
        state.ibkr_bridge_last_error = "ibkr: TimeoutError: TimeoutError()"
        state.gapper_table.state = TABLE_STATE_FROZEN
        state.gapper_table.roster_ts = 11.0
        state.gapper_cache_ts = 12.0
        state.gainer_table.state = TABLE_STATE_LIVE
        body = get_scan_envelope()
        assert body["mode"] == "market"
        assert body["feed_error"] == "ibkr: TimeoutError: TimeoutError()"
        assert "integrations" in body["health"]
        assert body["tables"]["gappers"] == {"table_state": TABLE_STATE_FROZEN, "roster_ts": 11.0, "last_scan": 12.0}
        assert body["tables"]["gainers"]["table_state"] == TABLE_STATE_LIVE
        assert set(body["tables"]) == {"gappers", "gainers", "losers", "afterhours", "large_cap"}
        # Envelope only: never a row list.
        assert not any(isinstance(v, list) for v in body.values())
        state.ibkr_bridge_last_error = ""
        assert get_scan_envelope()["feed_error"] is None
    finally:
        (
            state.current_mode, state.ibkr_bridge_last_error, state.gapper_table.state,
            state.gapper_table.roster_ts, state.gapper_cache_ts, state.gainer_table.state,
        ) = prev


def test_integration_details_are_ascii():
    # A client that decodes charset-less JSON as cp1252 turned an em dash
    # into three garbage characters (QA C63).
    for name, chip in build_integrations_status().items():
        assert chip["detail"].isascii(), (name, chip["detail"])
