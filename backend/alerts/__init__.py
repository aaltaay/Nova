"""Outbound alert channels — Discord, Telegram, generic webhooks (Phase D)."""

from alerts.dispatch import dispatch_alert, get_status, record_status
from alerts.hooks import notify_hod_alert, notify_nova_os_event

__all__ = [
    "dispatch_alert",
    "get_status",
    "notify_hod_alert",
    "notify_nova_os_event",
    "record_status",
]
