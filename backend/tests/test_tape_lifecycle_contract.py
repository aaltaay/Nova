"""Recorded stall sequences through the pinned SDK, with all socket sends stubbed (#722, #922).

This harness establishes local ownership, decoder delivery and send outcomes. It contains no broker
capacity model and cannot establish upstream slot occupancy or that a re-ask cures an IBKR stall.
"""
from __future__ import annotations

import asyncio
import time

import pytest
from ib_async import IB, Stock

from ibkr import client, halt_status, stray_lines, tape_recording, tape_silence, tape_stream as tape
from line_lending import sockets, tape_heal


async def _until(test):
    async def wait():
        while not test():
            await asyncio.sleep(0.001)
    await asyncio.wait_for(wait(), timeout=2)


@pytest.fixture
def sdk(monkeypatch):
    ib = IB()
    clock = {"now": 1_791_900_000.0}
    requests, cancels = [], []
    sequence = iter(range(100, 1000))
    ib.client.getReqId = lambda: next(sequence)
    ib.client.reqTickByTickData = lambda req, *a: requests.append(req)
    ib.client.cancelTickByTickData = lambda req: cancels.append(req)

    async def qualify(contract):
        contract.conId = sum(map(ord, contract.symbol))
        return [contract]

    ib.qualifyContractsAsync = qualify
    tape.reset_for_tests()
    tape_heal.reset_for_tests()
    sockets.reset_for_tests()
    stray_lines.reset_for_tests()
    monkeypatch.setattr(time, "time", lambda: clock["now"])
    monkeypatch.setattr(client, "get_ib", lambda: ib)
    monkeypatch.setattr(client, "is_ready", lambda: True)
    monkeypatch.setattr(client, "current_generation", lambda: 1)
    monkeypatch.setattr(tape, "_load_ib_types", lambda: True)
    monkeypatch.setattr(tape, "_Stock", Stock)
    monkeypatch.setattr(tape, "_warm_10sec_fill", lambda sym: None)
    monkeypatch.setattr(tape_recording, "_last", {})
    monkeypatch.setattr(tape_recording, "_last_exchange", {})
    monkeypatch.setattr(tape_recording, "_since", {})
    monkeypatch.setattr(tape_recording, "_errors", {})
    monkeypatch.setattr(tape_silence, "l1_trade_at", lambda sym: clock["now"])
    monkeypatch.setattr(halt_status, "halted_now", lambda syms, now=None: {s: False for s in syms})
    monkeypatch.setattr(tape_heal, "LINE_LENDING_TAPE_HEAL_POLL_SEC", 0.001)
    from capture import feed_hold
    from ibkr import tape_recovery
    from sim import mode

    monkeypatch.setattr(mode, "is_replay_desk", lambda: False)
    monkeypatch.setattr(feed_hold, "held", lambda sym: None)
    monkeypatch.setattr(tape_recovery, "line_dead", lambda *a, **kw: None)
    monkeypatch.setattr(tape_silence, "_note", lambda *a: None)

    def received(ticker, sym):
        # Receipt bookkeeping only; sink fan-out has its own isolated regressions.
        if ticker.tickByTicks:
            tape_recording._last[sym] = clock["now"]
            tape_recording._last_exchange[sym] = clock["now"]
            ticker.tickByTicks.clear()

    monkeypatch.setattr(tape, "_on_tape_update", received)
    yield ib, clock, requests, cancels
    tape_heal.reset_for_tests()
    tape.reset_for_tests()
    sockets.reset_for_tests()
    stray_lines.reset_for_tests()


def _print(ib, req):
    ib.client.decoder.tickByTick(["99", str(req), "2", "1791900000", "6.20", "100", "0", "NASDAQ", ""])
    ticker = ib.wrapper.subscriptions.get_ticker(req)
    if ticker is not None:
        ticker.updateEvent.emit(ticker)


