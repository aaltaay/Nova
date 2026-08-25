"""Unit tests for IBKR Time & Sales tape_stream helpers."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import ibkr.tape_stream as tape
from metrics import op_metrics


class _Event:
    def __init__(self):
        self.handlers = []

    def __iadd__(self, handler):
        self.handlers.append(handler)
        return self

    def __isub__(self, handler):
        self.handlers.remove(handler)
        return self


class _FakeTicker:
    def __init__(self, ticks):
        self.tickByTicks = list(ticks)
        self.updateEvent = _Event()


def test_on_tape_update_pushes_print_and_skips_nonpositive(monkeypatch):
    q: asyncio.Queue = asyncio.Queue()
    monkeypatch.setitem(tape._viewer_queues, "CNEY", [q])
    monkeypatch.setattr(
        tape._depth,
        "current_book",
        lambda _sym: {
            "bids": [{"price": 0.73, "size": 100}],
            "asks": [{"price": 0.75, "size": 100}],
        },
    )

    ticks = [
        SimpleNamespace(time=None, price=-1.0, size=0, exchange="", specialConditions=""),
        SimpleNamespace(time=None, price=0.74, size=100, exchange="ISLAND", specialConditions=""),
    ]
    tape._on_tape_update(_FakeTicker(ticks), "CNEY")

    assert q.qsize() == 1
    print_data = q.get_nowait()
    assert print_data["type"] == "print"
    assert print_data["symbol"] == "CNEY"
    assert print_data["price"] == 0.74
    assert print_data["size"] == 100
    assert print_data["exchange"] == "ISLAND"
    assert print_data["side"] == "between"
    assert print_data["bid"] == 0.73
    assert print_data["ask"] == 0.75


def test_on_tape_update_classifies_ask_hit(monkeypatch):
    q: asyncio.Queue = asyncio.Queue()
    monkeypatch.setitem(tape._viewer_queues, "MVO", [q])
    monkeypatch.setattr(
        tape._depth,
        "current_book",
        lambda _sym: {
            "bids": [{"price": 0.8428, "size": 100}],
            "asks": [{"price": 0.8488, "size": 100}],
        },
    )
    ticks = [
        SimpleNamespace(time=None, price=0.8488, size=50, exchange="ARCA", specialConditions=""),
    ]
    tape._on_tape_update(_FakeTicker(ticks), "MVO")
    print_data = q.get_nowait()
    assert print_data["side"] == "ask"


def test_on_ib_error_routes_to_matching_contract(monkeypatch):
    q: asyncio.Queue = asyncio.Queue()
    monkeypatch.setitem(tape._viewer_queues, "CNEY", [q])
    monkeypatch.setitem(tape._contracts, "CNEY", SimpleNamespace(conId=42))

    tape._on_ib_error(1, 10089, "Requires additional subscription", SimpleNamespace(conId=42))

    err = q.get_nowait()
    assert err["type"] == "error"
    assert "subscription" in err["message"].lower()


def test_push_queue_drops_oldest_when_full(monkeypatch):
    q: asyncio.Queue = asyncio.Queue(maxsize=1)
    monkeypatch.setitem(tape._viewer_queues, "ABC", [q])
    q.put_nowait({"type": "print", "symbol": "ABC", "price": 1.0})

    tape._push_queue("ABC", {"type": "print", "symbol": "ABC", "price": 2.0})

    assert q.qsize() == 1
    latest = q.get_nowait()
    assert latest["price"] == 2.0


def test_push_queue_broadcasts_to_every_viewer(monkeypatch):
    """2026-08-25: a single shared queue per symbol made two viewers
    competing consumers -- a live soak proved 1,902 archived prints
    delivered zero of them to the surviving viewer. Every registered
    viewer queue must get every print.
    """
    q1: asyncio.Queue = asyncio.Queue()
    q2: asyncio.Queue = asyncio.Queue()
    monkeypatch.setitem(tape._viewer_queues, "DAIC", [q1, q2])

    tape._push_queue("DAIC", {"type": "print", "symbol": "DAIC", "price": 5.5})

    assert q1.get_nowait()["price"] == 5.5
    assert q2.get_nowait()["price"] == 5.5


def test_subscribe_is_idempotent_and_measured_once(monkeypatch):
    class _IB:
        def __init__(self):
            self.errorEvent = _Event()
            self.requests = 0

        async def qualifyContractsAsync(self, contract):
            contract.conId = 42
            return [contract]

        def reqTickByTickData(self, *_args, **_kwargs):
            self.requests += 1
            return _FakeTicker([])

    class _Stock:
        def __init__(self, symbol, *_args):
            self.symbol = symbol
            self.conId = 0

    ib = _IB()
    tape.reset_for_tests()
    op_metrics.reset_for_tests()
    monkeypatch.setattr(tape._client, "get_ib", lambda: ib)
    monkeypatch.setattr(tape, "_load_ib_types", lambda: True)
    monkeypatch.setattr(tape, "_Stock", _Stock)

    first = asyncio.run(tape.subscribe_async("AAPL"))
    second = asyncio.run(tape.subscribe_async("AAPL"))

    assert first["ok"] is True and second["ok"] is True
    assert ib.requests == 1
    stats = op_metrics.snapshot()["operations"]["ibkr.tape.subscribe"]
    assert stats["count"] == 1
    assert stats["error_count"] == 0


def test_subscribe_request_failure_is_measured(monkeypatch):
    class _IB:
        def __init__(self):
            self.errorEvent = _Event()

        async def qualifyContractsAsync(self, contract):
            contract.conId = 42
            return [contract]

        def reqTickByTickData(self, *_args, **_kwargs):
            raise RuntimeError("subscription rejected")

    class _Stock:
        def __init__(self, symbol, *_args):
            self.symbol = symbol
            self.conId = 0

    tape.reset_for_tests()
    op_metrics.reset_for_tests()
    monkeypatch.setattr(tape._client, "get_ib", lambda: _IB())
    monkeypatch.setattr(tape, "_load_ib_types", lambda: True)
    monkeypatch.setattr(tape, "_Stock", _Stock)

    result = asyncio.run(tape.subscribe_async("AAPL"))

    assert result["ok"] is False
    assert op_metrics.snapshot()["operations"]["ibkr.tape.subscribe"]["error_count"] == 1


def test_unsubscribe_lingers_so_resubscribe_reuses_ticker(monkeypatch):
    class _IB:
        def __init__(self):
            self.errorEvent = _Event()
            self.requests = 0
            self.cancels = 0

        async def qualifyContractsAsync(self, contract):
            contract.conId = 42
            return [contract]

        def reqTickByTickData(self, *_args, **_kwargs):
            self.requests += 1
            return _FakeTicker([])

        def cancelTickByTickData(self, *_args, **_kwargs):
            self.cancels += 1

    class _Stock:
        def __init__(self, symbol, *_args):
            self.symbol = symbol
            self.conId = 0

    ib = _IB()
    tape.reset_for_tests()
    monkeypatch.setattr(tape._client, "get_ib", lambda: ib)
    monkeypatch.setattr(tape, "_load_ib_types", lambda: True)
    monkeypatch.setattr(tape, "_Stock", _Stock)
    monkeypatch.setattr(tape, "IBKR_TAPE_LINGER_SEC", 60.0)

    async def _run():
        first = await tape.subscribe_async("IPST")
        tape.unsubscribe("IPST")
        second = await tape.subscribe_async("IPST")
        still_live = "IPST" in tape._tickers
        tape.reset_for_tests()
        return first, second, still_live

    first, second, still_live = asyncio.run(_run())
    assert first["ok"] is True and second["ok"] is True
    assert ib.requests == 1
    assert ib.cancels == 0
    assert still_live is True


def test_linger_expires_then_cancels_ib(monkeypatch):
    class _IB:
        def __init__(self):
            self.errorEvent = _Event()
            self.cancels = 0

        async def qualifyContractsAsync(self, contract):
            contract.conId = 42
            return [contract]

        def reqTickByTickData(self, *_args, **_kwargs):
            return _FakeTicker([])

        def cancelTickByTickData(self, *_args, **_kwargs):
            self.cancels += 1

    class _Stock:
        def __init__(self, symbol, *_args):
            self.symbol = symbol
            self.conId = 0

    ib = _IB()
    tape.reset_for_tests()
    monkeypatch.setattr(tape._client, "get_ib", lambda: ib)
    monkeypatch.setattr(tape, "_load_ib_types", lambda: True)
    monkeypatch.setattr(tape, "_Stock", _Stock)
    monkeypatch.setattr(tape, "IBKR_TAPE_LINGER_SEC", 0.01)

    async def _run():
        await tape.subscribe_async("IPST")
        tape.unsubscribe("IPST")
        await asyncio.sleep(0.05)
        cancels = ib.cancels
        tape.reset_for_tests()
        return cancels

    assert asyncio.run(_run()) == 1


def test_linger_does_not_cancel_when_viewer_reattached(monkeypatch):
    """2026-08-25 DAIC/WVVIP freeze: a StrictMode double-mount schedules a
    linger from the discarded socket's cleanup; the surviving viewer's
    ws_viewer_opened() must stop that linger from cancelling a watched line.
    """
    class _IB:
        def __init__(self):
            self.errorEvent = _Event()
            self.cancels = 0

        async def qualifyContractsAsync(self, contract):
            contract.conId = 42
            return [contract]

        def reqTickByTickData(self, *_args, **_kwargs):
            return _FakeTicker([])

        def cancelTickByTickData(self, *_args, **_kwargs):
            self.cancels += 1

    class _Stock:
        def __init__(self, symbol, *_args):
            self.symbol = symbol
            self.conId = 0

    ib = _IB()
    tape.reset_for_tests()
    monkeypatch.setattr(tape._client, "get_ib", lambda: ib)
    monkeypatch.setattr(tape, "_load_ib_types", lambda: True)
    monkeypatch.setattr(tape, "_Stock", _Stock)
    monkeypatch.setattr(tape, "IBKR_TAPE_LINGER_SEC", 0.01)

    async def _run():
        await tape.subscribe_async("DAIC")
        # First viewer's cleanup schedules the linger (discarded socket).
        tape.unsubscribe("DAIC")
        # Second viewer reattaches before the linger fires.
        tape.ws_viewer_opened("DAIC")
        await asyncio.sleep(0.05)
        cancels = ib.cancels
        still_live = "DAIC" in tape._tickers
        subscribed = tape.is_subscribed("DAIC")
        tape.reset_for_tests()
        return cancels, still_live, subscribed

    cancels, still_live, subscribed = asyncio.run(_run())
    assert cancels == 0
    assert still_live is True
    assert subscribed is True


def test_concurrent_subscribe_creates_one_ticker_and_one_handler(monkeypatch):
    """Two callers racing subscribe_async for the same symbol (StrictMode
    double-mount) must not both send reqTickByTickData / attach a handler.
    """
    class _IB:
        def __init__(self):
            self.errorEvent = _Event()
            self.requests = 0

        async def qualifyContractsAsync(self, contract):
            await asyncio.sleep(0.02)  # widen the race window
            contract.conId = 42
            return [contract]

        def reqTickByTickData(self, *_args, **_kwargs):
            self.requests += 1
            return _FakeTicker([])

    class _Stock:
        def __init__(self, symbol, *_args):
            self.symbol = symbol
            self.conId = 0

    ib = _IB()
    tape.reset_for_tests()
    monkeypatch.setattr(tape._client, "get_ib", lambda: ib)
    monkeypatch.setattr(tape, "_load_ib_types", lambda: True)
    monkeypatch.setattr(tape, "_Stock", _Stock)

    async def _run():
        first, second = await asyncio.gather(
            tape.subscribe_async("WVVIP"), tape.subscribe_async("WVVIP")
        )
        tickers = dict(tape._tickers)
        tape.reset_for_tests()
        return first, second, tickers

    first, second, tickers = asyncio.run(_run())
    assert first["ok"] is True and second["ok"] is True
    assert ib.requests == 1
    assert list(tickers.keys()) == ["WVVIP"]


def test_released_line_broadcasts_error_to_open_viewer_queue(monkeypatch):
    """A released line must notify every open viewer instead of silently
    orphaning them behind a stale "LIVE" badge (PROBLEM_LOG 2026-08-25).
    """
    class _IB:
        def __init__(self):
            self.errorEvent = _Event()

        async def qualifyContractsAsync(self, contract):
            contract.conId = 42
            return [contract]

        def reqTickByTickData(self, *_args, **_kwargs):
            return _FakeTicker([])

        def cancelTickByTickData(self, *_args, **_kwargs):
            pass

    class _Stock:
        def __init__(self, symbol, *_args):
            self.symbol = symbol
            self.conId = 0

    ib = _IB()
    tape.reset_for_tests()
    monkeypatch.setattr(tape._client, "get_ib", lambda: ib)
    monkeypatch.setattr(tape, "_load_ib_types", lambda: True)
    monkeypatch.setattr(tape, "_Stock", _Stock)

    async def _run():
        await tape.subscribe_async("DAIC")
        queue = tape.open_viewer_queue("DAIC")
        tape._release_subscription("DAIC")
        released = await asyncio.wait_for(queue.get(), timeout=1.0)
        tape.reset_for_tests()
        return released

    released = asyncio.run(_run())
    assert released["type"] == "error"
    assert released["released"] is True


def test_two_viewer_queues_of_same_symbol_both_get_every_print(monkeypatch):
    """The actual production bug: a live soak against the running API
    proved that with a single shared queue, a second viewer of a symbol
    already being watched received zero of 1,902 archived prints.
    """
    tape.reset_for_tests()
    q1 = tape.open_viewer_queue("DAIC")
    q2 = tape.open_viewer_queue("DAIC")

    tape._on_tape_update(
        _FakeTicker(
            [SimpleNamespace(time=None, price=5.58, size=100, exchange="ARCA", specialConditions="")]
        ),
        "DAIC",
    )

    assert q1.get_nowait()["price"] == 5.58
    assert q2.get_nowait()["price"] == 5.58
    tape.reset_for_tests()
