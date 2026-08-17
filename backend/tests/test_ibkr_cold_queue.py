"""ADR 010 -- one cold scheduler; interactive preempts droppable work."""
from __future__ import annotations

import asyncio

import pytest

from ibkr.ib_scheduler import ColdDropped, cold_slot, inflight_label, reset_for_testing
from ibkr.work_class import WorkClass, classify


@pytest.fixture(autouse=True)
def _reset_scheduler():
    reset_for_testing()
    yield
    reset_for_testing()


def test_interactive_preempts_droppable_seeds() -> None:
    async def _run() -> None:
        entered = asyncio.Event()
        release = asyncio.Event()

        async def chart() -> None:
            async with cold_slot(label="historical", interactive=True, droppable=False):
                entered.set()
                await release.wait()

        async def seed() -> None:
            await entered.wait()
            with pytest.raises(ColdDropped):
                async with cold_slot(label="surge_seed", droppable=True):
                    pass

        t1 = asyncio.create_task(chart())
        t2 = asyncio.create_task(seed())
        await asyncio.wait_for(t2, timeout=2.0)
        release.set()
        await t1

    asyncio.run(_run())


def test_hot_labels_never_enter_scheduler_class() -> None:
    assert classify("placeOrder") is WorkClass.HOT
    assert classify("snapshot_quotes") is WorkClass.COLD


def test_inflight_label_set_during_slot() -> None:
    async def _run() -> None:
        async with cold_slot(label="snapshot_quotes", droppable=True):
            assert inflight_label() == "snapshot_quotes"
        assert inflight_label() == ""

    asyncio.run(_run())
