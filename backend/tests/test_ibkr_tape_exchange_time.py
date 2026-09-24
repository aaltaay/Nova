"""IBKR's own second on each AllLast print, beside ib_async's arrival time (#563).

ib_async 2.1.0 builds each AllLast tick with ``Wrapper.lastTime`` (when the
message reached Nova) and throws IBKR's ``time`` argument away, so a live print
labelled ``ts_source: "exchange"`` carried an arrival time. These tests drive
the pinned ib_async's own IB, registry and decoder, with only the socket
stubbed.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from ib_async import IB, Stock
from ib_async.objects import TickAttribLast, TickByTickAllLast

from ibkr import tape_events, tape_exchange_time

IBKR_SECOND = 1_790_000_000                                  # the print's own second, per IBKR
ARRIVED = datetime(2026, 9, 24, 13, 30, 2, 250_000, tzinfo=timezone.utc)  # when it reached Nova


def _ib_with_all_last_line() -> tuple[IB, object, int]:
    """A real IB holding one AllLast line (request id 7), nothing sent anywhere."""
    ib = IB()
    ib.client.getReqId = lambda: 7
    ib.client.reqTickByTickData = lambda *_args: None
    contract = Stock("IPDN", "SMART", "USD")
    contract.conId = 42
    ticker = ib.reqTickByTickData(contract, "AllLast")
    ib.wrapper.lastTime = ARRIVED
    return ib, ticker, 7


def _decode_print(ib: IB, req_id: int, *, second: int = IBKR_SECOND, price="10.5", size="100",
                  mask="0", exchange="NASDAQ", conditions="") -> None:
    """One tickByTick AllLast message through ib_async's own decoder (msg 99, tick type 2)."""
    ib.client.decoder.tickByTick(["99", str(req_id), "2", str(second), price, size, mask, exchange, conditions])


def test_the_pinned_ib_async_stamps_prints_with_their_arrival_not_ibkrs_time():
    """Why the override exists. If ib_async starts keeping IBKR's time, revisit #563."""
    ib, ticker, req_id = _ib_with_all_last_line()
    _decode_print(ib, req_id)
    tick = ticker.tickByTicks[-1]
    assert tick.time == ARRIVED
    assert tape_exchange_time.exchange_second(tick) is None


def test_install_keeps_ibkrs_second_beside_the_arrival_time():
    ib, ticker, req_id = _ib_with_all_last_line()
    assert tape_exchange_time.install(ib) is True
    _decode_print(ib, req_id, price="10.55", size="300", mask="2", conditions="4 W")

    tick = ticker.tickByTicks[-1]
    assert isinstance(tick, TickByTickAllLast)
    assert tick.time == ARRIVED                                   # the order stays arrival time
    assert tape_exchange_time.exchange_second(tick) == IBKR_SECOND
    assert (tick.price, tick.size, tick.exchange, tick.specialConditions) == (10.55, 300.0, "NASDAQ", "4 W")
    assert tick.tickAttribLast.unreported is True
    assert ticker.last == 10.55                                   # ib_async's own bookkeeping ran


def test_install_is_idempotent_and_each_print_is_stamped_once():
    ib, ticker, req_id = _ib_with_all_last_line()
    assert tape_exchange_time.install(ib) is True
    assert tape_exchange_time.install(ib) is True
    _decode_print(ib, req_id, second=IBKR_SECOND)
    _decode_print(ib, req_id, second=IBKR_SECOND + 1)
    assert [tape_exchange_time.exchange_second(t) for t in ticker.tickByTicks] == [IBKR_SECOND, IBKR_SECOND + 1]


def test_an_unknown_request_id_keeps_nothing_and_raises_nothing():
    ib, ticker, _req_id = _ib_with_all_last_line()
    tape_exchange_time.install(ib)
    _decode_print(ib, 999)
    assert ticker.tickByTicks == []


