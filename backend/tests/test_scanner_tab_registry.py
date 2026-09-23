"""Tests for per-client displayed scanner table hints.

The desk renders more than one scanner table at a time (main tab + scanner
dock), so a client declares a *set* of displayed tables. A single dominant
string could not express "main = Gappers (frozen) + dock = Gainers (live)",
which silently zeroed the whole price_patch feed.
"""
from __future__ import annotations

import scanner_tab_registry as registry


class FakeWS:
    """Stand-in for a WebSocket — the registry only keys off object identity."""


def setup_function() -> None:
    registry._client_tabs.clear()


def test_set_tabs_normalizes_dedupes_and_drops_unknown():
    ws = FakeWS()
    tabs = registry.set_tabs(ws, ["Gainers", "gainers", "bogus", "GAPPERS", "none"])
    assert tabs == ["gainers", "gappers"]


def test_set_tab_single_hint_still_supported():
    ws = FakeWS()
    assert registry.set_tabs(ws, ["gainers"]) == ["gainers"]
    assert registry.set_tab(ws, "losers") == "losers"
    assert registry.get_active_tables() == ["losers"]


def test_none_only_client_contributes_no_tables():
    ws = FakeWS()
    registry.set_tabs(ws, ["none"])
    assert registry.get_active_tables() == []
    assert registry.get_dominant_tab() == "none"


def test_active_tables_is_the_union_across_clients():
    a, b = FakeWS(), FakeWS()
    registry.set_tabs(a, ["gappers", "gainers"])
    registry.set_tabs(b, ["losers"])
    assert set(registry.get_active_tables()) == {"gappers", "gainers", "losers"}


def test_active_tables_orders_by_client_demand():
    a, b, c = FakeWS(), FakeWS(), FakeWS()
    registry.set_tabs(a, ["gainers"])
    registry.set_tabs(b, ["gainers"])
    registry.set_tabs(c, ["losers"])
    # Two clients want gainers, one wants losers — gainers leads.
    assert registry.get_active_tables()[0] == "gainers"
    assert registry.get_dominant_tab() == "gainers"


def test_equal_demand_keeps_the_clients_own_order():
    # One desk: the Trader's Focus rail (Large Cap) is declared first, the
    # Scanner tab it left behind (Gappers) second. Name order would put
    # Gappers first and let it take the active-tab budget.
    ws = FakeWS()
    registry.set_tabs(ws, ["large_cap", "gappers"])
    assert registry.get_active_tables() == ["large_cap", "gappers"]


def test_clear_removes_the_client_hint():
    ws = FakeWS()
    registry.set_tabs(ws, ["gainers"])
    registry.clear(ws)
    assert registry.get_active_tables() == []
    assert registry.client_count() == 0
