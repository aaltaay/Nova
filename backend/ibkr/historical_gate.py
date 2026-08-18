"""Compat shim -- historicals no longer take the cold slot (ADR 012).

``historical_slot`` still maps onto ``cold_slot`` for tests that assert
preemption. Production chart/surge/setups paths use ``historical_service``.
``interactive_busy`` is true when either a cold interactive holder or an
open-chart historical fill is in flight.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from ibkr.ib_scheduler import ColdDropped, cold_slot
from ibkr.ib_scheduler import interactive_busy as _cold_interactive

HistoricalBusy = ColdDropped


def interactive_busy() -> bool:
    from ibkr.historical_service import open_chart_busy

    return _cold_interactive() or open_chart_busy()


@asynccontextmanager
async def historical_slot(*, interactive: bool = False) -> AsyncIterator[None]:
    async with cold_slot(
        label="historical",
        interactive=interactive,
        droppable=not interactive,
    ):
        yield


__all__ = ["HistoricalBusy", "historical_slot", "interactive_busy"]