@pytest.mark.parametrize("target", ["SCNI", "VEEA"])
def test_registered_missing_trades_and_late_old_prints_never_imply_recovery(sdk, target):
    ib, clock, requests, cancels = sdk

    async def scenario():
        for sym in ("SAIQ", "VEEA"):
            assert (await tape.subscribe_async(sym))["ok"]
            _print(ib, requests[-1])
        assert (await tape.subscribe_async("SCNI"))["ok"]  # opened into the shared stall, never printed
        tape.ws_viewer_opened(target)
        sockets.opened(target, tab=True, front=True, now=clock["now"], kind=sockets.TAPE)
        queue1, queue2 = tape.open_viewer_queue(target), tape.open_viewer_queue(target)
        tape.ws_viewer_opened(target)
        old_req = ib.wrapper.subscriptions.find_market_data(tape._contracts[target].conId, "AllLast").reqId
        clock["now"] += 40
        reading = tape_silence.reading(target)
        assert tape.is_subscribed(target) and reading["state"] == "dead" and "SAIQ" in reading["pipeline"]
        tape_heal.line_down(target, silence=reading)
        await _until(lambda: tape_heal.silent_status(target)["state"] == "holding")
        assert len(requests) == 3 and cancels == []

        clock["now"] += 1
        _print(ib, requests[0])                         # sibling returns without any re-ask
        await _until(lambda: old_req in cancels)
        assert len(requests) == 3 and tape.viewer_count(target) == 2
        assert tape._viewer_queues[target] == [queue1, queue2]
        assert ib.wrapper.subscriptions.get_ticker(old_req) is None
        assert stray_lines.view()["cancellations"][-1]["cancel_sent"] is True
        # During the same-instrument guard, the line is temporarily unsubscribed, yet the outage
        # anchor and missing-trades order gate stay in force.
        assert not tape.is_subscribed(target)
        assert tape_heal.unverified_reask(target)["since"] == reading["since"]
        assert tape_silence.missed_trades(target)["since"] == reading["since"]
        assert tape_silence.reading(target)["state"] == "dead"
        assert tape_silence.reading(target)["since"] == reading["since"]
        expected_peers = ["VEEA"] if target == "SCNI" else []
        assert tape_silence.pipeline_peers(target) == expected_peers
        queued = []
        while not queue1.empty():
            queued.append(queue1.get_nowait())
        assert any(
            f.get("silent_recovery") == "attempting" and f.get("silence_since") == reading["since"]
            for f in queued
        )

        clock["now"] += 16                             # the real same-instrument guard, on the fixture clock
        await _until(lambda: len(requests) == 4)
        await _until(lambda: tape_heal.silent_status(target)["text"] ==
                     "Tape re-asked; waiting for prints to verify its return.")
        assert tape_heal.silent_status(target)["state"] == "attempting"
        assert tape_recording.producer_status(target)["last_print_ts"] is None
        # A successful subscribe alone is never evidence that prints resumed: before 30 s pass,
        # the line still reads dead from the original outage start and missing-trades stays locked.
        assert tape_silence.missed_trades(target)["since"] == reading["since"]
        assert tape_silence.reading(target)["state"] == "dead"
        assert tape_silence.reading(target)["since"] == reading["since"]
        assert tape_silence.pipeline_peers(target) == expected_peers
        _print(ib, old_req)                             # a late cancelled-id print cannot confirm the new line
        assert tape_recording.producer_status(target)["last_print_ts"] is None
        clock["now"] += 31
        await _until(lambda: tape_heal.silent_status(target)["state"] == "failed")
        assert tape.is_subscribed(target)              # registered, still genuinely missing L1 trades
        assert tape_silence.reading(target)["state"] == "dead"
        assert tape_silence.missed_trades(target)["since"] == reading["since"]
        tape_heal.line_down(target, silence=tape_silence.reading(target))
        assert not tape_heal.healing(target) and len(requests) == 4
        _print(ib, requests[-1])                        # only an actual print is evidence of return
        assert tape_recording.producer_status(target)["healthy"] is True
        assert tape_heal.silent_status(target)["state"] == "resumed"
        assert tape_silence.missed_trades(target) is None
        assert tape_silence.reading(target) is None

    asyncio.run(scenario())
