"""Optional Sentry init + before_send noise policy."""
from __future__ import annotations

from observability import init_sentry, sentry_enabled
from observability_filters import before_send, should_drop_sentry_event


def test_init_sentry_disabled_without_dsn(monkeypatch):
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    assert init_sentry() is False
    assert sentry_enabled() is False


def test_before_send_drops_bridge_keep_cache():
    event = {
        "message": "Gainers bridge failed — keeping 50 cached row(s): TimeoutError",
        "logger": "scanner_runners.movers",
    }
    assert should_drop_sentry_event(event, {}) is True
    assert before_send(event, {}) is None


def test_before_send_drops_ib_none():
    event = {
        "message": "IbkrDiscoveryError: IBKR not connected for scanner TOP_PERC_LOSE (ib=none)",
        "logger": "ibkr.discovery",
    }
    assert before_send(event, {}) is None


def test_before_send_drops_yfinance_logger():
    event = {
        "message": "HTTP Error 404",
        "logger": "yfinance",
    }
    assert before_send(event, {}) is None


def test_before_send_keeps_unrelated_attribute_error():
    event = {
        "message": "AttributeError: boom in ledger",
        "logger": "execution.ledger",
        "exception": {
            "values": [{"type": "AttributeError", "value": "boom in ledger"}],
        },
    }
    assert should_drop_sentry_event(event, {}) is False
    assert before_send(event, {}) is event


def test_before_send_keeps_session_unusable_fingerprint_message():
    """Ops-once capture_message must not be denylisted."""
    event = {
        "message": "ibkr.session.unusable",
        "logger": None,
    }
    assert before_send(event, {}) is event
