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

from constants import LOOP_LAG_SAMPLE_INTERVAL_SEC

logger = logging.getLogger(__name__)

# Any single sample lagging this far past its expected wakeup logs a warning
# (a genuinely idle loop lags by ~0ms; this only fires under real contention).
_WARN_THRESHOLD_SEC = 1.0

_last_lag_ms: float = 0.0
_max_lag_ms: float = 0.0
_samples: int = 0


def snapshot() -> dict[str, float | int]:
    return {
        "last_ms": round(_last_lag_ms, 1),
        "max_ms": round(_max_lag_ms, 1),
        "samples": _samples,
    }


def reset_for_testing() -> None:
    global _last_lag_ms, _max_lag_ms, _samples
    _last_lag_ms = 0.0
    _max_lag_ms = 0.0
    _samples = 0


async def sample_loop_lag_loop() -> None:
    """Background task: sleep a fixed interval, record how much longer it
    actually took. Runs until cancelled at shutdown."""
    global _last_lag_ms, _max_lag_ms, _samples
    loop = asyncio.get_running_loop()
    while True:
        expected = loop.time() + LOOP_LAG_SAMPLE_INTERVAL_SEC
        await asyncio.sleep(LOOP_LAG_SAMPLE_INTERVAL_SEC)
        lag_sec = max(0.0, loop.time() - expected)
        _last_lag_ms = lag_sec * 1000.0
        _max_lag_ms = max(_max_lag_ms, _last_lag_ms)
        _samples += 1
        if lag_sec > _WARN_THRESHOLD_SEC:
            logger.warning("event loop lag %.0fms (sample #%d)", _last_lag_ms, _samples)
