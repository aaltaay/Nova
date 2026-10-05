"""IBKR's callbacks (the IB loop) wake an order's waiter (the socket loop) at once and safely (#725)."""
from __future__ import annotations

import asyncio
import threading
import time

from execution.order_watch import OrderWatch, _Flag


def _watch() -> OrderWatch:
    return OrderWatch(101, None, aggregate_eligible=False)   # nothing persisted


def test_an_ack_from_another_thread_wakes_the_waiter_at_once():
    """``asyncio.Event`` set from the IB thread neither was thread-safe nor woke the waiting loop: the
    reply waited for some other wake-up. Debug mode raises on such a set; this one wakes at once."""
    watch = _watch()

    async def run() -> tuple[bool, float]:
        threading.Timer(0.05, lambda: watch.note_status("Submitted")).start()
        began = time.monotonic()
        acked = await watch.wait_ack(5.0)
        return acked, time.monotonic() - began

    acked, waited = asyncio.run(run(), debug=True)
    assert acked is True
    assert waited < 1.0
    assert watch.ack_status == "Submitted"


def test_a_fill_from_another_thread_wakes_its_waiter():
    watch = _watch()

    async def run() -> bool:
        threading.Timer(0.05, watch.note_filled).start()
        return await watch.wait_fill(5.0)

    assert asyncio.run(run(), debug=True) is True


def test_a_set_before_the_wait_is_never_lost():
    flag = _Flag()
    flag.set()
    assert asyncio.run(asyncio.wait_for(flag.wait(), 1.0)) is True


def test_waiters_on_two_loops_both_wake():
    """The cancel verify waits on the IB loop and the ack on the socket loop: one flag serves both."""
    flag = _Flag()
    woke: list[str] = []

    def other_loop() -> None:
        async def wait() -> None:
            await asyncio.wait_for(flag.wait(), 2.0)
            woke.append("other")

        asyncio.run(wait())

    thread = threading.Thread(target=other_loop)
    thread.start()

    async def run() -> None:
        threading.Timer(0.1, flag.set).start()
        await asyncio.wait_for(flag.wait(), 2.0)
        woke.append("main")

    asyncio.run(run(), debug=True)
    thread.join(3.0)
    assert sorted(woke) == ["main", "other"]


def test_a_waiter_that_timed_out_does_not_break_a_later_set():
    flag = _Flag()

    async def run() -> bool:
        try:
            await asyncio.wait_for(flag.wait(), 0.05)
        except asyncio.TimeoutError:
            pass
        flag.set()
        return await asyncio.wait_for(flag.wait(), 1.0)

    assert asyncio.run(run()) is True
