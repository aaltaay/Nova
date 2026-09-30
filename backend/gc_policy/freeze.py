"""Freeze the heap once, a few minutes after the backend starts (#619).

Before freezing, one full collection clears what is already garbage, so only live objects are
frozen. A frozen object is still freed when nothing refers to it; only one that later dies inside
a reference cycle is never reclaimed -- bounded, because this runs once per process.
``NOVA_GC_FREEZE=0`` turns it off.
"""
from __future__ import annotations

import asyncio
import gc
import logging
import os
import time
from typing import Any

from constants_perf import GC_FREEZE_AFTER_SEC, GC_FREEZE_ENV

logger = logging.getLogger(__name__)


def enabled() -> bool:
    return os.environ.get(GC_FREEZE_ENV, "1").strip().lower() not in ("0", "false", "off", "no")


def freeze_now() -> dict[str, Any]:
    """Collect what is garbage now, then move every live tracked object to the permanent generation."""
    started = time.perf_counter()
    collected = gc.collect()
    gc.freeze()
    out = {"frozen": gc.get_freeze_count(), "collected": collected,
           "ms": round((time.perf_counter() - started) * 1e3, 1)}
    logger.info("gc policy: froze %d long-lived objects (collected %d first, %.0f ms)",
                out["frozen"], out["collected"], out["ms"])
    return out


async def freeze_after_startup(delay_sec: float = GC_FREEZE_AFTER_SEC) -> None:
    """A runtime task: wait for startup's lazy imports and first loads, then freeze once."""
    if not enabled():
        logger.info("gc policy: freeze off (%s=0)", GC_FREEZE_ENV)
        return
    await asyncio.sleep(delay_sec)
    try:
        freeze_now()
    except Exception:
        logger.exception("gc policy: freeze failed")
