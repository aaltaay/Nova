"""Thin hooks for HOD Momo + Nova OS — keep source modules clean."""
from __future__ import annotations

import asyncio
import logging

from constants import (
    ALERTS_EVENT_TYPE_HOD_MOMO,
    ALERTS_EVENT_TYPE_NOVA_OS,
    ALERTS_NOVA_OS_NOTIFY_ACTIONS,
    ALERTS_NOVA_OS_NOTIFY_KINDS,
)

logger = logging.getLogger(__name__)


def should_notify_nova_os(receipt: dict) -> bool:
    """Filter Nova OS receipts worth outbound delivery."""
    kind = receipt.get("kind")
    if kind in ALERTS_NOVA_OS_NOTIFY_KINDS:
        action = receipt.get("action")
        if action is None or action in ALERTS_NOVA_OS_NOTIFY_ACTIONS:
            return True
    if receipt.get("would_execute") or receipt.get("executed"):
        return True
    return False


def notify_hod_alert(alert_dict: dict) -> None:
    """Best-effort HOD Momo outbound alert (sync)."""
    try:
        from alerts.dispatch import dispatch_alert

        dispatch_alert({"type": ALERTS_EVENT_TYPE_HOD_MOMO, "alert": alert_dict})
    except Exception as exc:
        logger.warning("notify_hod_alert failed: %s", exc)


async def notify_hod_alert_async(alert_dict: dict) -> None:
    """Fire-and-forget from async flush loop without blocking WS send."""
    try:
        await asyncio.to_thread(notify_hod_alert, alert_dict)
    except Exception as exc:
        logger.warning("notify_hod_alert_async failed: %s", exc)


def notify_nova_os_event(receipt: dict) -> None:
    """Best-effort Nova OS receipt notify — never raises to caller."""
    if not should_notify_nova_os(receipt):
        return
    try:
        from alerts.dispatch import dispatch_alert

        dispatch_alert({"type": ALERTS_EVENT_TYPE_NOVA_OS, "receipt": receipt})
    except Exception as exc:
        logger.warning("notify_nova_os_event failed: %s", exc)
