"""A tape line's end is named and loud (#525).

ib_async 2.1.0 keeps a tick-by-tick subscription registered after IB errors on
it and hands the dead one back on the next request. So an error must name its
line by request id (it may carry no contract), end exactly that line, and cancel
it, so the next request is a real one.
"""
from __future__ import annotations

import asyncio
import logging
from types import SimpleNamespace

import pytest

import ibkr.tape_stream as tape
from capture import bridge_ibkr
from ibkr import tape_line


class _Event:
    def __init__(self):
        self.handlers = []

    def __iadd__(self, handler):
        self.handlers.append(handler)
        return self

    def __isub__(self, handler):
        self.handlers.remove(handler)
        return self


class _Registry:
    """ib_async's subscription registry, as far as tape_line reads it."""

    def __init__(self):
        self.subs: dict[tuple[int, str], SimpleNamespace] = {}

    def find_market_data(self, con_id, kind):
        return self.subs.get((con_id, kind))


class _IB:
    def __init__(self):
        self.errorEvent = _Event()
        self.wrapper = SimpleNamespace(subscriptions=_Registry())
        self.next_req = 77
        self.requests = 0
        self.cancels = 0

    async def qualifyContractsAsync(self, contract):
        contract.conId = 42
        return [contract]

    def reqTickByTickData(self, contract, tick_type, **_kwargs):
        # Like ib_async 2.1.0: a registered line is handed back, nothing is sent.
        key = (contract.conId, tick_type)
        if key not in self.wrapper.subscriptions.subs:
            self.requests += 1
            self.wrapper.subscriptions.subs[key] = SimpleNamespace(reqId=self.next_req)
            self.next_req += 1
        return SimpleNamespace(tickByTicks=[], updateEvent=_Event())

    def cancelTickByTickData(self, contract, tick_type):
        self.cancels += 1
        self.wrapper.subscriptions.subs.pop((contract.conId, tick_type), None)


class _Stock:
    def __init__(self, symbol, *_args):
        self.symbol = symbol
        self.conId = 0


@pytest.fixture
def ib(monkeypatch):
    fake = _IB()
    tape.reset_for_tests()
    monkeypatch.setattr(tape._client, "get_ib", lambda: fake)
    monkeypatch.setattr(tape, "_load_ib_types", lambda: True)
    monkeypatch.setattr(tape, "_Stock", _Stock)
    monkeypatch.setattr(tape, "_warm_10sec_fill", lambda _sym: None)
    yield fake
    tape.reset_for_tests()


def _open(symbol="IPDN"):
    result = asyncio.run(tape.subscribe_async(symbol))
    assert result["ok"] is True
    q: asyncio.Queue = asyncio.Queue()
    tape._viewer_queues.setdefault(symbol, []).append(q)
    return q


def test_an_error_with_no_contract_but_a_known_request_id_ends_that_line(ib, caplog):
    q = _open("IPDN")
    assert tape_line.line_req("IPDN") == 77
    with caplog.at_level(logging.WARNING):
        tape._on_ib_error(77, 10190, "Max number of tick-by-tick requests has been reached.", None)
    assert tape.is_subscribed("IPDN") is False          # the dead line is gone, so it can be asked for again
    assert ib.cancels == 1                               # and ib_async's registry lets go of it
    ended = tape_line.ended("IPDN")
    assert ended["code"] == 10190 and ended["req_id"] == 77
    assert "tick-by-tick" in q.get_nowait()["message"]
    loud = [r for r in caplog.records if r.levelno == logging.WARNING and "IPDN" in r.getMessage()]
    assert any("10190" in r.getMessage() for r in loud)
    health = bridge_ibkr.producer_health("IPDN")
    assert health["state"] == "disconnected" and health["ended"]["code"] == 10190
    assert "IBKR ended the AllLast line for IPDN" in health["error"]


def test_the_next_request_after_an_end_is_a_real_one(ib, monkeypatch):
    _open("IPDN")
    tape._on_ib_error(77, 10189, "Failed to request tick-by-tick data", None)
    monkeypatch.setattr(tape, "IBKR_TAPE_RESUBSCRIBE_GUARD_SEC", 0.0)
    assert asyncio.run(tape.subscribe_async("IPDN"))["ok"] is True
    assert ib.requests == 2                              # not ib_async's dead line handed back
    assert tape_line.line_req("IPDN") == 78 and tape_line.ended("IPDN") is None


def test_an_error_on_another_request_of_the_same_contract_is_not_the_tapes(ib):
    _open("IPDN")
    # A Level 1 line on the same contract (conId 42) answers 354 on its own request id.
    tape._on_ib_error(99, 354, "Requested market data is not subscribed", SimpleNamespace(conId=42))
    assert tape.is_subscribed("IPDN") is True and ib.cancels == 0
    assert tape_line.ended("IPDN") is None


def test_a_late_error_for_an_old_line_leaves_the_new_line_alone(ib, monkeypatch, caplog):
    _open("WHLR")
    tape.end_line("WHLR", "found silent", notify=False)
    monkeypatch.setattr(tape, "IBKR_TAPE_RESUBSCRIBE_GUARD_SEC", 0.0)
    asyncio.run(tape.subscribe_async("WHLR"))
    with caplog.at_level(logging.INFO):
        tape._on_ib_error(77, 300, "Can't find EId with tickerId:77", None)
    assert tape.is_subscribed("WHLR") is True and tape_line.line_req("WHLR") == 78
    assert any("ended AllLast line of WHLR" in r.getMessage() for r in caplog.records)


def test_a_request_id_from_an_earlier_connection_names_nothing(ib, monkeypatch):
    """Request ids restart with each connection: after a reconnect, 77 is somebody else's."""
    from ibkr import client

    monkeypatch.setattr(client, "current_generation", lambda: 1)
    _open("IPDN")
    monkeypatch.setattr(client, "current_generation", lambda: 2)
    tape._on_ib_error(77, 162, "Historical market data Service error message", None)
    assert tape.is_subscribed("IPDN") is True and tape_line.ended("IPDN") is None


def test_an_ib_notice_on_the_line_does_not_end_it(ib):
    _open("IPDN")
    tape._on_ib_error(77, 2104, "Market data farm connection is OK:usfarm", None)
    assert tape.is_subscribed("IPDN") is True and tape_line.ended("IPDN") is None


def test_cancelling_a_line_a_recording_uses_is_loud(ib, monkeypatch, caplog):
    from capture import mode

    _open("IPDN")
    monkeypatch.setattr(mode, "_symbols", ["IPDN"])
    with caplog.at_level(logging.WARNING):
        tape._release_subscription("IPDN")
    assert any("while it is recording" in r.getMessage() and r.levelno == logging.WARNING
               for r in caplog.records)


def test_guard_remaining_counts_from_the_cancel(ib):
    _open("IPDN")
    assert tape.guard_remaining("IPDN") == 0.0
    tape.end_line("IPDN", "found silent", notify=False)
    left = tape.guard_remaining("IPDN")
    assert 0 < left <= tape.IBKR_TAPE_RESUBSCRIBE_GUARD_SEC
