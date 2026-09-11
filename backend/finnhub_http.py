"""Shared Finnhub HTTP helpers -- Retry-After / 429 backoff (D-015).

Calendar, logos, and any other Finnhub caller share one process-wide
cooldown so a month-view 429 also pauses profile2 logo warm.
"""
from __future__ import annotations

import logging
import time

from constants import FINNHUB_RETRY_AFTER_DEFAULT_SEC

logger = logging.getLogger(__name__)

_rate_limited_until: float = 0.0


def parse_retry_after(resp: object, default: float = FINNHUB_RETRY_AFTER_DEFAULT_SEC) -> float:
    """Seconds to wait from a Retry-After header. Falls back to ``default``."""
    headers = getattr(resp, "headers", None) or {}
    raw = headers.get("Retry-After") if hasattr(headers, "get") else None
    if raw is None:
        return max(1.0, float(default))
    try:
        return max(1.0, float(raw))
    except (TypeError, ValueError):
        return max(1.0, float(default))


def note_rate_limit(resp: object, *, default: float = FINNHUB_RETRY_AFTER_DEFAULT_SEC) -> float:
    """Record a 429 and return the wait seconds. Extends an existing cooldown."""
    global _rate_limited_until
    wait = parse_retry_after(resp, default)
    until = time.time() + wait
    if until > _rate_limited_until:
        _rate_limited_until = until
    logger.warning("finnhub: 429 Retry-After=%.0fs (blocked until +%.0fs)", wait, wait)
    return wait


def is_blocked(now: float | None = None) -> bool:
    return (now if now is not None else time.time()) < _rate_limited_until


def remaining_sec(now: float | None = None) -> float:
    return max(0.0, _rate_limited_until - (now if now is not None else time.time()))


def reset_for_testing() -> None:
    global _rate_limited_until
    _rate_limited_until = 0.0
