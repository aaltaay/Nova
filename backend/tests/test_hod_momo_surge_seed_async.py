"""Held fixture SQLite reads leave the HTTP heartbeat live and never seed a new HOD generation (#797)."""
from __future__ import annotations

import asyncio
import threading
import time
from datetime import datetime, timezone

import pytest

import archive.db as archive_db
import bars_store
import hod_momo as hm
import hod_momo_surge_seed as seed
from hod_momo_state import HodMomoState
from market import session_key_et

NOW = datetime(2026, 10, 14, 14, 0, tzinfo=timezone.utc)


async def until(predicate):
    deadline = time.monotonic() + 5
    while not predicate():
        assert time.monotonic() < deadline, "fixture worker did not reach its barrier"
        await asyncio.sleep(0.001)


@pytest.fixture
def stored(monkeypatch, tmp_path):
    monkeypatch.setattr(archive_db, "cache_dir", lambda: tmp_path)
    monkeypatch.setattr(seed, "session_key_et", lambda now=None: session_key_et(now or NOW))
    monkeypatch.setattr(seed.time, "time", lambda: NOW.timestamp())
    hm.replace_state(HodMomoState(session_date=session_key_et(NOW)))
    archive_db.init_db()
    bars = [{"t": NOW.timestamp() - 60 * i, "o": 4.0, "h": 5.0, "l": 3.8, "c": 4.2, "v": 1000}
            for i in range(5, 0, -1)]
    bars_store.write_payload({"symbol": "SEED", "timeframe": "1Min", "bars": bars, "source": "ibkr"})
    return hm.get_state()


def held_read(monkeypatch):
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()
    original = bars_store.read
    threads = []

    def read(*args, **kw):
        threads.append(threading.get_ident())
        entered.set()
        assert release.wait(5), "test did not release its SQLite read"
        try:
            return original(*args, **kw)
        finally:
            finished.set()

    monkeypatch.setattr(bars_store, "read", read)
    return entered, release, finished, threads


def test_real_read_runs_on_worker_and_state_application_stays_on_loop(monkeypatch, stored):
    entered, release, finished, readers = held_read(monkeypatch)
    applied = []
    original = hm.seed_price_buffer

    def apply(*args):
        applied.append(threading.get_ident())
        return original(*args)

    monkeypatch.setattr(hm, "seed_price_buffer", apply)

    async def go():
        owner = threading.get_ident()
        task = asyncio.create_task(seed.seed_symbol_async("SEED", "ibkr"))
        try:
            await until(entered.is_set)
            beats = 0
            for _ in range(20):
                await asyncio.sleep(0)
                beats += 1
            assert beats == 20 and not task.done()
            assert not stored.session_highs and not stored.price_buffer
            release.set()
            assert await task == "store"
            assert readers[0] != owner and applied == [owner]
        finally:
            release.set()
            await task

    asyncio.run(go())
    assert finished.is_set() and stored.session_highs["SEED"] == 5.0
    assert len(stored.price_buffer["SEED"]) == 10


@pytest.mark.parametrize("change", ["owner", "session", "pending_generation", "clock_session"])
def test_late_read_cannot_seed_a_changed_generation(monkeypatch, stored, change):
    entered, release, _finished, _readers = held_read(monkeypatch)

    async def go():
        task = asyncio.create_task(seed.seed_symbol_async("SEED", "ibkr"))
        try:
            await until(entered.is_set)
            if change == "owner":
                hm.replace_state(HodMomoState(session_date=stored.session_date))
            elif change == "session":
                stored.session_date = "2026-10-15"
            elif change == "pending_generation":
                stored.pending_surge_seed = set()
            else:
                monkeypatch.setattr(seed, "session_key_et", lambda now=None: "2026-10-15")
            release.set()
            assert await task == "stale"
            assert not hm.get_state().surge_seeded and not hm.get_state().session_highs
            assert not hm.get_state().price_buffer
        finally:
            release.set()
            await task

    asyncio.run(go())


def test_cancelled_read_requeues_without_applying_after_worker_finishes(monkeypatch, stored):
    entered, release, finished, _readers = held_read(monkeypatch)

    async def go():
        task = asyncio.create_task(seed.seed_symbol_async("SEED", "ibkr"))
        try:
            await until(entered.is_set)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert stored.pending_surge_seed == {"SEED"}
            release.set()
            await until(finished.is_set)
            assert not stored.session_highs and not stored.price_buffer
        finally:
            release.set()

    asyncio.run(go())


def test_loop_cancellation_requeues_the_entire_unfinished_batch(monkeypatch, stored):
    entered, release, finished, _readers = held_read(monkeypatch)
    monkeypatch.setattr(seed, "HOD_MOMO_SURGE_SEED_POLL_SEC", 0.001)
    stored.pending_surge_seed = {"SEED", "OTHER"}

    async def go():
        task = asyncio.create_task(seed.surge_seed_loop(lambda: "ibkr"))
        try:
            await until(entered.is_set)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert stored.pending_surge_seed == {"SEED", "OTHER"}
            release.set()
            await until(finished.is_set)
        finally:
            release.set()

    asyncio.run(go())


def test_read_failure_keeps_existing_live_retry_and_a_later_store_hit_can_seed(monkeypatch, stored):
    original = bars_store.read

    def fail(*args):
        raise OSError("fixture store unavailable")

    monkeypatch.setattr(bars_store, "read", fail)
    assert asyncio.run(seed.seed_symbol_async("SEED", "ibkr")) == "live"
    assert "SEED" in stored.surge_seeded and "SEED" in stored.surge_seed_retry_at
    assert not stored.price_buffer
    stored.surge_seed_retry_at["SEED"] = 0
    hm.request_surge_seed("SEED")
    assert "SEED" in stored.pending_surge_seed and "SEED" not in stored.surge_seeded
    monkeypatch.setattr(bars_store, "read", original)
    assert asyncio.run(seed.seed_symbol_async("SEED", "ibkr")) == "store"
    assert "SEED" in stored.surge_seeded and "SEED" not in stored.surge_seed_retry_at


def test_sync_seed_rejects_event_loop_callers_before_reading(monkeypatch, stored):
    def unexpected(*args):
        raise AssertionError("a synchronous read reached the event loop")

    monkeypatch.setattr(bars_store, "read", unexpected)

    async def go():
        with pytest.raises(RuntimeError, match="seed_symbol_async"):
            seed.seed_symbol("SEED", "ibkr")

    asyncio.run(go())
