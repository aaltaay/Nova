"""IB-loop non-blocking guarantees for D-012 / D-018 / D-020 / D-025.

Every case here answers one question: does this path still put blocking work
(SQLite, ``time.sleep``, an off-owner ``reqMktData``) on the IB connect-loop?
"""
from __future__ import annotations

import ast
import asyncio
import threading
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from execution import persist_queue
from ibkr import loop_supervisor
from ibkr.historical_service import request_bars, reset_for_testing


@pytest.fixture(autouse=True)
def _reset():
    reset_for_testing()
    persist_queue.reset_for_tests()
    yield
    reset_for_testing()
    persist_queue.reset_for_tests()


def _call_names(module) -> set[str]:
    """Dotted names of every call in ``module`` -- prose in docstrings excluded."""
    tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
    return {
        ast.unparse(node.func)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
    }


def _payload(symbol: str, timeframe: str) -> dict:
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "bars": [{"t": "2026-09-11T14:00:00Z", "o": 1, "h": 1, "l": 1, "c": 1, "v": 1}],
        "source": "ibkr",
    }


# ── D-018: bars_store SQLite runs in a worker thread ─────────────────────────


def test_historical_fill_reads_and_writes_bars_store_off_the_loop():
    """A cold 1Min fill must not open SQLite on the IB loop thread."""
    caller_thread = threading.get_ident()
    read_threads: list[int] = []
    write_threads: list[int] = []

    def fake_read(_symbol, _timeframe, _limit):
        read_threads.append(threading.get_ident())
        return None

    def fake_write(_payload):
        write_threads.append(threading.get_ident())

    async def fake_fetch(symbol, timeframe, limit, *, interactive=False):
        return _payload(symbol, timeframe)

    async def _run():
        with (
            patch("bars_store.read", side_effect=fake_read),
            patch("bars_store.write_payload", side_effect=fake_write),
            patch("bars_store.coverage_from_bars", return_value={"filling": False}),
            patch("ticker_bars_push.broadcast_bars_patch"),
            patch("ibkr.bars.fetch_bars_async", new=AsyncMock(side_effect=fake_fetch)),
            patch("ibkr.historical_service._persist_derived"),
        ):
            await request_bars("AAPL", "1Min", 10, priority="open_chart")

    asyncio.run(_run())
    assert read_threads and write_threads
    assert caller_thread not in read_threads
    assert caller_thread not in write_threads


# ── D-025: no pacing sleep on the loop, semaphore released while deferred ────


def test_paced_open_chart_leaves_the_hist_semaphore_free():
    """The paced fill reschedules; a second symbol still gets a slot at once."""
    waits = {"AAPL": 2.0, "MSFT": 0.0}
    rescheduled: list[tuple[str, float]] = []
    fetched: list[str] = []

    async def fake_fetch(symbol, timeframe, limit, *, interactive=False):
        fetched.append(symbol)
        return _payload(symbol, timeframe)

    async def _run():
        import ibkr.historical_service as hs

        with (
            patch("bars_store.read", return_value=None),
            patch("bars_store.write_payload"),
            patch("bars_store.coverage_from_bars", return_value={"filling": False}),
            patch("ticker_bars_push.broadcast_bars_patch"),
            patch("ibkr.bars.fetch_bars_async", new=AsyncMock(side_effect=fake_fetch)),
            patch("ibkr.historical_service._persist_derived"),
            patch(
                "ibkr.historical_service._pacing.wait_seconds",
                side_effect=lambda sym, tf, dur: waits[sym],
            ),
            patch.object(
                hs,
                "_reschedule_after_wait",
                side_effect=lambda sym, tf, lim, pri, wait: rescheduled.append(
                    (sym, wait),
                ),
            ),
        ):
            with pytest.raises(hs.HistoricalShed):
                await request_bars("AAPL", "1Min", 10, priority="open_chart")
            await request_bars("MSFT", "1Min", 10, priority="open_chart")
            assert hs._semaphore()._value == int(
                hs.IBKR_HISTORICAL_MAX_CONCURRENT
            )

    asyncio.run(_run())
    assert rescheduled == [("AAPL", 2.0)]
    assert fetched == ["MSFT"]


def test_historical_service_has_no_sleep_left():
    """Static guard: a future edit must not reintroduce sleep-then-send."""
    import ibkr.historical_service as hs

    calls = _call_names(hs)
    assert "asyncio.sleep" not in calls
    assert "time.sleep" not in calls
    assert "asyncio.to_thread" in calls


# ── D-012a: ledger writes leave the IB loop ──────────────────────────────────


