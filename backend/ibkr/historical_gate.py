"""Serialize IBKR historical-bar requests; prefer the open chart over background scans.

IB Gateway pacing + a single API socket means concurrent ``reqHistoricalData``
calls queue and time out. The setups_stream loop was issuing ~15 fetches every
15s, starving the interactive ticker chart (UI stuck on Loading for 30s+).

Rules:
- Only one historical fetch runs at a time (asyncio.Lock on the IB event loop).
- Interactive (chart) callers bump a depth counter so background work skips
  while a chart request is in flight or waiting.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator

_lock = asyncio.Lock()
_interactive_depth = 0


class HistoricalBusy(Exception):
    """Background fetch aborted because an interactive chart request needs the slot."""


def interactive_busy() -> bool:
    return _interactive_depth > 0


@asynccontextmanager
async def historical_slot(*, interactive: bool = False) -> AsyncIterator[None]:
    global _interactive_depth
    if interactive:
        _interactive_depth += 1
    try:
        if not interactive:
            if _interactive_depth > 0:
                raise HistoricalBusy("interactive chart has priority")
        await _lock.acquire()
        try:
            if not interactive and _interactive_depth > 0:
                raise HistoricalBusy("interactive chart has priority")
            yield
        finally:
            _lock.release()
    finally:
        if interactive:
            _interactive_depth = max(0, _interactive_depth - 1)
