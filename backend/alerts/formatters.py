"""Format HOD Momo + Nova OS events for outbound channels (no secrets)."""
from __future__ import annotations

import json

from constants import (
    ALERTS_EVENT_TYPE_HOD_MOMO,
    ALERTS_EVENT_TYPE_NOVA_OS,
    ALERTS_EVENT_TYPE_TEST,
)


def _fmt_price(value: object) -> str:
    try:
        return f"${float(value):.2f}"
    except (TypeError, ValueError):
        return "—"


def _fmt_change(value: object) -> str:
    try:
        return f"{float(value):+.1f}%"
    except (TypeError, ValueError):
        return "—"


def format_hod_momo_text(alert: dict) -> str:
    ticker = alert.get("ticker", "?")
    strategy = alert.get("strategy_name", "?")
    rvol = alert.get("rvol")
    try:
        rvol_s = f"{float(rvol):.1f}x" if rvol is not None else "—"
    except (TypeError, ValueError):
        rvol_s = "—"
    count = alert.get("consolidation_count", 1)
    burst = f" ({count} alerts)" if count and count > 1 else ""
    return (
        f"HOD Momo · {ticker}{burst}\n"
        f"Strategy: {strategy}\n"
        f"Price: {_fmt_price(alert.get('price'))}  "
        f"Change: {_fmt_change(alert.get('change_pct'))}  RVOL: {rvol_s}"
    )


def format_nova_os_text(receipt: dict) -> str:
    symbol = receipt.get("symbol") or "—"
    action = receipt.get("action") or receipt.get("kind") or "event"
    decision = receipt.get("decision")
    mode = receipt.get("mode")
    executed = receipt.get("executed")
    would = receipt.get("would_execute")
    reasons = receipt.get("reason_codes") or []
    reason_s = ", ".join(reasons[:3]) if reasons else "—"
    lines = [
        f"Nova OS · {symbol}",
        f"Action: {action}",
    ]
    if decision:
        lines.append(f"Decision: {decision}")
    if mode:
        lines.append(f"Mode: {mode}")
    lines.append(f"Would execute: {would}  Executed: {executed}")
    lines.append(f"Reasons: {reason_s}")
    return "\n".join(lines)


def format_event_payload(event: dict) -> dict:
    """JSON-safe payload for generic webhooks (no secrets)."""
    event_type = event.get("type")
    if event_type == ALERTS_EVENT_TYPE_HOD_MOMO:
        return {
            "type": ALERTS_EVENT_TYPE_HOD_MOMO,
            "text": format_hod_momo_text(event.get("alert") or {}),
            "alert": event.get("alert") or {},
        }
    if event_type == ALERTS_EVENT_TYPE_NOVA_OS:
        receipt = event.get("receipt") or {}
        return {
            "type": ALERTS_EVENT_TYPE_NOVA_OS,
            "text": format_nova_os_text(receipt),
            "receipt": receipt,
        }
    # Test / unknown events — prefer explicit text so Discord embeds are not empty.
    text = event.get("text")
    if isinstance(text, str) and text.strip():
        return {
            "type": event_type or ALERTS_EVENT_TYPE_TEST,
            "text": text.strip(),
        }
    return {"type": event_type or "unknown", "text": json.dumps(event, default=str)}


def format_discord_body(event: dict) -> dict:
    payload = format_event_payload(event)
    event_type = event.get("type")
    if event_type == ALERTS_EVENT_TYPE_HOD_MOMO:
        title = "HOD Momo Alert"
        color = 0x3B82F6
    elif event_type == ALERTS_EVENT_TYPE_NOVA_OS:
        title = "Nova OS Event"
        color = 0x10B981
    else:
        title = "Nova Test Alert"
        color = 0x6B7280
    return {
        "embeds": [
            {
                "title": title,
                "description": payload.get("text", ""),
                "color": color,
            }
        ]
    }


def format_telegram_text(event: dict) -> str:
    payload = format_event_payload(event)
    text = payload.get("text")
    if isinstance(text, str) and text:
        return text
    return json.dumps(payload, default=str)
