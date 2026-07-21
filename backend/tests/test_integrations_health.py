"""Aux integration chips for header — not price-feed labels."""
from __future__ import annotations

from integrations_health import build_integrations_status, health_with_integrations


def test_build_integrations_status_shape(monkeypatch):
    monkeypatch.setattr("alpaca._alpaca_headers", lambda: {"APCA-API-KEY-ID": "x"})
    monkeypatch.setattr(
        "runtime_state.get_runtime_state",
        lambda: type("S", (), {"cached_health": {"status": "connected", "latency_ms": 12}})(),
    )
    monkeypatch.setattr("ibkr.client.is_connected", lambda: False)
    monkeypatch.setattr("alpaca._env", lambda k, d="": "")
    monkeypatch.setattr("news.ai_reasoning._is_enabled", lambda: False)

    out = build_integrations_status()
    assert set(out) >= {"alpaca", "ibkr", "openai", "yfinance", "archive"}
    assert out["alpaca"]["status"] == "ok"
    assert "not live prices" in out["alpaca"]["detail"]
    assert out["openai"]["status"] == "off"


def test_health_with_integrations_merges():
    merged = health_with_integrations({"status": "connected", "latency_ms": 1})
    assert merged["status"] == "connected"
    assert "integrations" in merged
    assert "alpaca" in merged["integrations"]
