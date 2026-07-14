"""Unit tests for IBKR Time & Sales tape_stream helpers."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import ibkr.tape_stream as tape


class _FakeTicker:
    def __init__(self, ticks):
        self.tickByTicks = list(ticks)
        self.updateEvent = SimpleNamespace()


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