def test_a_stamp_that_fails_keeps_the_print_as_ib_async_built_it(monkeypatch, caplog):
    ib, ticker, req_id = _ib_with_all_last_line()
    tape_exchange_time.install(ib)
    monkeypatch.setattr(tape_exchange_time, "_stamp", lambda *_a: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(tape_exchange_time, "_stamp_failed_logged", False)
    with caplog.at_level(logging.WARNING, logger="ibkr.tape_exchange_time"):
        _decode_print(ib, req_id)
    assert type(ticker.tickByTicks[-1]) is TickByTickAllLast
    assert tape_exchange_time.exchange_second(ticker.tickByTicks[-1]) is None
    assert "could not keep IBKR's second" in caplog.text


def test_a_wrapper_without_the_hook_is_reported_not_patched(caplog):
    with caplog.at_level(logging.DEBUG, logger="ibkr.tape_exchange_time"):
        assert tape_exchange_time.install(SimpleNamespace(wrapper=SimpleNamespace())) is False
    assert tape_exchange_time.install(SimpleNamespace()) is False
    assert "no exchange second" in caplog.text


@pytest.mark.parametrize("value", [None, 0, -5, True, 1.5, "1790000000"])
def test_exchange_second_is_a_positive_whole_second_or_none(value):
    assert tape_exchange_time.exchange_second(SimpleNamespace(exchange_time=value)) is None


def test_a_live_print_says_its_time_is_the_arrival_and_carries_ibkrs_second(monkeypatch):
    """A fake wrapper call whose IBKR time differs from lastTime, through the tape payload."""
    ib, ticker, req_id = _ib_with_all_last_line()
    tape_exchange_time.install(ib)
    _decode_print(ib, req_id)
    dispatched, pushed = [], []
    monkeypatch.setattr("ibkr.tape_recording.dispatch", lambda payload: dispatched.append(dict(payload)))
    monkeypatch.setattr(tape_events, "_practice_desk", lambda: False)
    monkeypatch.setattr("archive.write_queue.enqueue_tape_print", lambda **_kw: None)
    monkeypatch.setattr("archive.bar_builder.on_tape_print", lambda **_kw: None)
    monkeypatch.setattr("ibkr.tape_10sec.on_print", lambda *_a: None)
    depth = SimpleNamespace(current_book=lambda _symbol: None)

    tape_events.on_tape_update(ticker, "IPDN", lambda _s, payload: pushed.append(payload), depth)

    assert len(dispatched) == len(pushed) == 1
    for payload in (dispatched[0], pushed[0]):
        assert payload["ts_source"] == "receive"
        assert payload["ts"] == ARRIVED.timestamp()
        assert payload["exchange_ts"] == IBKR_SECOND
        assert payload["time"] == ARRIVED.isoformat()


def test_a_print_the_override_did_not_see_says_receive_with_no_exchange_second(monkeypatch):
    dispatched = []
    monkeypatch.setattr("ibkr.tape_recording.dispatch", lambda payload: dispatched.append(dict(payload)))
    monkeypatch.setattr(tape_events, "_practice_desk", lambda: True)
    monkeypatch.setattr("archive.write_queue.enqueue_tape_print", lambda **_kw: None)
    monkeypatch.setattr("archive.bar_builder.on_tape_print", lambda **_kw: None)
    monkeypatch.setattr("ibkr.tape_10sec.on_print", lambda *_a: None)
    plain = TickByTickAllLast(2, ARRIVED, 10.5, 100.0, TickAttribLast(), "NASDAQ", "")
    ticker = SimpleNamespace(tickByTicks=[plain])

    tape_events.on_tape_update(ticker, "IPDN", lambda *_a: None, SimpleNamespace(current_book=lambda _s: None))

    assert dispatched[0]["ts_source"] == "receive"
    assert dispatched[0]["exchange_ts"] is None


def test_opening_a_tape_line_installs_the_override_on_that_ib(monkeypatch):
    from ibkr import client, tape_stream

    ib = IB()
    ib.client.getReqId = lambda: 7
    ib.client.reqTickByTickData = lambda *_args: None

    async def qualify(contract):
        contract.conId = 42
        return [contract]

    ib.qualifyContractsAsync = qualify
    tape_stream.reset_for_tests()
    monkeypatch.setattr(client, "get_ib", lambda: ib)
    monkeypatch.setattr(client, "current_generation", lambda: 1)
    monkeypatch.setattr(tape_stream, "_warm_10sec_fill", lambda _symbol: None)
    try:
        assert asyncio.run(tape_stream.subscribe_async("IPDN"))["ok"] is True
        ib.wrapper.lastTime = ARRIVED
        _decode_print(ib, 7)
        tick = tape_stream._tickers["IPDN"]["ticker"].tickByTicks[-1]
        assert tick.time == ARRIVED
        assert tape_exchange_time.exchange_second(tick) == IBKR_SECOND
    finally:
        tape_stream.reset_for_tests()
