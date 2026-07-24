"""Top-level RTT remains honestly attributed to Alpaca account health."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import health_status
import integrations_health
import observability
import routes.health as health_routes


def test_ping_health_labels_alpaca_account_rtt(monkeypatch):
    state = SimpleNamespace(cached_health={})
    monkeypatch.setattr(health_status, "get_runtime_state", lambda: state)
    monkeypatch.setattr(
        health_status.requests,
        "get",
        lambda *_a, **_k: SimpleNamespace(status_code=200, text=""),
    )

    assert health_status.ping_health("https://example.test", {"key": "x"}) is True
    assert state.cached_health["health_source"] == "alpaca_account_api"
    assert state.cached_health["latency_source"] == "alpaca_account_http"


def test_health_api_distinguishes_rtt_from_market_data_source(monkeypatch):
    state = SimpleNamespace(cached_health={
        "status": "connected",
        "latency_ms": 12,
        "health_source": "alpaca_account_api",
        "latency_source": "alpaca_account_http",
    })
    monkeypatch.setattr(health_routes, "get_runtime_state", lambda: state)
    monkeypatch.setattr(health_routes, "_get_discovery_provider", lambda: "ibkr")
    monkeypatch.setattr(health_routes, "_get_feed", lambda: "iex")
    monkeypatch.setattr(integrations_health, "build_integrations_status", lambda: {})
    monkeypatch.setattr(observability, "sentry_enabled", lambda: False)

    payload = asyncio.run(health_routes.health_check())

    assert payload["market_data_source"] == "ibkr"
    assert payload["latency_source"] == "alpaca_account_http"
    assert payload["health_source"] == "alpaca_account_api"
