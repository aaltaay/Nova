"""Alert formatter + hooks coverage (Phase D harden)."""
from __future__ import annotations

from alerts.formatters import (
    format_discord_body,
    format_event_payload,
    format_hod_momo_text,
    format_telegram_text,
)
from alerts.hooks import should_notify_nova_os
from alerts.telegram import _safe_error_message
from constants import (
    ALERTS_EVENT_TYPE_HOD_MOMO,
    ALERTS_EVENT_TYPE_NOVA_OS,
    ALERTS_EVENT_TYPE_TEST,
    NOVA_OS_ACTION_STAGED,
)


def test_test_event_discord_embed_has_description():
    event = {
        "type": ALERTS_EVENT_TYPE_TEST,
        "text": "Nova alert channel test — if you see this, delivery works.",
    }
    body = format_discord_body(event)
    desc = body["embeds"][0]["description"]
    assert "delivery works" in desc
    assert body["embeds"][0]["title"] == "Nova Test Alert"


def test_test_event_telegram_uses_plain_text():
    event = {"type": ALERTS_EVENT_TYPE_TEST, "text": "hello from nova"}
    assert format_telegram_text(event) == "hello from nova"
    assert format_event_payload(event)["text"] == "hello from nova"


def test_hod_formatter_tolerates_missing_price():
    text = format_hod_momo_text({"ticker": "AAA", "strategy_name": "Breakout", "price": None})
    assert "AAA" in text
    assert "—" in text


def test_hod_discord_title():
    body = format_discord_body({
        "type": ALERTS_EVENT_TYPE_HOD_MOMO,
        "alert": {"ticker": "XYZ", "strategy_name": "S", "price": 1.5, "change_pct": 2.0},
    })
    assert body["embeds"][0]["title"] == "HOD Momo Alert"
    assert "XYZ" in body["embeds"][0]["description"]


def test_should_notify_nova_os_filters():
    assert should_notify_nova_os({"kind": "action", "action": NOVA_OS_ACTION_STAGED}) is True
    assert should_notify_nova_os({"kind": "action", "action": "unknown_noise"}) is False
    assert should_notify_nova_os({"kind": "info"}) is False
    assert should_notify_nova_os({"would_execute": True}) is True
    assert should_notify_nova_os({"executed": True}) is True
    assert should_notify_nova_os({"type": ALERTS_EVENT_TYPE_NOVA_OS}) is False


def test_telegram_safe_error_redacts_token_in_url():
    token = "123456:ABC-DEF"
    exc = RuntimeError(f"failed https://api.telegram.org/bot{token}/sendMessage timeout")
    safe = _safe_error_message(exc, token)
    assert token not in safe
    assert "api.telegram.org/bot***/sendMessage" in safe
