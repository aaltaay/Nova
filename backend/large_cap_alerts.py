"""Large Cap breakout alert channel (ADR 014) -- separate from HOD Momo.

Trigger: price breaks the stored 20-day high (or low), confirmed by RVOL
above a threshold. Per-symbol, per-direction, once per session. Fires
through the existing outbound ``alerts.dispatch`` fan-out (Discord /
Telegram / webhook) under its own event type -- never through
``hod_momo.on_trade_update`` -- so day-trade chimes and swing signals never
mix (explicit user decision, ADR 014).
"""
from __future__ import annotations

import logging
import time
from collections import deque
from typing import Any

from constants import (
    LARGE_CAP_ALERT_EVENT_TYPE,
    LARGE_CAP_ALERT_HISTORY_SIZE,
    LARGE_CAP_ALERT_MIN_RVOL,
)

logger = logging.getLogger(__name__)

# (symbol, direction) -> session_key already alerted this session.
_fired_today: dict[tuple[str, str], str] = {}
_history: deque[dict[str, Any]] = deque(maxlen=LARGE_CAP_ALERT_HISTORY_SIZE)


def get_alert_history() -> list[dict[str, Any]]:
    return list(_history)


def check_breakout(
    symbol: str,
    *,
    price: float | None,
    high_20d: float | None,
    low_20d: float | None,
    rvol: float | None,
) -> dict[str, Any] | None:
    """Check + fire a 20-day breakout alert. Returns the fired event, or ``None``."""
    if price is None or rvol is None or rvol < LARGE_CAP_ALERT_MIN_RVOL:
        return None
    direction: str | None = None
    level: float | None = None
    if high_20d is not None and price > high_20d:
        direction, level = "up", high_20d
    elif low_20d is not None and price < low_20d:
        direction, level = "down", low_20d
    if direction is None or level is None:
        return None

    from market import session_key_et

    key = (symbol, direction)
    session_key = session_key_et()
    if _fired_today.get(key) == session_key:
        return None
    _fired_today[key] = session_key

    event = {
        "type": LARGE_CAP_ALERT_EVENT_TYPE,
        "symbol": symbol,
        "direction": direction,
        "price": price,
        "level_20d": level,
        "rvol": rvol,
        "ts": time.time(),
        "text": (
            f"{symbol} broke {'above' if direction == 'up' else 'below'} its "
            f"20-day {'high' if direction == 'up' else 'low'} "
            f"(${level:.2f}) at ${price:.2f}, RVOL {rvol:.1f}x"
        ),
    }
    _history.appendleft(event)
    try:
        from alerts.dispatch import dispatch_alert

        dispatch_alert(event)
    except Exception:
        logger.exception("large_cap_alerts: dispatch failed for %s", symbol)
    return event


def reset_for_testing() -> None:
    _fired_today.clear()
    _history.clear()
