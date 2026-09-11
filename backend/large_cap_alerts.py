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
# Owner: this module. Persisted on today's dated Large Cap snapshot
# (``fired_today``) with schema_version from cache_schema. Invalidation:
# session_key_et() rollover. Memory is a cache of that file.
_fired_today: dict[tuple[str, str], str] = {}
_fired_loaded = False
_history: deque[dict[str, Any]] = deque(maxlen=LARGE_CAP_ALERT_HISTORY_SIZE)
_FIRED_SEP = ":"


def _serialize_fired() -> dict[str, str]:
    return {f"{sym}{_FIRED_SEP}{direction}": session for (sym, direction), session in _fired_today.items()}


def _ensure_fired_loaded() -> None:
    global _fired_loaded
    if _fired_loaded:
        return
    _fired_loaded = True
    from cache import load_large_cap_fired
    from market import session_key_et

    today = session_key_et()
    for key, session in load_large_cap_fired().items():
        if session != today or _FIRED_SEP not in key:
            continue
        symbol, direction = key.rsplit(_FIRED_SEP, 1)
        if symbol and direction in ("up", "down"):
            _fired_today[(symbol, direction)] = session


def _persist_fired() -> None:
    from cache import save_large_cap_fired

    save_large_cap_fired(_serialize_fired())


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

    _ensure_fired_loaded()
    key = (symbol, direction)
    session_key = session_key_et()
    if _fired_today.get(key) == session_key:
        return None
    _fired_today[key] = session_key
    _persist_fired()

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
    global _fired_loaded
    _fired_today.clear()
    _fired_loaded = False
    _history.clear()