def test_persist_queue_defers_from_the_ib_thread_and_keeps_order():
    order: list[str] = []
    loop_supervisor.start()
    try:

        def on_loop() -> None:
            persist_queue.submit("first", lambda: order.append("first"))
            persist_queue.submit("second", lambda: order.append("second"))
            persist_queue.submit("third", lambda: order.append("third"))

        deferred = loop_supervisor.call_on_ib(
            lambda: [
                persist_queue.submit("probe", lambda: None),
            ],
            5.0,
        )
        assert deferred == [True]  # submitted from the IB loop -> queued
        loop_supervisor.call_on_ib(on_loop, 5.0)
        assert persist_queue.flush(5.0) is True
    finally:
        loop_supervisor.stop()
    assert order == ["first", "second", "third"]


def test_persist_queue_runs_inline_off_the_ib_loop():
    ran: list[str] = []
    assert persist_queue.submit("inline", lambda: ran.append("inline")) is False
    assert ran == ["inline"]


def test_order_watch_ack_and_fill_writes_go_through_the_queue():
    from execution.telemetry import OrderWatch

    submitted: list[str] = []

    def fake_submit(label, job):
        submitted.append(label)
        return True

    watch = OrderWatch(4242, "exec-4242")
    with patch("execution.persist_queue.submit", side_effect=fake_submit):
        watch.note_status("Filled", filled=1.0, average_fill_price=2.5)
        watch.note_filled()

    assert any(label.startswith("ack order 4242") for label in submitted)
    assert any(label.startswith("fill evidence order 4242") for label in submitted)
    assert any(label.startswith("fill order 4242") for label in submitted)
    assert any(label.startswith("round-trip order 4242") for label in submitted)


# ── D-012b: cancel verify is awaitable and wakes on orderStatus ──────────────


def test_cancel_verify_wakes_on_order_status_without_polling():
    import ibkr.cancel_verify as cv
    import ibkr.orders as orders
    from execution.telemetry import OrderWatch

    open_rows = [{"order_id": 51}]
    watch = OrderWatch(51, "exec-51")

    async def _run():
        with (
            patch.object(orders, "cancel_order", return_value={"ok": True, "error": None}),
            patch.object(orders, "open_orders", side_effect=lambda: list(open_rows)),
        ):
            task = asyncio.create_task(
                cv.cancel_order_verified(51, timeout_sec=5.0, poll_sec=4.0, watch=watch),
            )
            await asyncio.sleep(0)
            # The verify is parked on the callback, not on a 4s poll tick.
            open_rows.clear()
            watch.note_status("Cancelled")
            return await asyncio.wait_for(task, timeout=1.0)

    out = asyncio.run(_run())
    assert out["ok"] is True
    assert out["verified_gone"] is True
    assert watch._status_listeners == []


def test_cancel_verify_reports_still_open_after_timeout():
    import ibkr.cancel_verify as cv
    import ibkr.orders as orders

    async def _run():
        with (
            patch.object(orders, "cancel_order", return_value={"ok": True, "error": None}),
            patch.object(orders, "open_orders", return_value=[{"order_id": 77}]),
        ):
            return await cv.cancel_order_verified(77, timeout_sec=0.1, poll_sec=0.05)

    out = asyncio.run(_run())
    assert out["ok"] is False
    assert out["verified_gone"] is False
    assert "still open" in out["error"]


def test_cancel_verify_module_has_no_thread_hop_or_blocking_sleep():
    import ibkr.cancel_verify as cv

    calls = _call_names(cv)
    assert "asyncio.to_thread" not in calls
    assert "time.sleep" not in calls


# ── D-020: shortability rides the shared owner-aware L1 line ─────────────────


class _FakeEvent:
    def __init__(self) -> None:
        self.listeners: list = []

    def __iadd__(self, fn):
        self.listeners.append(fn)
        return self

    def __isub__(self, fn):
        if fn in self.listeners:
            self.listeners.remove(fn)
        return self

    def fire(self, ticker) -> None:
        for fn in list(self.listeners):
            fn(ticker)


class _FakeTicker:
    def __init__(self, shortable=None) -> None:
        self.updateEvent = _FakeEvent()
        self.shortableShares = shortable


class _FakeIb:
    def __init__(self) -> None:
        self.mkt_data_calls: list[tuple[str, str]] = []
        self.cancel_calls: list[str] = []
        self.tickers: dict[str, _FakeTicker] = {}

    async def qualifyContractsAsync(self, contract):
        contract.conId = 1234
        return [contract]

    def reqMktData(self, contract, generic="", *_args):
        self.mkt_data_calls.append((contract.symbol, generic))
        ticker = self.tickers.setdefault(contract.symbol, _FakeTicker())
        return ticker

    def cancelMktData(self, contract):
        self.cancel_calls.append(contract.symbol)


