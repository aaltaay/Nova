"""
Lightweight asyncio event-loop lag sampler.

A busy event loop (IBKR callbacks, an accidental blocking call sneaking onto
the loop, etc.) delays every coroutine's next wakeup, including HTTP
handlers. Prior incidents inferred loop contention from health-probe
timeouts alone (see PROBLEM_LOG 2026-07-23) with no direct measurement. This
module samples the gap between an expected and actual wakeup so
``/api/health`` can report a real number instead of a guess.
"""
from __future__ import annotations

import asyncio
import logging

from constants import (
    LOOP_LAG_SAMPLE_INTERVAL_SEC,
    LOOP_LAG_WEDGED_MS,
    LOOP_LAG_WEDGED_STREAK,
)

logger = logging.getLogger(__name__)

# Any single sample lagging this far past its expected wakeup logs a warning
# (a genuinely idle loop lags by ~0ms; this only fires under real contention).
_WARN_THRESHOLD_SEC = 1.0

_last_lag_ms: float = 0.0
_max_lag_ms: float = 0.0
_samples: int = 0
_high_streak: int = 0
_wedged: bool = False


def snapshot() -> dict[str, float | int | bool]:
    return {
        "last_ms": round(_last_lag_ms, 1),
        "max_ms": round(_max_lag_ms, 1),
        "samples": _samples,
        "wedged": _wedged,
        "high_streak": _high_streak,
    }


def is_wedged() -> bool:
    return _wedged


def reset_for_testing() -> None:
    global _last_lag_ms, _max_lag_ms, _samples, _high_streak, _wedged
    _last_lag_ms = 0.0
    _max_lag_ms = 0.0
    _samples = 0
    _high_streak = 0
    _wedged = False


async def sample_loop_lag_loop() -> None:
    """Background task: sleep a fixed interval, record how much longer it
    actually took. Runs until cancelled at shutdown."""
    global _last_lag_ms, _max_lag_ms, _samples, _high_streak, _wedged
    loop = asyncio.get_running_loop()
    while True:
        expected = loop.time() + LOOP_LAG_SAMPLE_INTERVAL_SEC
        await asyncio.sleep(LOOP_LAG_SAMPLE_INTERVAL_SEC)
        lag_sec = max(0.0, loop.time() - expected)
        _last_lag_ms = lag_sec * 1000.0
        _max_lag_ms = max(_max_lag_ms, _last_lag_ms)
        _samples += 1
        if _last_lag_ms >= LOOP_LAG_WEDGED_MS:
            _high_streak += 1
        else:
            _high_streak = 0
        was_wedged = _wedged
        _wedged = _high_streak >= LOOP_LAG_WEDGED_STREAK
        if lag_sec > _WARN_THRESHOLD_SEC:
            logger.warning(
                "event loop lag %.0fms (sample #%d wedged=%s streak=%d)",
                _last_lag_ms, _samples, _wedged, _high_streak,
            )
        if _wedged and not was_wedged:
            logger.error(
                "API_WEDGED: event loop lag streak %d >= %d (last=%.0fms)",
                _high_streak, LOOP_LAG_WEDGED_STREAK, _last_lag_ms,
            )
