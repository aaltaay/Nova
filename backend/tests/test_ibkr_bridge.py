"""Tests for ibkr_bridge.py table/L1 quote application onto HOD Momo."""
from __future__ import annotations

import ibkr_bridge
import hod_momo_active as _hod_active
from runtime_state import ScannerRuntimeState


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
