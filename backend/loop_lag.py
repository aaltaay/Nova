"""Dual event-loop lag samplers (HTTP vs IB) -- ADR 010.

A busy loop delays every coroutine on that loop. HTTP and IB are separate
after isolation; ``/api/health`` reports both. Circuit-break ``run_coro``
keys off IB lag.
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

_WARN_THRESHOLD_SEC = 1.0


class LoopLagSampler:
    def __init__(self, name: str) -> None:
        self.name = name
        self.last_ms: float = 0.0
        self.max_ms: float = 0.0
        self.samples: int = 0
        self.high_streak: int = 0
        self.wedged: bool = False

    def snapshot(self) -> dict[str, float | int | bool]:
        return {
            "last_ms": round(self.last_ms, 1),
            "max_ms": round(self.max_ms, 1),
            "samples": self.samples,
            "wedged": self.wedged,
            "high_streak": self.high_streak,
        }

    def reset(self) -> None:
        self.last_ms = 0.0
        self.max_ms = 0.0
        self.samples = 0
        self.high_streak = 0
        self.wedged = False

    async def sample_loop(self) -> None:
        loop = asyncio.get_running_loop()
        while True:
            expected = loop.time() + LOOP_LAG_SAMPLE_INTERVAL_SEC
            await asyncio.sleep(LOOP_LAG_SAMPLE_INTERVAL_SEC)
            lag_sec = max(0.0, loop.time() - expected)
            self.last_ms = lag_sec * 1000.0
            self.max_ms = max(self.max_ms, self.last_ms)
            self.samples += 1
            if self.last_ms >= LOOP_LAG_WEDGED_MS:
                self.high_streak += 1
            else:
                self.high_streak = 0
            was_wedged = self.wedged
            self.wedged = self.high_streak >= LOOP_LAG_WEDGED_STREAK
            if lag_sec > _WARN_THRESHOLD_SEC:
                logger.warning(
                    "%s loop lag %.0fms (sample #%d wedged=%s streak=%d)",
                    self.name, self.last_ms, self.samples, self.wedged, self.high_streak,
                )
            if self.wedged and not was_wedged:
                logger.error(
                    "API_WEDGED: %s loop lag streak %d >= %d (last=%.0fms)",
                    self.name, self.high_streak, LOOP_LAG_WEDGED_STREAK, self.last_ms,
                )


http_lag = LoopLagSampler("http")
ib_lag = LoopLagSampler("ib")


def snapshot() -> dict[str, float | int | bool]:
    """Backward-compat: HTTP loop lag (``loop_lag_ms`` on /api/health)."""
    return http_lag.snapshot()


def is_wedged() -> bool:
    """Circuit-break SoT is the IB loop (ADR 010)."""
    return ib_lag.wedged


def reset_for_testing() -> None:
    http_lag.reset()
    ib_lag.reset()


async def sample_loop_lag_loop() -> None:
    """HTTP-loop sampler (uvicorn)."""
    await http_lag.sample_loop()


async def sample_ib_loop_lag_loop() -> None:
    """IB-loop sampler (supervisor thread)."""
    await ib_lag.sample_loop()
