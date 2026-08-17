"""One IB-loop cold scheduler (ADR 010).

Replaces historical_gate + discovery._snapshot_lock + completed-orders lock.
Interactive chart preempts droppable cold work. In-flight work finishes
(one request); queued droppable jobs raise ColdDropped.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator

from ibkr.loop_supervisor import assert_ib_loop

_lock: asyncio.Lock | None = None
_interactive_depth = 0
_inflight_label = ""


class ColdDropped(Exception):
    """Droppable cold work aborted because interactive/hot needs the slot."""


def _get_lock() -> asyncio.Lock:
    global _lock
    if _lock is None:
        _lock = asyncio.Lock()
    return _lock


def interactive_busy() -> bool:
    return _interactive_depth > 0


def inflight_label() -> str:
    return _inflight_label


def reset_for_testing() -> None:
    global _lock, _interactive_depth, _inflight_label
    _lock = None
    _interactive_depth = 0
    _inflight_label = ""


@asynccontextmanager
async def cold_slot(
    *,
    label: str,
    interactive: bool = False,
    droppable: bool = True,
) -> AsyncIterator[None]:
    """Single-flight IB cold slot. Must be awaited on the IB loop once started."""
    global _interactive_depth, _inflight_label
    assert_ib_loop()
    if interactive:
        _interactive_depth += 1
    try:
        if not interactive and droppable and _interactive_depth > 0:
            raise ColdDropped("interactive chart has priority")
        lock = _get_lock()
        await lock.acquire()
        try:
            if not interactive and droppable and _interactive_depth > 0:
                raise ColdDropped("interactive chart has priority")
            _inflight_label = label
            yield
        finally:
            _inflight_label = ""
            lock.release()
    finally:
        if interactive:
            _interactive_depth = max(0, _interactive_depth - 1)
