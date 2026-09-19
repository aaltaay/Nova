"""ibkr/ib_await.py -- a stale ib_async single-flight cancel must not leak
into the caller's task (PROBLEM_LOG 2026-09-19)."""
from __future__ import annotations

import asyncio

import pytest
from ib_async import IB

from ibkr.errors import StaleIbRequestError
from ibkr.ib_await import await_ib_request


def test_passes_result_through():
    async def run():
        fut = asyncio.get_running_loop().create_future()
        fut.set_result(["trade"])
        return await await_ib_request(fut, timeout=1.0)

    assert asyncio.run(run()) == ["trade"]


def test_timeout_still_raises_timeout_error():
    async def run():
        await await_ib_request(asyncio.sleep(30), timeout=0.01)

    with pytest.raises(TimeoutError):
        asyncio.run(run())


def test_real_ib_async_stale_singleton_becomes_stale_error():
    """Exact shape from the 2026-09-19 log: connectAsync's completed-orders
    sync timed out, then Nova's warm-up asked again on the same IB."""

    async def run():
        ib = IB()
        sent: list[bool] = []
        ib.client.reqCompletedOrders = lambda api_only: sent.append(api_only)
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(ib.reqCompletedOrdersAsync(False), 0.01)
        with pytest.raises(StaleIbRequestError):
            await await_ib_request(ib.reqCompletedOrdersAsync(False), timeout=1.0)
        # ib_async attached to the dead future instead of re-sending.
        assert sent == [False]

    asyncio.run(run())


def test_real_cancel_of_the_calling_task_still_propagates():
    async def run():
        task = asyncio.create_task(await_ib_request(asyncio.sleep(30), timeout=10.0))
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(run())
