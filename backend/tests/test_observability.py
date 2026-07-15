"""Optional Sentry init is a no-op without SENTRY_DSN."""
from __future__ import annotations

from observability import init_sentry


def test_init_sentry_disabled_without_dsn(monkeypatch):
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    assert init_sentry() is False
    from observability import sentry_enabled

    assert sentry_enabled() is False
