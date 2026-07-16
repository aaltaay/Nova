"""Fan-out outbound alerts to enabled channels."""
from __future__ import annotations

import logging
import time
from collections import deque
from typing import Any

from alerts import channels_store
from alerts import discord as discord_sender
from alerts import formatters
from alerts import generic_webhook as webhook_sender
from alerts import telegram as telegram_sender
from constants import (
    ALERTS_CHANNEL_TYPE_DISCORD,
    ALERTS_CHANNEL_TYPE_TELEGRAM,
    ALERTS_CHANNEL_TYPE_WEBHOOK,
    ALERTS_EVENT_TYPE_TEST,
    ALERTS_STATUS_RING_SIZE,
)

logger = logging.getLogger(__name__)

_status_ring: deque[dict[str, Any]] = deque(maxlen=ALERTS_STATUS_RING_SIZE)


def record_status(entry: dict) -> None:
    _status_ring.appendleft(entry)


def get_status() -> list[dict]:
    return list(_status_ring)


def _dispatch_to_channel(channel: channels_store.Channel, event: dict) -> dict:
    started = time.time()
    ok = False
    error: str | None = None
    try:
        if channel.type == ALERTS_CHANNEL_TYPE_DISCORD:
            if not channel.webhook_url:
                raise ValueError("discord channel missing webhook_url")
            body = formatters.format_discord_body(event)
            ok, error = discord_sender.send_discord(channel.webhook_url, body)
        elif channel.type == ALERTS_CHANNEL_TYPE_TELEGRAM:
            if not channel.bot_token or not channel.chat_id:
                raise ValueError("telegram channel missing bot_token or chat_id")
            text = formatters.format_telegram_text(event)
            ok, error = telegram_sender.send_telegram(channel.bot_token, channel.chat_id, text)
        elif channel.type == ALERTS_CHANNEL_TYPE_WEBHOOK:
            if not channel.webhook_url:
                raise ValueError("webhook channel missing webhook_url")
            payload = formatters.format_event_payload(event)
            ok, error = webhook_sender.send_webhook(channel.webhook_url, payload)
        else:
            error = f"unknown channel type: {channel.type}"
    except Exception as exc:
        error = str(exc)
        logger.warning(
            "alerts dispatch: channel %s (%s) failed: %s",
            channel.id,
            channel.name,
            error,
        )

    result = {
        "channel_id": channel.id,
        "channel_name": channel.name,
        "channel_type": channel.type,
        "ok": ok,
        "error": error,
        "elapsed_ms": int((time.time() - started) * 1000),
        "event_type": event.get("type"),
        "ts": time.time(),
    }
    if not ok:
        record_status(result)
        logger.warning(
            "alerts dispatch FAILED channel=%s type=%s error=%s",
            channel.id,
            channel.type,
            error,
        )
    return result


def dispatch_alert(event: dict, *, channel_ids: list[str] | None = None) -> list[dict]:
    """Fan out event to enabled channels. Never swallows per-channel errors."""
    channels = channels_store.list_enabled_channels()
    if channel_ids is not None:
        wanted = set(channel_ids)
        channels = [c for c in channels if c.id in wanted]
    if not channels:
        entry = {
            "ok": False,
            "error": "no enabled channels",
            "event_type": event.get("type"),
            "ts": time.time(),
        }
        record_status(entry)
        logger.warning("alerts dispatch: no enabled channels for event type=%s", event.get("type"))
        return [entry]

    results: list[dict] = []
    for ch in channels:
        results.append(_dispatch_to_channel(ch, event))
    return results


def dispatch_test(channel: channels_store.Channel, message: str | None = None) -> dict:
    """Test-fire a single channel with a synthetic event."""
    text = message or "Nova alert channel test — if you see this, delivery works."
    event = {
        "type": ALERTS_EVENT_TYPE_TEST,
        "text": text,
        "alert": {"ticker": "TEST", "strategy_name": "Test", "price": 1.0, "change_pct": 0.0, "rvol": 1.0},
    }
    return _dispatch_to_channel(channel, event)