@pytest.fixture
def ticks_env(monkeypatch):
    import ibkr.client as client_mod
    import ibkr.ticks as ticks_mod

    fake_ib = _FakeIb()
    monkeypatch.setattr(client_mod, "get_ib", lambda: fake_ib)
    ticks_mod._subs.clear()
    ticks_mod._subscribe_lock = None
    yield ticks_mod, fake_ib
    ticks_mod._subs.clear()
    ticks_mod._subscribe_lock = None


def test_shortability_uses_the_shared_line_and_waits_for_the_tick(ticks_env):
    from ibkr import listing_flags

    ticks_mod, fake_ib = ticks_env

    async def _run():
        task = asyncio.create_task(listing_flags._shortable_shares("SOAR"))
        await asyncio.sleep(0)
        ticker = fake_ib.tickers["SOAR"]
        ticker.shortableShares = 25_000.0
        ticker.updateEvent.fire(ticker)
        return await asyncio.wait_for(task, timeout=1.0)

    shares = asyncio.run(_run())
    assert shares == 25_000.0
    # One line: default L1 generic ticks merged with listing 236, then released.
    from constants import IBKR_L1_GENERIC_TICKS
    assert fake_ib.mkt_data_calls == [("SOAR", f"{IBKR_L1_GENERIC_TICKS},236")]
    assert fake_ib.cancel_calls == ["SOAR"]
    assert ticks_mod.owners_for("SOAR") == set()


def test_shortability_upgrades_an_existing_line_instead_of_opening_one(ticks_env):
    from ibkr import listing_flags

    ticks_mod, fake_ib = ticks_env

    async def _run():
        assert await ticks_mod.subscribe("SOAR", ticks_mod.OWNER_SCANNER)
        fake_ib.tickers["SOAR"].shortableShares = 900.0
        shares = await listing_flags._shortable_shares("SOAR")
        return shares, ticks_mod.owners_for("SOAR")

    shares, owners = asyncio.run(_run())
    assert shares == 900.0
    from constants import IBKR_L1_GENERIC_TICKS
    assert fake_ib.mkt_data_calls == [
        ("SOAR", IBKR_L1_GENERIC_TICKS),
        ("SOAR", f"{IBKR_L1_GENERIC_TICKS},236"),
    ]
    # The scanner keeps its stream: the upgrade cancelled only to re-request.
    assert fake_ib.cancel_calls == ["SOAR"]
    assert owners == {"scanner"}
    assert ticks_mod.has_generic_tick("SOAR", "233") is True
    assert ticks_mod.has_generic_tick("SOAR", "49") is True
    assert ticks_mod.has_generic_tick("SOAR", "236") is True


def test_shortability_times_out_without_a_tick(ticks_env, monkeypatch):
    from ibkr import listing_flags

    monkeypatch.setattr(listing_flags, "IBKR_SHORTABLE_TICK_WAIT_SEC", 0.05)
    shares = asyncio.run(listing_flags._shortable_shares("SOAR"))
    assert shares is None


def test_scanner_subscribe_requests_rtvolume_on_the_shared_line(ticks_env):
    ticks_mod, fake_ib = ticks_env

    async def _run():
        assert await ticks_mod.subscribe("PFSA", ticks_mod.OWNER_SCANNER)
        assert await ticks_mod.subscribe("PFSA", ticks_mod.OWNER_DETAIL)
        return (
            ticks_mod.owners_for("PFSA"),
            ticks_mod.has_generic_tick("PFSA", "233"),
            ticks_mod.has_generic_tick("PFSA", "49"),
        )

    owners, has_233, has_49 = asyncio.run(_run())
    from constants import IBKR_L1_GENERIC_TICKS
    assert fake_ib.mkt_data_calls == [("PFSA", IBKR_L1_GENERIC_TICKS)]
    assert fake_ib.cancel_calls == []
    assert owners == {"scanner", "detail"}
    assert has_233 is True
    assert has_49 is True


def test_listing_flags_never_calls_req_mkt_data_directly():
    from ibkr import listing_flags

    calls = _call_names(listing_flags)
    assert not [name for name in calls if name.endswith("reqMktData")]
    assert not [name for name in calls if name.endswith("cancelMktData")]
    assert "asyncio.sleep" not in calls
