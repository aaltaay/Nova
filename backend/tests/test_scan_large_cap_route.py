"""GET/POST /api/large-cap* routes (ADR 014)."""
from __future__ import annotations

import pytest

from runtime_state import get_runtime_state
from runtime_state.state import TABLE_STATE_LIVE
from routes.scan import (
    LargeCapConfigPatch,
    get_history_dates,
    get_large_cap,
    get_large_cap_alerts,
    get_large_cap_config,
    update_large_cap_config,
)


def test_get_large_cap_returns_rows_with_scores():
    state = get_runtime_state()
    prev_rows = state.large_cap_cache
    prev_table_state = state.large_cap_table.state
    try:
        state.large_cap_cache = [
            {"symbol": "NVDA", "price": 200.0, "rvol": 3.0, "atr_expansion": 2.0,
             "change_20d_pct": 0.1},
            {"symbol": "AMD", "price": 150.0, "rvol": 1.0, "atr_expansion": 0.5,
             "change_20d_pct": 0.02},
        ]
        state.large_cap_table.state = TABLE_STATE_LIVE
        body = get_large_cap()
        assert body["table_state"] == TABLE_STATE_LIVE
        rows = body["large_cap"]
        assert len(rows) == 2
        nvda = next(r for r in rows if r["symbol"] == "NVDA")
        assert nvda["large_cap_score"] is not None
    finally:
        state.large_cap_cache = prev_rows
        state.large_cap_table.state = prev_table_state


def test_large_cap_config_get_and_post_round_trip():
    body = get_large_cap_config()
    assert body["market_cap_above"] == 50_000

    patched = update_large_cap_config(LargeCapConfigPatch(market_cap_above=25_000))
    assert patched["market_cap_above"] == 25_000

    body_after = get_large_cap_config()
    assert body_after["market_cap_above"] == 25_000


def test_large_cap_config_post_rejects_invalid_value():
    from fastapi import HTTPException

    with pytest.raises(HTTPException):
        update_large_cap_config(LargeCapConfigPatch(market_cap_above=-1))


def test_large_cap_alerts_route_returns_history():
    body = get_large_cap_alerts()
    assert "alerts" in body
    assert isinstance(body["alerts"], list)


def test_history_dates_accepts_large_cap_type():
    body = get_history_dates(type="large_cap")
    assert "dates" in body


def test_history_dates_rejects_unknown_type():
    body = get_history_dates(type="not-a-real-type")
    assert body["dates"] == []
