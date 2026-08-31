"""Gappers is a filtered projection of Gainers (ibkr/gapper_view.py), so an
unpriced Gainers roster starves the Gappers projection even when every
*displayed* Gappers row is already priced. Integrity must judge that
dependency, not just the displayed table (2026-08-31 XAIR: Gappers reported
11/11 priced while the Gainers row IB ranked #3 had no quote at all).
"""
from __future__ import annotations

import time

import scanner_tab_registry as _tabs
from ibkr import scanner_session as _ss
from integrity_live import _row_price_coverage
from runtime_state.state import ScannerRuntimeState, TableState


def _live_state(*, gainer_rows, gapper_rows) -> ScannerRuntimeState:
    state = ScannerRuntimeState()
    state.gapper_cache = gapper_rows
    state.gapper_table = TableState(state="live", roster_ts=time.time())
    state.gainer_cache = gainer_rows
    state.gainer_table = TableState(state="live", roster_ts=time.time())
    return state


def test_gainers_judged_when_only_gappers_is_displayed(monkeypatch):
    monkeypatch.setattr(_tabs, "get_active_tables", lambda: [_ss.TABLE_GAPPERS])
    now = time.time()
    state = _live_state(
        gapper_rows=[{"symbol": "AEHL", "price": 5.96}],
        gainer_rows=[
            {"symbol": "AEHL", "price": 5.96},
            {"symbol": "XAIR", "price": None, "admitted_ts": now - 300.0},
        ],
    )
    coverage = _row_price_coverage(state)
    tables = {c["table"]: c for c in coverage}
    assert _ss.TABLE_GAPPERS in tables
    assert _ss.TABLE_GAINERS in tables
    assert tables[_ss.TABLE_GAINERS]["priced"] == 1
    assert tables[_ss.TABLE_GAINERS]["rows"] == 2


def test_gainers_age_comes_from_oldest_unpriced_row_not_roster_ts(monkeypatch):
    """A busy table's roster_ts is rewritten on every IB push, so it can
    never age past the admission grace on its own -- the per-row
    admitted_ts is what lets integrity actually judge a starved row."""
    monkeypatch.setattr(_tabs, "get_active_tables", lambda: [_ss.TABLE_GAPPERS])
    now = time.time()
    state = _live_state(
        gapper_rows=[],
        gainer_rows=[
            {"symbol": "XAIR", "price": None, "admitted_ts": now - 400.0},
        ],
    )
    state.gainer_table.roster_ts = now  # just committed again, moments ago
    coverage = _row_price_coverage(state)
    tables = {c["table"]: c for c in coverage}
    assert tables[_ss.TABLE_GAINERS]["roster_age_sec"] >= 399.0


def test_gainers_not_added_when_gappers_not_displayed(monkeypatch):
    monkeypatch.setattr(_tabs, "get_active_tables", lambda: [_ss.TABLE_LOSERS])
    state = _live_state(gapper_rows=[], gainer_rows=[{"symbol": "AAA", "price": None}])
    state.loser_cache = [{"symbol": "BBB", "price": 1.0}]
    state.loser_table = TableState(state="live", roster_ts=time.time())
    coverage = _row_price_coverage(state)
    tables = {c["table"] for c in coverage}
    assert _ss.TABLE_GAINERS not in tables
