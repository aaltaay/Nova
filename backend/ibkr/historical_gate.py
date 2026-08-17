"""Serialize IBKR historical-bar requests; prefer the open chart over background.

ADR 010: this is a facade over ``ib_scheduler.cold_slot``. Do not add a
second lock beside the scheduler.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from ibkr.ib_scheduler import ColdDropped, cold_slot, interactive_busy

HistoricalBusy = ColdDropped


@asynccontextmanager
async def historical_slot(*, interactive: bool = False) -> AsyncIterator[None]:
    async with cold_slot(
        label="historical",
        interactive=interactive,
        droppable=not interactive,
    ):
        yield


__all__ = ["HistoricalBusy", "historical_slot", "interactive_busy"]
