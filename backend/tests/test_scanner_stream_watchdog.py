"""The watchdog reopens a persistent scanner lease that never answered.

Regression 2026-10-23: IBKR refused the 04:00 Gainers lease with Error 322
(all ten scanner slots taken) and ``_watchdog_once`` skipped every lease with
no batch yet, so the Gainers board recorded 0 rows until 16:00.
"""
from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace

import pytest

from constants import (
    IBKR_ERROR_SCANNER_SLOT_EXHAUSTED,
    IBKR_SCANNER_FIRST_BATCH_RESUBSCRIBE_SEC,
    IBKR_SCANNER_WATCHDOG_MIN_SEC,
)
from ibkr import discovery
from ibkr import loop_supervisor
from ibkr import scanner_stream as stream

LIMIT = IBKR_SCANNER_FIRST_BATCH_RESUBSCRIBE_SEC


def _lease(table: str = "gainers", *, opened: float) -> stream._Lease:
    return stream._Lease(
        table=table,
        scan_code="TOP_PERC_GAIN",
        generation=stream._client.current_generation(),
        epoch=stream._epoch,
        session_key=stream._session.session_key_et(),
        opened_mono=opened,
    )


@pytest.fixture
def desk(monkeypatch):
    """A monotonic clock the test moves, and fake cancel / open / slot recovery
    that record what the watchdog did, in order."""
    clock = SimpleNamespace(now=50_000.0)
    monkeypatch.setattr(
        stream, "time",
        SimpleNamespace(monotonic=lambda: clock.now, perf_counter_ns=time.perf_counter_ns),
    )
    events: list[tuple[str, str]] = []

    def _cancel(table, *, freeze_first=False):
        events.append(("cancel", table))
        stream._leases.pop(table, None)

    async def _open(spec):
        events.append(("open", spec.table))
        lease = _lease(spec.table, opened=clock.now)
        stream._leases[spec.table] = lease
        return lease

    def _recover(_ib):
        events.append(("recover", ""))
        return 3

    monkeypatch.setattr(stream, "_cancel_lease", _cancel)
    monkeypatch.setattr(stream, "_open_lease", _open)
    monkeypatch.setattr(discovery, "recover_scanner_slots", _recover)
    stream._leases.clear()
    yield SimpleNamespace(clock=clock, events=events)
    stream._leases.clear()
    stream._pending_hydrate.clear()


@pytest.mark.asyncio
async def test_silent_lease_past_the_limit_is_reopened_once_then_spaced(desk):
    stream._leases["gainers"] = _lease(opened=desk.clock.now)
    desk.clock.now += LIMIT + 1

    await stream._watchdog_once()
    assert desk.events == [("cancel", "gainers"), ("open", "gainers")]

    # The reopened lease is timed from its own open: a Gateway that keeps
    # refusing is asked once per limit, never every reconcile tick.
    await stream._watchdog_once()
    desk.clock.now += LIMIT - 1
    await stream._watchdog_once()
    assert desk.events == [("cancel", "gainers"), ("open", "gainers")]

    desk.clock.now += 2
    await stream._watchdog_once()
    assert desk.events.count(("open", "gainers")) == 2


def test_lease_that_answered_with_an_empty_batch_is_not_reopened(desk):
    """An empty batch is an answer (2026-08-07); only no event is silence."""
    assert LIMIT + 5 < IBKR_SCANNER_WATCHDOG_MIN_SEC
    lease = _lease(opened=desk.clock.now)
    stream._leases["gainers"] = lease
    desk.clock.now += 1
    stream._on_batch(lease, [])
    assert lease.last_batch_mono == desk.clock.now

    desk.clock.now += LIMIT + 5   # past the first-batch limit, inside the stall limit
    asyncio.run(stream._watchdog_once())
    assert desk.events == []


@pytest.mark.asyncio
async def test_fresh_silent_lease_inside_the_limit_is_kept(desk):
    stream._leases["gainers"] = _lease(opened=desk.clock.now)
    desk.clock.now += LIMIT - 1
    await stream._watchdog_once()
    assert desk.events == []


@pytest.mark.asyncio
async def test_stalled_lease_is_still_reopened(desk):
    lease = _lease(opened=desk.clock.now)
    lease.last_batch_mono = desk.clock.now
    lease.batch_intervals = [5.0, 5.0, 5.0]   # limit = max(min, mult x 5 s) = min
    stream._leases["gainers"] = lease
    desk.clock.now += IBKR_SCANNER_WATCHDOG_MIN_SEC - 1
    await stream._watchdog_once()
    assert desk.events == []
    desk.clock.now += 2
    await stream._watchdog_once()
    assert desk.events == [("cancel", "gainers"), ("open", "gainers")]


@pytest.mark.asyncio
async def test_lease_refused_for_slots_frees_leaked_slots_before_reopening(desk):
    refused = _lease(opened=desk.clock.now)
    refused.ib_error_code = IBKR_ERROR_SCANNER_SLOT_EXHAUSTED
    stream._leases["gainers"] = refused
    desk.clock.now += LIMIT + 1
    await stream._watchdog_once()
    assert desk.events == [("cancel", "gainers"), ("recover", ""), ("open", "gainers")]


class _Event:
    def __init__(self) -> None:
        self.handlers: list = []

    def __iadd__(self, handler):
        self.handlers.append(handler)
        return self

    def __isub__(self, handler):
        self.handlers.remove(handler)
        return self

    def emit(self, *args) -> None:
        for handler in list(self.handlers):
            handler(*args)


@pytest.mark.asyncio
async def test_open_lease_keeps_the_refusal_code_and_its_open_time(monkeypatch, caplog):
    """IBKR answers a refused subscribe with Error 322 and never a batch: the
    lease keeps the code (only for its own reqId) and names it in the log."""

    class _IB:
        def __init__(self) -> None:
            self.errorEvent = _Event()

        def reqScannerSubscription(self, _sub):
            loop = asyncio.get_running_loop()
            loop.call_soon(self.errorEvent.emit, 9999, 200, "other request", None)
            loop.call_soon(self.errorEvent.emit, 438420, 322, "Only 10 simultaneous", None)
            return SimpleNamespace(reqId=438420, updateEvent=_Event())

    ib = _IB()
    monkeypatch.setattr(stream._client, "get_ib", lambda: ib)
    monkeypatch.setattr(stream._client, "is_ready", lambda: True)
    monkeypatch.setattr(stream, "_load_types", lambda: True)
    monkeypatch.setattr(stream, "_ScannerSubscription", lambda **kw: SimpleNamespace(**kw))
    monkeypatch.setattr(stream, "IBKR_SCAN_REQUEST_TIMEOUT_SEC", 0.05)
    monkeypatch.setattr(loop_supervisor, "is_started", lambda: False)
    spec = stream._session.LeaseSpec(table="gainers", scan_code="TOP_PERC_GAIN")
    before = time.monotonic()
    try:
        with caplog.at_level("WARNING", logger=stream.__name__):
            lease = await stream._open_lease(spec)
        assert lease is not None
        assert lease.ib_error_code == 322
        assert lease.last_batch_mono == 0.0
        assert before <= lease.opened_mono <= time.monotonic()
        assert ib.errorEvent.handlers == []   # the hook lives only for the first-batch wait
        assert "first batch timeout for gainers" in caplog.text
        assert "(IBKR Error 322)" in caplog.text
    finally:
        stream._leases.pop("gainers", None)
        stream._persistent_reqids.pop(438420, None)
