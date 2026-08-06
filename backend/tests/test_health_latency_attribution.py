"""Top-level /api/health is Nova process -- not Alpaca account RTT."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import health_status
import integrations_health
import observability
import routes.health as health_routes


def test_mark_nova_process_health_labels_process_source(monkeypatch):
    state = SimpleNamespace(cached_health={})
    monkeypatch.setattr(health_status, "get_runtime_state", lambda: state)

    health_status.mark_nova_process_health()
    assert state.cached_health["status"] == "connected"
    assert state.cached_health["health_source"] == "nova_process"
    assert state.cached_health["latency_source"] == "none"


def test_ping_health_does_not_overwrite_api_chip(monkeypatch):
    state = SimpleNamespace(
        cached_health={
            "status": "connected",
            "latency_ms": 0,
            "health_source": "nova_process",
            "latency_source": "none",
        }
    )
    monkeypatch.setattr(health_status, "get_runtime_state", lambda: state)
    monkeypatch.setattr(
        health_status.requests,
        "get",
        lambda *_a, **_k: SimpleNamespace(status_code=200, text=""),
    )

    assert health_status.ping_health("https://example.test", {"key": "x"}) is True
    assert state.cached_health["health_source"] == "nova_process"


def test_health_api_distinguishes_process_from_market_data_source(monkeypatch):
    state = SimpleNamespace(
        cached_health={
            "status": "connected",
            "latency_ms": 0,
            "health_source": "nova_process",
            "latency_source": "none",
        }
    )
    monkeypatch.setattr(health_routes, "get_runtime_state", lambda: state)
    monkeypatch.setattr(health_routes, "_get_discovery_provider", lambda: "ibkr")
    monkeypatch.setattr(health_routes, "_get_feed", lambda: "iex")
    monkeypatch.setattr(integrations_health, "build_integrations_status", lambda: {})
    monkeypatch.setattr(observability, "sentry_enabled", lambda: False)

    payload = asyncio.run(health_routes.health_check())

    assert payload["market_data_source"] == "ibkr"
    assert payload["latency_source"] == "none"
    assert payload["health_source"] == "nova_process"
