"""Unit tests for IBKR historical request gate (chart priority over setups)."""
from __future__ import annotations

import asyncio

import pytest

from ibkr.historical_gate import HistoricalBusy, historical_slot, interactive_busy


def test_background_skips_when_interactive_waiting():
    async def _run():
        entered = asyncio.Event()
        release = asyncio.Event()

        async def chart_hold():
            async with historical_slot(interactive=True):
                entered.set()
                await release.wait()

        async def background_try():
            await entered.wait()
            with pytest.raises(HistoricalBusy):
                async with historical_slot(interactive=False):
                    pass

        t1 = asyncio.create_task(chart_hold())
        t2 = asyncio.create_task(background_try())
        await asyncio.wait_for(t2, timeout=2.0)
        assert interactive_busy()
        release.set()
        await t1
        assert not interactive_busy()

    asyncio.run(_run())


def test_serializes_concurrent_slots():
    async def _run():
        order: list[str] = []

        async def work(name: str):
            async with historical_slot(interactive=False):
                order.append(f"{name}-start")
                await asyncio.sleep(0.05)
                order.append(f"{name}-end")

        await asyncio.gather(work("a"), work("b"))
        assert order in (
            ["a-start", "a-end", "b-start", "b-end"],
            ["b-start", "b-end", "a-start", "a-end"],
        )

    asyncio.run(_run())
