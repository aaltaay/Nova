"""Persist outbound alert channel configs (secrets stored, masked on read)."""
from __future__ import annotations

import json
import logging
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from constants import (
    ALERTS_CHANNEL_TYPE_DISCORD,
    ALERTS_CHANNEL_TYPE_TELEGRAM,
    ALERTS_CHANNEL_TYPE_WEBHOOK,
    ALERTS_CHANNEL_TYPES,
    ALERTS_CHANNELS_FILENAME,
    ALERTS_MAX_CHANNELS,
    ALERTS_SECRET_MASK_VISIBLE_CHARS,
)
from alerts.webhook_url import validate_webhook_url
from paths import cache_dir

logger = logging.getLogger(__name__)


@dataclass
class Channel:
    id: str
    type: str
    enabled: bool
    name: str
    webhook_url: str | None = None
    bot_token: str | None = None
    chat_id: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


def _store_path() -> Path:
    return cache_dir() / ALERTS_CHANNELS_FILENAME


def mask_secret(value: str | None, visible: int = ALERTS_SECRET_MASK_VISIBLE_CHARS) -> str:
    """Mask a secret for API responses — show only trailing chars."""
    if not value:
        return ""
    if len(value) <= visible:
        return "*" * len(value)
    return "*" * (len(value) - visible) + value[-visible:]


def channel_to_public(ch: Channel) -> dict:
    """Serialize channel for GET — never return full secrets."""
    out = {
        "id": ch.id,
        "type": ch.type,
        "enabled": ch.enabled,
        "name": ch.name,
    }
    if ch.webhook_url:
        out["webhook_url_masked"] = mask_secret(ch.webhook_url)
        out["webhook_url_set"] = True
    else:
        out["webhook_url_set"] = False
    if ch.bot_token:
        out["bot_token_masked"] = mask_secret(ch.bot_token)
        out["bot_token_set"] = True
    else:
        out["bot_token_set"] = False
    if ch.chat_id:
        out["chat_id_masked"] = mask_secret(ch.chat_id)
        out["chat_id_set"] = True
    else:
        out["chat_id_set"] = False
    return out


def _channel_from_dict(d: dict) -> Channel:
    return Channel(
        id=d["id"],
        type=d["type"],
        enabled=bool(d.get("enabled", True)),
        name=d.get("name", ""),
        webhook_url=d.get("webhook_url"),
        bot_token=d.get("bot_token"),
        chat_id=d.get("chat_id"),
        extra=dict(d.get("extra") or {}),
    )


def _load_raw() -> list[dict]:
    path = _store_path()
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return list(data.get("channels") or [])
    except Exception as exc:
        logger.warning("alerts channels_store: failed to load %s: %s", path.name, exc)
        return []


def _save_raw(channels: list[dict]) -> None:
    path = _store_path()
    path.write_text(
        json.dumps({"channels": channels}, indent=2),
        encoding="utf-8",
    )


def list_channels() -> list[dict]:
    return [channel_to_public(_channel_from_dict(d)) for d in _load_raw()]


def get_channel(channel_id: str) -> Channel | None:
    for d in _load_raw():
        if d.get("id") == channel_id:
            return _channel_from_dict(d)
    return None


def _validate_type(channel_type: str) -> None:
    if channel_type not in ALERTS_CHANNEL_TYPES:
        raise ValueError(f"invalid channel type: {channel_type!r}")


def _validate_secrets(channel_type: str, data: dict, *, existing: Channel | None = None) -> None:
    webhook = data.get("webhook_url") or (existing.webhook_url if existing else None)
    bot_token = data.get("bot_token") or (existing.bot_token if existing else None)
    chat_id = data.get("chat_id") or (existing.chat_id if existing else None)
    if channel_type == ALERTS_CHANNEL_TYPE_DISCORD:
        if not webhook:
            raise ValueError("discord channel requires webhook_url")
        validate_webhook_url(webhook)
    elif channel_type == ALERTS_CHANNEL_TYPE_TELEGRAM:
        if not bot_token or not chat_id:
            raise ValueError("telegram channel requires bot_token and chat_id")
    elif channel_type == ALERTS_CHANNEL_TYPE_WEBHOOK:
        if not webhook:
            raise ValueError("webhook channel requires webhook_url")
        validate_webhook_url(webhook)


def create_channel(data: dict) -> dict:
    channels = _load_raw()
    if len(channels) >= ALERTS_MAX_CHANNELS:
        raise ValueError(f"max channels ({ALERTS_MAX_CHANNELS}) reached")
    channel_type = data.get("type", "")
    _validate_type(channel_type)
    _validate_secrets(channel_type, data)
    webhook = data.get("webhook_url")
    if webhook:
        webhook = validate_webhook_url(webhook)
    ch = Channel(
        id=str(uuid.uuid4()),
        type=channel_type,
        enabled=bool(data.get("enabled", True)),
        name=str(data.get("name") or f"{channel_type} channel"),
        webhook_url=webhook,
        bot_token=data.get("bot_token"),
        chat_id=str(data["chat_id"]) if data.get("chat_id") is not None else None,
    )
    channels.append(asdict(ch))
    _save_raw(channels)
    return channel_to_public(ch)


def update_channel(channel_id: str, data: dict) -> dict:
    channels = _load_raw()
    idx = next((i for i, d in enumerate(channels) if d.get("id") == channel_id), None)
    if idx is None:
        raise KeyError(f"channel not found: {channel_id}")
    existing = _channel_from_dict(channels[idx])
    channel_type = data.get("type", existing.type)
    _validate_type(channel_type)
    webhook = data.get("webhook_url", existing.webhook_url)
    if "webhook_url" in data and data.get("webhook_url"):
        webhook = validate_webhook_url(data["webhook_url"])
    merged = {
        "webhook_url": webhook,
        "bot_token": data.get("bot_token", existing.bot_token),
        "chat_id": data.get("chat_id", existing.chat_id),
    }
    _validate_secrets(channel_type, merged, existing=existing)
    updated = Channel(
        id=channel_id,
        type=channel_type,
        enabled=bool(data["enabled"]) if "enabled" in data else existing.enabled,
        name=str(data["name"]) if "name" in data else existing.name,
        webhook_url=merged["webhook_url"],
        bot_token=merged["bot_token"],
        chat_id=str(merged["chat_id"]) if merged["chat_id"] is not None else None,
        extra=existing.extra,
    )
    channels[idx] = asdict(updated)
    _save_raw(channels)
    return channel_to_public(updated)


def delete_channel(channel_id: str) -> bool:
    channels = _load_raw()
    new_channels = [d for d in channels if d.get("id") != channel_id]
    if len(new_channels) == len(channels):
        return False
    _save_raw(new_channels)
    return True


def list_enabled_channels() -> list[Channel]:
    return [c for c in (_channel_from_dict(d) for d in _load_raw()) if c.enabled]
