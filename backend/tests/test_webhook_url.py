"""SEC-008 — webhook URL SSRF hardening."""
from __future__ import annotations

import pytest

from alerts.webhook_url import validate_webhook_url


def test_rejects_http_scheme():
    with pytest.raises(ValueError, match="scheme"):
        validate_webhook_url("http://example.com/hook")


def test_rejects_loopback_literal(monkeypatch):
    monkeypatch.setattr(
        "alerts.webhook_url.socket.getaddrinfo",
        lambda *a, **k: [(_ for _ in ()).throw(AssertionError("should not resolve"))],
    )
    with pytest.raises(ValueError, match="private|link-local|not allowed"):
        validate_webhook_url("https://127.0.0.1/hook")


def test_rejects_metadata_hostname(monkeypatch):
    monkeypatch.setattr(
        "alerts.webhook_url.socket.getaddrinfo",
        lambda *a, **k: [(_ for _ in ()).throw(AssertionError("should not resolve"))],
    )
    with pytest.raises(ValueError, match="not allowed"):
        validate_webhook_url("https://metadata.google.internal/latest")


def test_rejects_resolved_private_ip(monkeypatch):
    monkeypatch.setattr(
        "alerts.webhook_url.socket.getaddrinfo",
        lambda *a, **k: [(0, 0, 0, "", ("10.0.0.5", 0))],
    )
    with pytest.raises(ValueError, match="private|link-local"):
        validate_webhook_url("https://evil.example/hook")


def test_allows_public_https(monkeypatch):
    monkeypatch.setattr(
        "alerts.webhook_url.socket.getaddrinfo",
        lambda *a, **k: [(0, 0, 0, "", ("8.8.8.8", 0))],
    )
    assert validate_webhook_url("https://discord.com/api/webhooks/1/abc") == (
        "https://discord.com/api/webhooks/1/abc"
    )


def test_allowlist_blocks_other_hosts(monkeypatch):
    monkeypatch.setenv("NOVA_WEBHOOK_HOST_ALLOWLIST", "discord.com")
    monkeypatch.setattr(
        "alerts.webhook_url.socket.getaddrinfo",
        lambda *a, **k: [(0, 0, 0, "", ("8.8.8.8", 0))],
    )
    with pytest.raises(ValueError, match="ALLOWLIST"):
        validate_webhook_url("https://evil.example/hook")
