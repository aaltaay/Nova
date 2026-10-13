"""``ticks.unsubscribe`` runs on the IB loop whichever loop calls it (ADR 010).

On 2026-10-12 the Trader's ticker socket and the scanner's reconcile called it on
the HTTP loop. Whenever a subscribe held the lock on the IB loop it raised
"<asyncio.locks.Lock ...> is bound to a different event loop" before letting the
owner go, and the line stayed open until the backend restarted. When the lock was
free it sent ``cancelMktData`` from the HTTP thread instead.
"""
from __future__ import annotations

import asyncio
import threading

import pytest

from ibkr import loop_supervisor, ticks

_HOLD_SEC = 0.3


class _FakeIb:
    def __init__(self) -> None:
        self.cancels: list[tuple[object, bool]] = []

    def cancelMktData(self, contract) -> None:
        self.cancels.append((contract, loop_supervisor.is_ib_loop()))


@pytest.fixture
def ib_loop(monkeypatch):
    fake = _FakeIb()
    monkeypatch.setattr(ticks._client, "get_ib", lambda: fake)
    ticks._subs.clear()
    ticks._subscribe_lock = None
    loop_supervisor.start()
    try:
        yield fake
    finally:
        loop_supervisor.stop()
        ticks._subs.clear()
        ticks._subscribe_lock = None


def _open_line(symbol: str, owner: str = ticks.OWNER_DETAIL) -> object:
    contract = object()
    ticks._subs[symbol] = {
        "ticker": None, "contract": contract, "handler": None, "owners": {owner},
        "generic_ticks": "", "last_price": None, "last_update_ts": None,
    }
    return contract


def _hold_the_lock_on_ib() -> threading.Event:
    """A subscribe in flight on the IB loop: the lock held, a second subscribe waiting on it.

    The waiter binds the lock to the IB loop, as two subscribes queued there do on the desk.
    """
    held = threading.Event()

    async def _hold() -> None:
        lock = ticks._get_lock()
        await lock.acquire()

        async def _queued_subscribe() -> None:
            async with lock:
                pass

        waiter = asyncio.create_task(_queued_subscribe())
        await asyncio.sleep(0)
        held.set()
        await asyncio.sleep(_HOLD_SEC)
        lock.release()
        await waiter

    asyncio.run_coroutine_threadsafe(_hold(), loop_supervisor.get_loop())
    assert held.wait(2.0)
    return held


def test_unsubscribe_from_the_http_loop_waits_for_a_subscribe_holding_the_lock(ib_loop) -> None:
    contract = _open_line("SUNE")
    _hold_the_lock_on_ib()

    asyncio.run(ticks.unsubscribe("SUNE"))

    assert "SUNE" not in ticks._subs
    assert ib_loop.cancels == [(contract, True)]


def test_unsubscribe_from_the_http_loop_cancels_the_line_on_the_ib_loop(ib_loop) -> None:
    contract = _open_line("YMAT")

    asyncio.run(ticks.unsubscribe("YMAT"))

    assert "YMAT" not in ticks._subs
    assert ib_loop.cancels == [(contract, True)]


def test_a_caller_that_stops_waiting_never_abandons_the_release(ib_loop) -> None:
    contract = _open_line("FCHL")
    _hold_the_lock_on_ib()

    async def _caller_gives_up() -> None:
        task = asyncio.create_task(ticks.unsubscribe("FCHL"))
        await asyncio.sleep(_HOLD_SEC / 3)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(_caller_gives_up())

    async def _after_the_lock_frees() -> None:
        async with ticks._get_lock():
            pass

    asyncio.run_coroutine_threadsafe(_after_the_lock_frees(), loop_supervisor.get_loop()).result(2.0)
    assert "FCHL" not in ticks._subs
    assert ib_loop.cancels == [(contract, True)]


def test_an_owner_still_on_the_line_keeps_it_open(ib_loop) -> None:
    _open_line("GRML", ticks.OWNER_SCANNER)
    ticks._subs["GRML"]["owners"].add(ticks.OWNER_DETAIL)

    asyncio.run(ticks.unsubscribe("GRML"))

    assert ticks._subs["GRML"]["owners"] == {ticks.OWNER_SCANNER}
    assert ib_loop.cancels == []
