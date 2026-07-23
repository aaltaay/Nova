"""Tests for ibkr_bridge.py table/L1 quote application onto HOD Momo."""
from __future__ import annotations

import ibkr_bridge
import hod_momo_active as _hod_active
from ibkr import scanner_session as _ss
from runtime_state import ScannerRuntimeState
from runtime_state.state import TABLE_STATE_FROZEN


def _fake_state() -> ScannerRuntimeState:
    return ScannerRuntimeState()


def test_apply_table_quotes_passes_day_high_to_hod_momo(monkeypatch):
    """Cold reqTickersAsync snapshots must seed HOD truth same as the live L1 path
    (apply_l1_quote) — otherwise HOD strategies stay cold-start blocked until a
    live tick happens to arrive (see gap5 in the end-to-end verification)."""
    state = _fake_state()
    monkeypatch.setattr(ibkr_bridge, "get_runtime_state", lambda: state)
    monkeypatch.setattr(_hod_active, "get_active_symbols", lambda: [])

    captured: dict = {}

    def fake_on_trade_update(symbol, price, ts, *, volume=None, day_high=None):
        captured["symbol"] = symbol
        captured["price"] = price
        captured["day_high"] = day_high

    monkeypatch.setattr(ibkr_bridge._hod_momo, "on_trade_update", fake_on_trade_update)

    quotes = {"AAA": {"price": 10.0, "prev_close": 9.0, "volume": 100, "high": 10.5}}
    ibkr_bridge.apply_table_quotes(quotes)

    assert captured["symbol"] == "AAA"
    assert captured["day_high"] == 10.5


def test_apply_table_quotes_missing_high_passes_none(monkeypatch):
    state = _fake_state()
    monkeypatch.setattr(ibkr_bridge, "get_runtime_state", lambda: state)
    monkeypatch.setattr(_hod_active, "get_active_symbols", lambda: [])

    captured: dict = {}

    def fake_on_trade_update(symbol, price, ts, *, volume=None, day_high=None):
        captured["day_high"] = day_high

    monkeypatch.setattr(ibkr_bridge._hod_momo, "on_trade_update", fake_on_trade_update)

    quotes = {"AAA": {"price": 10.0, "prev_close": 9.0, "volume": 100}}
    ibkr_bridge.apply_table_quotes(quotes)

    assert captured["day_high"] is None


def test_apply_l1_quote_never_mutates_a_frozen_table(monkeypatch):
    """ADR 008: HOD's reserved L1 pool keeps ticking retained symbols after
    their table freezes — that must never reprice the frozen cache/timestamp
    (see PROBLEM_LOG scanner_stream shadow parity review)."""
    state = _fake_state()
    state.gainer_cache = [{"symbol": "AAA", "price": 5.0, "prev_close": 4.0, "volume": 10}]
    state.gainer_cache_ts = 111.0
    state.gainer_table.state = TABLE_STATE_FROZEN
    state.gainer_table.session_key = _ss.session_key_et()
    monkeypatch.setattr(ibkr_bridge, "get_runtime_state", lambda: state)
    monkeypatch.setattr(_hod_active, "get_active_symbols", lambda: ["AAA"])
    monkeypatch.setattr(ibkr_bridge._hod_momo, "on_trade_update", lambda *a, **k: None)

    ibkr_bridge.apply_l1_quote("AAA", 9.0, 500, 4.0, 222.0)

    assert state.gainer_cache[0]["price"] == 5.0
    assert state.gainer_cache_ts == 111.0


def test_apply_l1_quote_reprices_a_live_table(monkeypatch):
    state = _fake_state()
    state.gainer_cache = [{"symbol": "AAA", "price": 5.0, "prev_close": 4.0, "volume": 10}]
    state.gainer_cache_ts = 111.0
    monkeypatch.setattr(ibkr_bridge, "get_runtime_state", lambda: state)
    monkeypatch.setattr(_hod_active, "get_active_symbols", lambda: ["AAA"])
    monkeypatch.setattr(ibkr_bridge._hod_momo, "on_trade_update", lambda *a, **k: None)

    ibkr_bridge.apply_l1_quote("AAA", 9.0, 500, 4.0, 222.0)

    assert state.gainer_cache[0]["price"] == 9.0
    assert state.gainer_cache_ts == 222.0


def test_refresh_hod_active_set_always_recomputes(monkeypatch):
    """Regression for the WLDS lockout (PROBLEM_LOG 2026-07-23): once all three
    scanner tables freeze for the day, their cache list objects are never
    reassigned again (ADR 008 — frozen membership is immutable), so an
    id()+len()-based memoization would return the same stale snapshot
    forever. refresh_hod_active_set must reflect the live cache contents on
    every call, even when the caller mutates the same list object in place
    between calls rather than reassigning it."""
    state = _fake_state()
    state.afterhours_cache = [{"symbol": "AAA", "change_pct": 50.0}]
    monkeypatch.setattr(ibkr_bridge, "get_runtime_state", lambda: state)

    first = ibkr_bridge.refresh_hod_active_set()
    assert "AAA" in first
    assert "WLDS" not in first

    # Same list object (id unchanged), mutated in place — mirrors what a
    # frozen table's cache would look like if a symbol were already present
    # in it but a stale-cache bug had excluded it from an earlier snapshot.
    state.afterhours_cache.append({"symbol": "WLDS", "change_pct": 117.0})

    second = ibkr_bridge.refresh_hod_active_set()
    assert "WLDS" in second
