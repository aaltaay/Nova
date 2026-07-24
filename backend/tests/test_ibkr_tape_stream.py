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
    monkeypatch.setitem(tape._queues, "CNEY", q)
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
    monkeypatch.setitem(tape._queues, "MVO", q)
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
    monkeypatch.setitem(tape._queues, "CNEY", q)
    monkeypatch.setitem(tape._contracts, "CNEY", SimpleNamespace(conId=42))

    tape._on_ib_error(1, 10089, "Requires additional subscription", SimpleNamespace(conId=42))

    err = q.get_nowait()
    assert err["type"] == "error"
    assert "subscription" in err["message"].lower()


def test_push_queue_drops_oldest_when_full(monkeypatch):
    q: asyncio.Queue = asyncio.Queue(maxsize=1)
    monkeypatch.setitem(tape._queues, "ABC", q)
    q.put_nowait({"type": "print", "symbol": "ABC", "price": 1.0})

    tape._push_queue("ABC", {"type": "print", "symbol": "ABC", "price": 2.0})

    assert q.qsize() == 1
    latest = q.get_nowait()
    assert latest["price"] == 2.0


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
    tape._contracts.clear()
    tape._tickers.clear()
    tape._queues.clear()
    tape._error_hooked_ib_ids.clear()
    tape._cancelled_at.clear()
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

    tape._contracts.clear()
    tape._tickers.clear()
    tape._queues.clear()
    tape._error_hooked_ib_ids.clear()
    tape._cancelled_at.clear()
    op_metrics.reset_for_tests()
    monkeypatch.setattr(tape._client, "get_ib", lambda: _IB())
    monkeypatch.setattr(tape, "_load_ib_types", lambda: True)
    monkeypatch.setattr(tape, "_Stock", _Stock)

    result = asyncio.run(tape.subscribe_async("AAPL"))

    assert result["ok"] is False
    assert op_metrics.snapshot()["operations"]["ibkr.tape.subscribe"]["error_count"] == 1
