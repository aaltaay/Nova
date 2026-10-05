"""An order send crosses to the IB loop awaited, and goes out once or provably never (#725)."""
from __future__ import annotations

import asyncio
import threading
import time

import pytest

from ibkr import loop_supervisor
from ibkr import send_hop


@pytest.fixture
def ib_loop():
    """A real IB loop thread, as the desk runs one (ADR 010)."""
    loop_supervisor.stop()
    loop = loop_supervisor.start()
    yield loop
    loop_supervisor.stop()


def _hold(loop, seconds: float) -> threading.Event:
    """Keep the IB loop busy for ``seconds`` (a burst of ticks, a slow handler); set the event to free it."""
    free = threading.Event()
    loop.call_soon_threadsafe(lambda: free.wait(seconds))
    return free


def test_the_caller_loop_keeps_running_while_the_ib_loop_is_busy(ib_loop):
    """The blocking hop held the socket loop -- every Level 2, Time & Sales and quote socket -- for as
    long as the IB loop was busy. Awaited, the socket loop keeps turning and the send still runs on
    the IB loop."""
    ran_on: list[str] = []

    async def run() -> tuple[str, int]:
        _hold(ib_loop, 0.3)
        ticks = 0

        async def other() -> None:
            nonlocal ticks
            while True:
                ticks += 1
                await asyncio.sleep(0.01)

        side = asyncio.create_task(other())
        result = await send_hop.send(
            lambda: ran_on.append(threading.current_thread().name) or "placed", label="test",
        )
        side.cancel()
        return result, ticks

    result, ticks = asyncio.run(run(), debug=True)
    assert result == "placed"
    assert ran_on == ["nova-ib-loop"]
    assert ticks >= 10          # about 30 turns of 10 ms while the IB loop was busy for 0.3 s


def test_a_send_the_ib_loop_did_not_start_in_time_is_never_sent(ib_loop):
    ran: list[bool] = []

    async def run() -> None:
        _hold(ib_loop, 0.6)
        with pytest.raises(send_hop.SendNotSent) as caught:
            await send_hop.send(lambda: ran.append(True), timeout=0.15, label="order")
        assert not isinstance(caught.value, send_hop.SendTooLate)
        await asyncio.sleep(0.8)  # the IB loop is free again: the abandoned send must not run now

    asyncio.run(run())
    assert ran == []


def test_a_desk_order_past_its_deadline_is_never_sent(ib_loop):
    """ADR 045: a desk order may not reach IBKR more than 750 ms after the click, however long the IB
    loop was busy. The caller stops waiting at the deadline, and the IB loop never starts it."""
    ran: list[bool] = []

    async def run() -> float:
        _hold(ib_loop, 0.5)
        began = time.monotonic()
        with pytest.raises(send_hop.SendTooLate):
            await send_hop.send(lambda: ran.append(True), not_after=time.time() + 0.1, timeout=5.0)
        waited = time.monotonic() - began
        await asyncio.sleep(0.7)
        return waited

    waited = asyncio.run(run())
    assert ran == []
    assert waited < 0.4         # the reply came at the deadline, not after the IB loop's 0.5 s


def test_a_send_already_running_is_awaited_never_reported_unsent(ib_loop):
    """``run_coro`` cancelled the hop on its timeout and reported a failure while a send the IB loop
    had started reached IBKR. A running send reached IBKR: its result is the answer."""
    release = threading.Event()

    def slow_place() -> str:
        release.wait(1.0)
        return "placed"

    async def run() -> str:
        threading.Timer(0.3, release.set).start()
        return await send_hop.send(slow_place, timeout=0.1, label="order")

    assert asyncio.run(run()) == "placed"


def test_the_ib_loop_declines_a_send_the_caller_gave_up_on_or_one_past_its_deadline():
    hop = send_hop._Hop()
    assert hop.give_up() is True
    assert hop.start(None, time.time()) is False         # abandoned: never starts

    late = send_hop._Hop()
    now = time.time()
    assert late.start(now - 0.2, now) is False
    assert late.late_ms == pytest.approx(200.0, abs=1.0)
    assert late.give_up() is False                         # already settled

    running = send_hop._Hop()
    assert running.start(None, time.time()) is True
    assert running.give_up() is False                      # it reached IBKR: the caller cannot unsend it


def test_without_an_ib_loop_the_send_runs_inline_and_the_deadline_still_holds():
    loop_supervisor.stop()
    assert asyncio.run(send_hop.send(lambda: 7)) == 7
    ran: list[bool] = []
    with pytest.raises(send_hop.SendTooLate):
        asyncio.run(send_hop.send(lambda: ran.append(True), not_after=time.time() - 1.0))
    assert ran == []


def test_the_sends_own_error_reaches_the_caller(ib_loop):
    def broken() -> None:
        raise ValueError("bad contract")

    with pytest.raises(ValueError, match="bad contract"):
        asyncio.run(send_hop.send(broken))
