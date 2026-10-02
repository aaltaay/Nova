"""A trigger wakes the bot and the stock-mode runner at once, never at the next poll.

TNMG 2026-10-02: the red to green triggered at 09:47:18.228 ET and Nova's bot sent its
entry at 18.644 -- 416 ms spent waiting for the runner's next 0.5 s tick.
"""
from __future__ import annotations

import asyncio
import threading
import time
from collections import deque

from bot.wake import Wake


def test_unbound_set_is_a_no_op_and_sleep_sleeps():
    wake = Wake()
    wake.set()

    async def go() -> float:
        start = time.perf_counter()
        await wake.sleep(0.05)
        return time.perf_counter() - start

    assert asyncio.run(go()) >= 0.04


def test_a_ring_ends_the_sleep_at_once():
    async def go() -> float:
        wake = Wake()
        wake.bind()
        asyncio.get_running_loop().call_later(0.02, wake.set)
        start = time.perf_counter()
        await wake.sleep(5.0)
        return time.perf_counter() - start

    assert asyncio.run(go()) < 1.0


def test_a_ring_from_another_thread_ends_the_sleep():
    async def go() -> float:
        wake = Wake()
        wake.bind()
        threading.Timer(0.02, wake.set).start()
        start = time.perf_counter()
        await wake.sleep(5.0)
        return time.perf_counter() - start

    assert asyncio.run(go()) < 1.0


def test_a_ring_during_the_tick_ends_the_next_sleep_then_clears():
    async def go() -> tuple[float, float]:
        wake = Wake()
        wake.bind()
        wake.set()                            # the trigger landed while the loop was busy
        start = time.perf_counter()
        await wake.sleep(5.0)
        first = time.perf_counter() - start
        start = time.perf_counter()
        await wake.sleep(0.05)                # nothing rang since: a full poll
        return first, time.perf_counter() - start

    first, second = asyncio.run(go())
    assert first < 0.5
    assert second >= 0.04


class _Engine:
    def __init__(self) -> None:
        self.listeners: list = []

    def add_trigger_listener(self, fn) -> None:
        self.listeners.append(fn)

    def remove_trigger_listener(self, fn) -> None:
        self.listeners.remove(fn)


def _ticks_after_trigger(monkeypatch, runner, poll_name: str) -> float:
    """Run ``runner.run`` with a 5 s poll; seconds from a trigger to the tick that drains it."""
    engine = _Engine()
    monkeypatch.setattr("setup_scanner.engine.get_engine", lambda: engine)
    monkeypatch.setattr("bot.activation.note_start", lambda: None)
    monkeypatch.setattr(runner, poll_name, 5.0)
    monkeypatch.setattr(runner, "_wake", Wake(), raising=False)
    monkeypatch.setattr(runner, "_inbox", deque(maxlen=50))
    drained: list[float] = []

    async def fake_tick(now: float | None = None) -> None:
        while runner._inbox:
            runner._inbox.popleft()
            drained.append(time.perf_counter())

    monkeypatch.setattr(runner, "tick", fake_tick)

    async def go() -> float:
        task = asyncio.create_task(runner.run())
        await asyncio.sleep(0.05)             # the first tick ran; the loop now sleeps its 5 s poll
        assert engine.listeners, "the runner listens to the scanner"
        sent = time.perf_counter()
        engine.listeners[0]({"symbol": "TNMG", "setup_id": "x"})
        for _ in range(100):
            if drained:
                break
            await asyncio.sleep(0.01)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        assert drained, "the trigger was never read"
        return drained[0] - sent

    return asyncio.run(go())


def test_the_bot_reads_a_trigger_at_once(monkeypatch):
    from bot.first_pullback import runner

    assert _ticks_after_trigger(monkeypatch, runner, "BOT_FP_POLL_SEC") < 0.5


def test_auto_entry_and_approve_read_a_trigger_at_once(monkeypatch):
    from stock_mode import runner

    assert _ticks_after_trigger(monkeypatch, runner, "STOCK_MODE_POLL_SEC") < 0.5
