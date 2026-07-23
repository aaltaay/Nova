"""Product lock: scanner discovery is IBKR-only."""
from __future__ import annotations

import alpaca as alpaca_mod


def test_normalize_coerces_alpaca_to_ibkr():
    assert alpaca_mod._normalize_discovery_provider("alpaca") == "ibkr"
    assert alpaca_mod._normalize_discovery_provider("ALPACA") == "ibkr"
    assert alpaca_mod._normalize_discovery_provider("ibkr") == "ibkr"
    assert alpaca_mod._normalize_discovery_provider(None) == "ibkr"
    assert alpaca_mod._normalize_discovery_provider("bogus") == "ibkr"


def test_set_discovery_provider_rejects_alpaca(monkeypatch):
    monkeypatch.setattr(alpaca_mod, "_active_discovery_provider", "")
    alpaca_mod._set_discovery_provider("alpaca")
    assert alpaca_mod._get_discovery_provider() == "ibkr"


def test_env_alpaca_coerces_on_get(monkeypatch):
    monkeypatch.setattr(alpaca_mod, "_active_discovery_provider", "")
    monkeypatch.setenv("NOVA_DISCOVERY_PROVIDER", "alpaca")
    assert alpaca_mod._get_discovery_provider() == "ibkr"


def test_config_options_are_ibkr_only():
    from constants import DISCOVERY_PROVIDER_DEFAULT, DISCOVERY_PROVIDER_OPTIONS

    assert DISCOVERY_PROVIDER_DEFAULT == "ibkr"
    assert DISCOVERY_PROVIDER_OPTIONS == ("ibkr",)


def test_post_config_persists_ibkr_not_alpaca(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    from main import app

    env_path = tmp_path / ".env"
    env_path.write_text("NOVA_DISCOVERY_PROVIDER=ibkr\n", encoding="utf-8")
    monkeypatch.setenv("NOVA_API_HOST", "127.0.0.1")
    monkeypatch.delenv("NOVA_API_KEY", raising=False)
    monkeypatch.setattr("routes.health.env_file_path", lambda: env_path)
    monkeypatch.setattr(alpaca_mod, "_active_discovery_provider", "")

    client = TestClient(app)
    res = client.post(
        "/api/config",
        json={
            "api_key": "",
            "api_secret": "",
            "base_url": "https://api.alpaca.markets",
            "data_feed": "iex",
            "discovery_provider": "alpaca",
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["discovery_provider"] == "ibkr"
    written = env_path.read_text(encoding="utf-8")
    assert "NOVA_DISCOVERY_PROVIDER" in written
    assert "alpaca" not in written.lower() or "api.alpaca.markets" in written.lower()
    # Discovery key must be ibkr (base URL may still mention alpaca.markets).
    assert "NOVA_DISCOVERY_PROVIDER='ibkr'" in written or "NOVA_DISCOVERY_PROVIDER=ibkr" in written
