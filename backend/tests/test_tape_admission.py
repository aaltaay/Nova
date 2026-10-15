"""Shared AllLast admission against a disconnected fake Gateway (#674)."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from ibkr import client, tape_line, tape_stream as tape


class Event:
    def __init__(self):
        self.handlers = []

    def __iadd__(self, fn):
        self.handlers.append(fn)
        return self

    def __isub__(self, fn):
        self.handlers.remove(fn)
        return self


class Gateway:
    def __init__(self):
        self.errorEvent = Event()
        self.requests = []
        self.cancels = []
        self.registry = {}
        self.wrapper = SimpleNamespace(subscriptions=SimpleNamespace(
            find_market_data=lambda con_id, kind: self.registry.get(con_id)))
        self.generation = 1
        self.qualifying = None
        self.resume = None
        self.cancel_error = False

    async def qualifyContractsAsync(self, contract):
        if self.qualifying is not None:
            self.qualifying.set()
            await self.resume.wait()
        contract.conId = sum(map(ord, contract.symbol))
        return [contract]

    def reqTickByTickData(self, contract, *args, **kwargs):
        self.requests.append(contract.symbol)
        self.registry[contract.conId] = SimpleNamespace(reqId=len(self.requests))
        return SimpleNamespace(updateEvent=Event(), tickByTicks=[])

    def cancelTickByTickData(self, contract, kind):
        self.cancels.append(contract.symbol)
        if self.cancel_error:
            raise RuntimeError("cancel send failed")
        self.registry.pop(contract.conId, None)


@pytest.fixture
def gateway(monkeypatch):
    fake = Gateway()
    tape.reset_for_tests()
    monkeypatch.setenv("IBKR_TAPE_MAX_LINES", "2")
    monkeypatch.setattr(client, "get_ib", lambda: fake)
    monkeypatch.setattr(client, "current_generation", lambda: fake.generation)
    monkeypatch.setattr(tape, "_load_ib_types", lambda: True)
    monkeypatch.setattr(tape, "_Stock", lambda sym, *_: SimpleNamespace(symbol=sym, conId=0))
    monkeypatch.setattr(tape, "_warm_10sec_fill", lambda _: None)
    yield fake
    tape.reset_for_tests()


def run(coro):
    return asyncio.run(coro)


def capacity():
    from ibkr import tape_admission

    return tape_admission.view()


def test_full_tape_with_free_depth_and_record_slots(gateway, monkeypatch):
    from leaderboard import auto_record

    monkeypatch.setattr(auto_record, "_busy_lines", lambda: [])
    monkeypatch.setattr(auto_record, "_recording", lambda: [])
    monkeypatch.setattr(auto_record, "_resuming", lambda: [])
    auto_record.reset_for_tests()
    run(tape.subscribe_async("AAA"))
    run(tape.subscribe_async("BBB"))
    assert auto_record.free_lines() == 0
    assert auto_record.free_lines(symbol="AAA") > 0
    refused = run(tape.subscribe_async("CCC", automatic=True))
    assert not refused["ok"] and "capacity" in refused["error"].lower()
    assert gateway.requests == ["AAA", "BBB"]
    assert run(tape.subscribe_async("AAA", automatic=True))["ok"]
    assert capacity()["used"] == 2


def test_pending_requests_reserve_atomically_and_same_symbol_reuses(gateway, monkeypatch):
    monkeypatch.setenv("IBKR_TAPE_MAX_LINES", "1")

    async def scenario():
        gateway.qualifying, gateway.resume = asyncio.Event(), asyncio.Event()
        first = asyncio.create_task(tape.subscribe_async("AAA", automatic=True))
        await gateway.qualifying.wait()
        assert capacity()["pending"] == ["AAA"]
        duplicate = asyncio.create_task(tape.subscribe_async("AAA", automatic=True))
        other = await tape.subscribe_async("BBB", automatic=True)
        assert not other["ok"]
        gateway.resume.set()
        assert all(r["ok"] for r in await asyncio.gather(first, duplicate))

    run(scenario())
    assert gateway.requests == ["AAA"]


def test_delayed_refusal_learns_ceiling_before_http_cleanup(gateway, monkeypatch):
    from ibkr import tape_line

    monkeypatch.delenv("IBKR_TAPE_MAX_LINES")
    callbacks = []
    monkeypatch.setattr(tape_line, "_on_http_loop", lambda fn, *args: callbacks.append(lambda: fn(*args)))
    for sym in ("AAA", "BBB", "CCC", "DDD"):
        run(tape.subscribe_async(sym))
    tape._on_ib_error(3, 10190, "Max number of tick-by-tick requests has been reached")
    assert capacity()["limit"] == 2  # not the fourth request sent after this refused request
    assert capacity()["source"] == "refusal"
    assert not run(tape.subscribe_async("EEE", automatic=True))["ok"]
    for callback in callbacks:
        callback()
    assert not tape.is_subscribed("CCC")
    assert tape.is_subscribed("DDD")


def test_cancel_dispatch_releases_local_budget_and_guard_still_applies(gateway, monkeypatch):
    monkeypatch.setenv("IBKR_TAPE_MAX_LINES", "1")
    run(tape.subscribe_async("AAA", automatic=True))
    tape_line.drop_line("AAA", "finished")
    assert capacity()["used"] == 0
    assert tape.guard_remaining("AAA") > 0
    assert not run(tape.subscribe_async("AAA", automatic=True))["ok"]
    assert run(tape.subscribe_async("BBB", automatic=True))["ok"]


def test_failed_cancel_remains_uncertain_until_session_reset(gateway, monkeypatch):
    monkeypatch.setenv("IBKR_TAPE_MAX_LINES", "1")
    run(tape.subscribe_async("AAA"))
    gateway.cancel_error = True
    tape_line.drop_line("AAA", "finished")
    assert capacity()["uncertain"] == ["AAA"]
    assert not run(tape.subscribe_async("BBB", automatic=True))["ok"]
    gateway.generation += 1
    gateway.registry.clear()
    assert run(tape.subscribe_async("BBB", automatic=True))["ok"]


def test_cancelled_qualification_returns_reservation(gateway, monkeypatch):
    monkeypatch.setenv("IBKR_TAPE_MAX_LINES", "1")

    async def scenario():
        gateway.qualifying, gateway.resume = asyncio.Event(), asyncio.Event()
        task = asyncio.create_task(tape.subscribe_async("AAA", automatic=True))
        await gateway.qualifying.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert capacity()["used"] == 0
        gateway.resume.set()
        assert (await tape.subscribe_async("BBB", automatic=True))["ok"]

    run(scenario())


def test_old_qualification_cannot_request_on_replacement_generation(gateway):
    async def scenario():
        gateway.qualifying, gateway.resume = asyncio.Event(), asyncio.Event()
        task = asyncio.create_task(tape.subscribe_async("AAA", automatic=True))
        await gateway.qualifying.wait()
        gateway.generation += 1
        gateway.qualifying = None
        assert (await tape.subscribe_async("BBB", automatic=True))["ok"]
        gateway.resume.set()
        assert not (await task)["ok"]
        assert gateway.requests == ["BBB"]
        assert capacity()["used"] == 1

    run(scenario())


def test_operator_can_request_when_auto_budget_full(gateway, monkeypatch):
    monkeypatch.setenv("IBKR_TAPE_MAX_LINES", "1")
    run(tape.subscribe_async("AAA", automatic=True))
    assert run(tape.subscribe_async("OPERATOR"))["ok"]
    assert not run(tape.subscribe_async("BBB", automatic=True))["ok"]


def test_invalid_configuration_is_a_loud_auto_admission_failure(gateway, monkeypatch):
    monkeypatch.setenv("IBKR_TAPE_MAX_LINES", "bogus")
    result = run(tape.subscribe_async("AAA", automatic=True))
    assert not result["ok"] and "IBKR_TAPE_MAX_LINES" in result["error"]
    assert gateway.requests == []


@pytest.mark.parametrize("failure", ["exception", "empty", "request"])
def test_failed_start_returns_its_reservation(gateway, monkeypatch, failure):
    monkeypatch.setenv("IBKR_TAPE_MAX_LINES", "1")

    async def qualify(contract):
        if failure == "exception":
            raise RuntimeError("qualification failed")
        return []

    if failure == "request":
        def request(*args, **kwargs):
            raise RuntimeError("request send failed")
        monkeypatch.setattr(gateway, "reqTickByTickData", request)
    else:
        monkeypatch.setattr(gateway, "qualifyContractsAsync", qualify)
    assert not run(tape.subscribe_async("AAA", automatic=True))["ok"]
    assert capacity()["used"] == 0


def test_queued_old_refusal_cannot_drop_a_new_generation_line(gateway, monkeypatch):
    callbacks = []
    monkeypatch.setattr(tape_line, "_on_http_loop", lambda fn, *args: callbacks.append(lambda: fn(*args)))
    run(tape.subscribe_async("AAA"))
    tape._on_ib_error(1, 10190, "capacity full")
    gateway.generation += 1
    gateway.registry.clear()
    assert run(tape.subscribe_async("AAA"))["ok"]
    for callback in callbacks:
        callback()
    assert tape.is_subscribed("AAA")
    assert capacity()["source"] == "configured"
    assert capacity()["used"] == 1


def test_generation_kept_lines_still_count(gateway, monkeypatch):
    from ibkr import line_session

    monkeypatch.setattr(line_session, "fate", lambda *args: line_session.KEPT)
    run(tape.subscribe_async("AAA"))
    run(tape.subscribe_async("BBB"))
    gateway.generation += 1
    assert not run(tape.subscribe_async("CCC", automatic=True))["ok"]
    assert capacity()["active"] == ["AAA", "BBB"]
    assert gateway.cancels == []
    tape._on_ib_error(2, 10190, "capacity full after connectivity restore")
    assert capacity()["limit"] == 1
    assert not tape.is_subscribed("BBB")


def test_unknown_budget_is_explicit_and_independent_of_depth(gateway, monkeypatch):
    monkeypatch.delenv("IBKR_TAPE_MAX_LINES")
    for sym in ("AAA", "BBB", "CCC", "DDD", "EEE", "FFF"):
        assert run(tape.subscribe_async(sym, automatic=True))["ok"]
    assert capacity()["limit"] is None
    assert capacity()["source"] == "unknown"
    assert capacity()["used"] == 6


def test_ready_gate_outage_does_not_forget_active_capacity(gateway, monkeypatch):
    run(tape.subscribe_async("AAA"))
    with monkeypatch.context() as outage:
        outage.setattr(client, "get_ib", lambda: None)
        assert capacity()["used"] == 1
        assert capacity()["active"] == ["AAA"]
    assert capacity()["used"] == 1


def test_linger_counts_until_cancel_dispatch(gateway, monkeypatch):
    monkeypatch.setenv("IBKR_TAPE_MAX_LINES", "1")
    monkeypatch.setattr(tape, "IBKR_TAPE_LINGER_SEC", 0)

    async def scenario():
        assert (await tape.subscribe_async("AAA"))["ok"]
        tape.unsubscribe("AAA")
        assert capacity()["used"] == 1
        assert not (await tape.subscribe_async("BBB", automatic=True))["ok"]
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert capacity()["used"] == 0
        assert (await tape.subscribe_async("BBB", automatic=True))["ok"]

    run(scenario())
