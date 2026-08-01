"""Sentry before_send denylist -- drop expected IBKR/desktop ops noise.

Source-level log downgrades are the primary fix; this is the safety net for
escapes (ib_async leftovers, yfinance, asyncio ConnectionReset, etc.).
"""
from __future__ import annotations

from typing import Any

# Message / exception needles (lowercase). Matched against event message,
# log entry, and exception values.
_DROP_MESSAGE_NEEDLES: tuple[str, ...] = (
    "ibkr not connected",
    "ib=none",
    "bridge failed",
    "keeping last-good",
    "cached row(s)",
    "afterhours_cache",
    "unknown reqid",
    "no subscription for",
    "no reqid found",
    "quote not found",
    "quotesummary",
    "error 1100",
    "connectivity lost",
    "error 326",
    "client id is already in use",
    "connectionreseterror",
    "connectionrefusederror",
    "winerror 10054",
    "forcibly closed by the remote host",
    'cannot call "send" once a close message',
    "cannot call 'send' once a close message",
    "must be used within",
    "websocketdisconnect",
    "api connection failed: cancellederror",
    "cancellederror()",
    "should not already be working",
    "datacloneerror",
    "order canceled - reason",
    "cancelorder: unknown orderid",
)

_DROP_EXCEPTION_TYPES: frozenset[str] = frozenset({
    "ConnectionResetError",
    "ConnectionRefusedError",
    "WebSocketDisconnect",
})

_DROP_LOGGERS: frozenset[str] = frozenset({
    "yfinance",
    "yfinance.scrapers.quote",
})


def _event_text(event: dict[str, Any]) -> str:
    parts: list[str] = []
    msg = event.get("message")
    if isinstance(msg, str):
        parts.append(msg)
    logentry = event.get("logentry") or {}
    if isinstance(logentry, dict):
        formatted = logentry.get("formatted") or logentry.get("message")
        if isinstance(formatted, str):
            parts.append(formatted)
    for exc in ((event.get("exception") or {}).get("values") or []):
        if not isinstance(exc, dict):
            continue
        val = exc.get("value")
        if isinstance(val, str):
            parts.append(val)
        typ = exc.get("type")
        if isinstance(typ, str):
            parts.append(typ)
    return " ".join(parts).lower()


def _exception_types(event: dict[str, Any], hint: dict[str, Any]) -> set[str]:
    types: set[str] = set()
    for exc in ((event.get("exception") or {}).get("values") or []):
        if isinstance(exc, dict) and isinstance(exc.get("type"), str):
            types.add(exc["type"])
    exc_info = hint.get("exc_info")
    if exc_info and len(exc_info) >= 1 and exc_info[0] is not None:
        try:
            types.add(exc_info[0].__name__)
        except Exception:
            pass
    return types


def should_drop_sentry_event(event: dict[str, Any], hint: dict[str, Any]) -> bool:
    """True when this event is known ops/benign noise and must not open Issues."""
    logger_name = str(event.get("logger") or "")
    if logger_name in _DROP_LOGGERS or logger_name.startswith("yfinance"):
        return True

    exc_types = _exception_types(event, hint)
    if exc_types & _DROP_EXCEPTION_TYPES:
        return True

    text = _event_text(event)
    if not text:
        return False
    return any(needle in text for needle in _DROP_MESSAGE_NEEDLES)


def before_send(event: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any] | None:
    """sentry_sdk.init before_send hook -- return None to drop."""
    if should_drop_sentry_event(event, hint):
        return None
    return event
