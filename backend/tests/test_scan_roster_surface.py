"""REST scanner lists expose table_state / feed_error (fail-loud, not empty-as-ok)."""
from __future__ import annotations

from runtime_state import get_runtime_state
from runtime_state.state import TABLE_STATE_LIVE, TABLE_STATE_UNAVAILABLE
from routes.scan import get_afterhours, get_gappers, get_movers


def test_gappers_exposes_feed_error_and_table_state():
    state = get_runtime_state()
    prev_err = state.ibkr_bridge_last_error
    prev_ts = state.ibkr_bridge_last_error_ts
    prev_table = (state.gapper_table.state, state.gapper_table.roster_ts)
    try:
        state.ibkr_bridge_last_error = "gappers: TimeoutError: TimeoutError()"
        state.ibkr_bridge_last_error_ts = 1_700_000_000.0
        state.gapper_table.state = TABLE_STATE_UNAVAILABLE
        state.gapper_table.roster_ts = 99.5
        body = get_gappers()
        assert body["feed_error"] == "gappers: TimeoutError: TimeoutError()"
        assert body["table_state"] == TABLE_STATE_UNAVAILABLE
        assert body["roster_ts"] == 99.5
        assert "gappers" in body
    finally:
        state.ibkr_bridge_last_error = prev_err
        state.ibkr_bridge_last_error_ts = prev_ts
        state.gapper_table.state = prev_table[0]
        state.gapper_table.roster_ts = prev_table[1]


def test_gappers_feed_error_is_null_when_clean():
    state = get_runtime_state()
    prev_err = state.ibkr_bridge_last_error
    try:
        state.ibkr_bridge_last_error = ""
        state.gapper_table.state = TABLE_STATE_LIVE
        body = get_gappers()
        assert body["feed_error"] is None
        assert body["table_state"] == TABLE_STATE_LIVE
    finally:
        state.ibkr_bridge_last_error = prev_err


def test_movers_and_afterhours_expose_roster_surface():
    state = get_runtime_state()
    prev_err = state.ibkr_bridge_last_error
    try:
        state.ibkr_bridge_last_error = "movers: IbkrDiscoveryError"
        state.gainer_table.state = TABLE_STATE_LIVE
        state.gainer_table.roster_ts = 1.0
        state.loser_table.state = TABLE_STATE_UNAVAILABLE
        state.loser_table.roster_ts = 2.0
        state.afterhours_table.state = TABLE_STATE_LIVE
        state.afterhours_table.roster_ts = 3.0
        movers = get_movers()
        assert movers["feed_error"] == "movers: IbkrDiscoveryError"
        assert movers["table_state"] == TABLE_STATE_LIVE
        assert movers["loser_table_state"] == TABLE_STATE_UNAVAILABLE
        ah = get_afterhours()
        assert ah["table_state"] == TABLE_STATE_LIVE
        assert ah["roster_ts"] == 3.0
        assert ah["feed_error"] == "movers: IbkrDiscoveryError"
    finally:
        state.ibkr_bridge_last_error = prev_err
