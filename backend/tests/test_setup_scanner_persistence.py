"""Held real commits never hold HTTP, lose a trigger, overtake a failure or outlive shutdown (#797)."""
from __future__ import annotations

import asyncio
import sqlite3
import threading
import time

import httpx
import pytest
from fastapi import FastAPI, HTTPException

import setup_scanner.engine as engine_module
import setup_scanner.persistence as persistence
import setup_scanner.routes as routes
from setup_scanner.engine import SetupEngine
from setup_scanner.store import SetupStore
from tests.test_setup_scanner_engine import SYM
from tests.test_setup_scanner_row_per_trigger import armed_bars, make


async def until(predicate):
    deadline = time.monotonic() + 5
    while not predicate():
        assert time.monotonic() < deadline, "fixture did not reach its barrier"
        await asyncio.sleep(0.001)


class CommitBarrier:
    """Wrap the fixture's real SQLite connection, holding inside SetupStore's actual lock."""
    def __init__(self, conn, *, fail=0):
        self.conn = conn
        self.entered, self.release = threading.Event(), threading.Event()
        self.committed, self.closed = False, False
        self.fail = fail
        self.threads = []
        self.ids = []

    def execute(self, sql, args=()):
        if sql.startswith("INSERT INTO setups"):
            self.ids.append(args[0])
        return self.conn.execute(sql, args)

    def commit(self):
        self.threads.append(threading.get_ident())
        self.entered.set()
        assert self.release.wait(5), "test did not release the real commit"
        if self.fail:
            self.fail -= 1
            raise sqlite3.OperationalError("fixture commit unavailable")
        self.conn.commit()
        self.committed = True

    def rollback(self):
        self.conn.rollback()

    def close(self):
        assert self.committed
        self.closed = True
        self.conn.close()


async def ready_engine(tmp_path):
    eng, clock = make(tmp_path / "setups.db", armed_bars())
    await eng.tick(clock["t"])
    eng.on_l1_minute("last", SYM, {"price": 4.35, "ts": clock["t"], "bar_open": 4.32})
    await eng.tick(clock["t"])
    return eng, clock


def trigger(eng, clock):
    clock["t"] += 2
    eng.on_l1_minute("last", SYM, {"price": 4.38, "ts": clock["t"], "bar_open": 4.32})


def test_real_held_commit_leaves_heartbeat_board_and_http_reads_off_the_loop(tmp_path, monkeypatch):
    async def go():
        eng, clock = await ready_engine(tmp_path)
        held = CommitBarrier(eng.store._conn)
        eng.store._conn = held
        monkeypatch.setattr(routes, "get_engine", lambda: eng)
        app = FastAPI()
        app.include_router(routes.router)
        heard = []
        eng.add_trigger_listener(lambda event: heard.append((event, held.committed)))
        trigger(eng, clock)
        tick = asyncio.create_task(eng.tick(clock["t"]))
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
            try:
                await until(held.entered.is_set)
                read = asyncio.create_task(client.get("/api/setups/rows", params={"date": eng.session}))
                for _ in range(20):
                    await asyncio.sleep(0)
                assert not tick.done() and not read.done() and not heard
                assert eng.stored_triggers(SYM, "default", "first_pullback") == [eng.active_id[SYM]]
                board = await client.get("/api/setups/board")
                assert board.status_code == 200 and board.json()["rows"][0]["state"] == "triggered"
                assert held.threads == [held.threads[0]] and held.threads[0] != threading.get_ident()
                held.release.set()
                await tick
                assert (await read).status_code == 200
                assert len(heard) == 1 and heard[0][1] is True
            finally:
                held.release.set()
                await tick
                eng.store.close()

    asyncio.run(go())


def test_failed_commit_is_retained_and_trigger_not_published_until_retry(tmp_path, monkeypatch):
    async def go():
        eng, clock = await ready_engine(tmp_path)
        held = CommitBarrier(eng.store._conn, fail=1)
        held.release.set()
        eng.store._conn = held
        monkeypatch.setattr(routes, "get_engine", lambda: eng)
        heard = []
        eng.add_trigger_listener(lambda e: heard.append((e["setup_id"], eng.store.rows()[0]["triggered_at"])))
        trigger(eng, clock)
        with pytest.raises(sqlite3.OperationalError, match="fixture commit"):
            await eng.tick(clock["t"])
        assert not heard and not held.committed and eng._outbox().pending
        assert eng.store.rows()[0]["triggered_at"] is None
        assert eng.stored_triggers(SYM, "default", "first_pullback") == [eng.active_id[SYM]]
        assert "fixture commit" in eng.board()["scoreboard_error"]
        with pytest.raises(HTTPException) as exc:
            routes._store_or_503()
        assert exc.value.status_code == 503
        await eng.tick(clock["t"])
        assert heard == [(eng.active_id[SYM], clock["t"])]
        assert not eng._outbox().pending and eng.store_error is None
        assert routes._store_or_503() is eng.store
        eng.store.close()

    asyncio.run(go())


def test_cancelled_tick_joins_commit_and_never_publishes_before_durability(tmp_path):
    async def go():
        eng, clock = await ready_engine(tmp_path)
        held = CommitBarrier(eng.store._conn)
        eng.store._conn = held
        heard = []
        eng.add_trigger_listener(heard.append)
        trigger(eng, clock)
        task = asyncio.create_task(eng.tick(clock["t"]))
        try:
            await until(held.entered.is_set)
            task.cancel()
            for _ in range(10):
                await asyncio.sleep(0)
            assert not task.done() and not heard and not held.committed
            task.cancel()   # repeated shutdown requests still join the one accepted SQLite batch
            await asyncio.sleep(0)
            assert not task.done()
            held.release.set()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert held.committed and not eng._outbox().pending and not heard
            assert eng.store.rows()[0]["triggered_at"] == clock["t"]
            await eng.tick(clock["t"])
            assert len(heard) == 1
        finally:
            held.release.set()
            eng.store.close()

    asyncio.run(go())


def test_batch_order_copies_rows_and_rolls_back_before_retry(tmp_path, monkeypatch):
    monkeypatch.setattr(persistence, "SETUPS_PERSIST_BATCH_ROWS", 2)
    store = SetupStore(tmp_path / "setups.db")
    held = CommitBarrier(store._conn, fail=1)
    held.release.set()
    store._conn = held
    outbox = persistence.OrderedOutbox(store)
    base = {"id": "A", "session_date": "2026-10-14", "symbol": "A", "state": "armed", "pillars": {"n": 1}}
    outbox.save(base)
    base["pillars"]["n"] = 2
    outbox.save({**base, "state": "triggered", "triggered_at": 10})
    outbox.save({"id": "B", "session_date": "2026-10-14", "symbol": "B", "state": "armed"})
    assert outbox.pending[0]["pillars"] == {"n": 1}

    async def go():
        with pytest.raises(sqlite3.OperationalError):
            await outbox.flush()
        assert not store.rows() and [r["id"] for r in outbox.pending] == ["A", "A", "B"]
        await outbox.flush()

    asyncio.run(go())
    assert held.ids == ["A", "A", "A", "A", "B"]
    rows = {r["id"]: r for r in store.rows()}
    assert rows["A"]["state"] == "triggered" and rows["A"]["pillars"] == {"n": 2}
    assert not outbox.pending
    store.close()


@pytest.mark.parametrize("change", ["session_clock", "replay_venue"])
def test_durable_trigger_does_not_publish_to_changed_session_or_replay(tmp_path, change):
    async def go():
        eng, clock = await ready_engine(tmp_path)
        held = CommitBarrier(eng.store._conn)
        eng.store._conn = held
        heard = []
        eng.add_trigger_listener(heard.append)
        trigger(eng, clock)
        task = asyncio.create_task(eng.tick(clock["t"]))
        try:
            await until(held.entered.is_set)
            if change == "session_clock":
                clock["t"] += 86400
            else:
                eng._replay_fn = lambda: True
            held.release.set()
            await task
            assert held.committed and not heard
        finally:
            held.release.set()
            eng.store.close()

    asyncio.run(go())


def test_runtime_shutdown_joins_history_and_commit_before_owned_store_close(tmp_path, monkeypatch):
    from ibkr import l1_minute

    async def go():
        eng, clock = await ready_engine(tmp_path)
        held = CommitBarrier(eng.store._conn)
        eng.store._conn = held
        eng._owns_store = True
        joined = []

        async def history():
            try:
                await asyncio.Event().wait()
            finally:
                joined.append("history")

        eng.seeder.task = asyncio.create_task(history())
        monkeypatch.setattr(l1_minute, "add_listener", lambda fn: None)
        monkeypatch.setattr(l1_minute, "remove_listener", lambda fn: None)
        trigger(eng, clock)
        task = asyncio.create_task(eng.run())
        try:
            await until(held.entered.is_set)
            task.cancel()
            await asyncio.sleep(0)
            assert not held.closed
            held.release.set()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert held.committed and held.closed and joined == ["history"]
            restored = SetupStore(tmp_path / "setups.db")
            assert restored.rows()[0]["triggered_at"] == clock["t"]
            restored.close()
        finally:
            held.release.set()

    asyncio.run(go())


def test_stored_trigger_load_is_off_loop(tmp_path, monkeypatch):
    eng, clock = make(tmp_path / "setups.db", armed_bars())
    original = eng.store.triggered_on
    entered, release = threading.Event(), threading.Event()
    readers = []

    def read(day):
        readers.append(threading.get_ident())
        entered.set()
        assert release.wait(5)
        return original(day)

    monkeypatch.setattr(eng.store, "triggered_on", read)

    async def go():
        task = asyncio.create_task(eng.tick(clock["t"]))
        try:
            await until(entered.is_set)
            for _ in range(20):
                await asyncio.sleep(0)
            assert not task.done() and not eng.lanes and readers[0] != threading.get_ident()
            release.set()
            await task
        finally:
            release.set()

    asyncio.run(go())
    eng.store.close()


def test_failed_trigger_read_surfaces_error_and_retries_before_lane_creation(tmp_path, monkeypatch):
    eng, clock = make(tmp_path / "setups.db", armed_bars())
    original = eng.store.triggered_on

    def fail(day):
        raise sqlite3.OperationalError("fixture trigger read unavailable")

    monkeypatch.setattr(eng.store, "triggered_on", fail)
    with pytest.raises(sqlite3.OperationalError):
        asyncio.run(eng.tick(clock["t"]))
    assert not eng.lanes and "fixture trigger read" in eng.store_error
    monkeypatch.setattr(eng.store, "triggered_on", original)
    asyncio.run(eng.tick(clock["t"]))
    assert eng.lanes and eng.store_error is None
    eng.store.close()


def test_inbox_backpressure_leaves_the_next_chunk_queued(tmp_path, monkeypatch):
    monkeypatch.setattr(engine_module, "SETUPS_INBOX_BATCH_SIZE", 2)

    async def go():
        eng, clock = await ready_engine(tmp_path)
        for _ in range(5):
            eng.on_l1_minute("last", SYM, {"price": 4.35, "ts": clock["t"], "bar_open": 4.32})
        await eng.tick(clock["t"])
        assert len(eng.inbox) == 3 and not eng._outbox().pending
        await eng.tick(clock["t"])
        assert len(eng.inbox) == 1
        await eng.tick(clock["t"])
        assert not eng.inbox
        eng.store.close()

    asyncio.run(go())


def test_trigger_publication_requires_its_own_commit_and_keeps_fifo(tmp_path):
    async def go():
        eng, clock = await ready_engine(tmp_path)
        heard = []
        eng.add_trigger_listener(lambda e: heard.append(e["setup_id"]))
        row = {"id": "FIRST", "session_date": eng.session, "symbol": SYM, "template_id": "default",
               "setup_type": "first_pullback", "triggered_at": clock["t"]}
        event = {"setup_id": "FIRST", "symbol": SYM, "template_id": "default", "setup_type": "first_pullback"}
        eng.save(row)
        eng.on_trigger(event)
        eng.publish_triggers()   # a different flush has finished, but this background row has not committed
        assert not heard
        await eng.flush_storage()
        later = {**row, "id": "SECOND"}
        eng.save(later)
        eng.on_trigger({**event, "setup_id": "SECOND"})
        eng.publish_triggers()
        assert heard == ["FIRST"] and len(eng._pending_triggers) == 1
        await eng.flush_storage()
        eng.publish_triggers()
        assert heard == ["FIRST", "SECOND"]
        eng.store.close()

    asyncio.run(go())


def test_run_catches_up_a_burst_without_sleeping_between_bounded_chunks(tmp_path, monkeypatch):
    from ibkr import l1_minute

    monkeypatch.setattr(l1_minute, "add_listener", lambda fn: None)
    monkeypatch.setattr(l1_minute, "remove_listener", lambda fn: None)
    monkeypatch.setattr(engine_module, "TICK_SEC", 60)
    observed = {}

    async def go():
        eng, clock = await ready_engine(tmp_path)
        count = 4096
        for _ in range(count):
            eng.on_l1_minute("last", SYM, {"price": 4.35, "ts": clock["t"], "bar_open": 4.32})
        seen, backlogs = [], []
        original_price = eng.playing.on_price
        original_tick = eng.tick
        done = asyncio.Event()

        def price(*args):
            seen.append(args[1])
            original_price(*args)

        async def tick(*args):
            await original_tick(*args)
            backlogs.append(len(eng.inbox))
            if not eng.inbox:
                done.set()

        eng.playing.on_price, eng.tick = price, tick
        started = time.monotonic()
        task = asyncio.create_task(eng.run())
        try:
            await asyncio.wait_for(done.wait(), 5)
            observed.update(messages=count, chunks=len(backlogs), elapsed_sec=round(time.monotonic() - started, 4),
                            final_backlog=len(eng.inbox))
            assert len(seen) == count
            assert backlogs == list(range(count - engine_module.SETUPS_INBOX_BATCH_SIZE, -1,
                                          -engine_module.SETUPS_INBOX_BATCH_SIZE))
            assert not eng._outbox().pending
        finally:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            eng.store.close()

    asyncio.run(go())
    print(f"Controlled setup inbox burst: {observed}")


def test_rollover_retains_an_old_settle_task_until_shutdown_joins_its_real_commit(tmp_path):
    from setup_scanner.seeder import SEED_COVERED, _Wait

    async def go():
        eng, clock = await ready_engine(tmp_path)
        old_session = eng.session
        held = CommitBarrier(eng.store._conn)
        eng.store._conn = held
        original_finish = eng.seeder.finish

        async def history(sym, since):
            return SEED_COVERED, None

        def finish(sym, bars, now):
            original_finish(sym, bars, now)
            eng.save({"id": "OLD-SETTLE", "session_date": eng.session, "symbol": sym, "triggered_at": now})

        eng.seeder.history, eng.seeder.finish = history, finish
        eng.seeding.add(SYM)
        eng.seeder.waiting[SYM] = _Wait(clock["t"], clock["t"])
        await eng.seeder.step(clock["t"])
        old = eng.seeder.task
        stop = None
        try:
            await until(held.entered.is_set)
            clock["t"] += 86400
            eng._rollover(clock["t"])
            assert eng.seeder.task is None and old in eng.seeder._owned
            stop = asyncio.create_task(eng.seeder.stop())
            for _ in range(10):
                await asyncio.sleep(0)
            assert not stop.done() and not old.done() and not held.committed
            held.release.set()
            await stop
            assert old.done() and not eng.seeder._owned and held.committed
            await eng.flush_storage()
            eng.store.close()
            restored = SetupStore(tmp_path / "setups.db")
            row = next(r for r in restored.rows() if r["id"] == "OLD-SETTLE")
            assert row["session_date"] == old_session and row["triggered_at"] is not None
            restored.close()
        finally:
            held.release.set()
            if stop is not None:
                await stop

    asyncio.run(go())


def test_trigger_read_revalidates_session_after_held_worker_read(tmp_path, monkeypatch):
    async def go():
        eng, clock = await ready_engine(tmp_path)
        from setup_scanner.store import session_date

        old_day, new_day = eng.session, session_date(clock["t"] + 86400)
        for sid, day in (("OLD", old_day), ("NEW", new_day)):
            eng.store.upsert({"id": sid, "session_date": day, "symbol": SYM, "triggered_at": 10,
                              "template_id": "default", "setup_type": "first_pullback"})
        eng.__dict__.pop("_triggered_memo")
        original = eng.store.triggered_on
        entered, release = threading.Event(), threading.Event()
        asked = []

        def read(day):
            asked.append(day)
            if len(asked) == 1:
                entered.set()
                assert release.wait(5)
            return original(day)

        monkeypatch.setattr(eng.store, "triggered_on", read)
        task = asyncio.create_task(eng.load_stored_triggers())
        try:
            await until(entered.is_set)
            clock["t"] += 86400
            eng._rollover(clock["t"])
            release.set()
            await task
            assert asked == [old_day, new_day]
            assert eng._triggered_memo["session"] == new_day
            assert eng.stored_triggers(SYM, "default", "first_pullback") == ["NEW"]
        finally:
            release.set()
            await task
            eng.store.close()

    asyncio.run(go())


def test_cancelled_startup_joins_slow_constructor_and_closes_result(tmp_path, monkeypatch):
    from ibkr import l1_minute
    from tests.test_setup_scanner_engine import FakeTape

    entered, release = threading.Event(), threading.Event()
    opened, closed = [], []
    registered = []

    def open_store():
        entered.set()
        assert release.wait(5)
        store = SetupStore(tmp_path / "startup.db")
        opened.append(threading.get_ident())
        close = store.close

        def closing():
            closed.append(threading.get_ident())
            close()

        store.close = closing
        return store

    monkeypatch.setattr(engine_module, "SetupStore", open_store)
    monkeypatch.setattr(l1_minute, "add_listener", registered.append)

    async def go():
        eng = SetupEngine(tape=FakeTape())
        task = asyncio.create_task(eng.run())
        try:
            await until(entered.is_set)
            task.cancel()
            await asyncio.sleep(0)
            task.cancel()
            for _ in range(10):
                await asyncio.sleep(0)
            assert not task.done() and not opened and not registered
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert len(opened) == len(closed) == 1
            assert opened[0] != threading.get_ident() and closed[0] != threading.get_ident()
            assert not registered
            with pytest.raises(sqlite3.ProgrammingError, match="closed"):
                eng.store.rows()
        finally:
            release.set()

    asyncio.run(go())


def test_filtered_event_without_row_cannot_block_a_later_durable_trigger(tmp_path):
    async def go():
        eng, clock = await ready_engine(tmp_path)
        heard = []
        eng.add_trigger_listener(lambda e: heard.append((e["setup_id"], e.get("filtered"))))
        event = {"symbol": SYM, "template_id": "default", "setup_type": "first_pullback"}
        eng.on_trigger({**event, "setup_id": "FILTERED", "filtered": "fixture stock filter"})
        eng.save({"id": "VALID", "session_date": eng.session, "symbol": SYM, "template_id": "default",
                  "setup_type": "first_pullback", "triggered_at": clock["t"]})
        eng.on_trigger({**event, "setup_id": "VALID"})
        eng.publish_triggers()
        assert heard == [("FILTERED", "fixture stock filter")]
        await eng.flush_storage()
        eng.publish_triggers()
        assert heard == [("FILTERED", "fixture stock filter"), ("VALID", None)]
        assert "FILTERED" not in {r["id"] for r in eng.store.rows()}
        eng.store.close()

    asyncio.run(go())


def test_failed_persistence_with_queued_feed_uses_bounded_retry_delay_then_recovers(tmp_path, monkeypatch):
    from ibkr import l1_minute

    monkeypatch.setattr(l1_minute, "add_listener", lambda fn: None)
    monkeypatch.setattr(l1_minute, "remove_listener", lambda fn: None)
    monkeypatch.setattr(engine_module, "TICK_SEC", 0.03)

    async def go():
        eng, clock = await ready_engine(tmp_path)
        held = CommitBarrier(eng.store._conn, fail=9999)
        held.release.set()
        eng.store._conn = held
        eng.save({"id": "RETRY", "session_date": eng.session, "symbol": SYM, "state": "armed"})
        for _ in range(5):
            eng.on_l1_minute("last", SYM, {"price": 4.35, "ts": clock["t"], "bar_open": 4.32})
        task = asyncio.create_task(eng.run())
        try:
            await until(held.entered.is_set)
            await asyncio.sleep(0.08)
            assert 1 <= len(held.threads) <= 4
            assert len(eng.inbox) == 5 and [r["id"] for r in eng._outbox().pending] == ["RETRY"]
            assert "RETRY" not in {r["id"] for r in eng.store.rows()}
            held.fail = 0
            await until(lambda: not eng.inbox and eng.store_error is None)
            assert not eng._outbox().pending and held.committed
            assert "RETRY" in {r["id"] for r in eng.store.rows()}
        finally:
            held.fail = 0
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            eng.store.close()

    asyncio.run(go())


def test_completed_history_task_observes_and_logs_its_persistence_failure(tmp_path, caplog):
    from setup_scanner.seeder import SEED_COVERED, _Wait

    async def go():
        eng, clock = await ready_engine(tmp_path)
        held = CommitBarrier(eng.store._conn, fail=1)
        held.release.set()
        eng.store._conn = held
        original_finish = eng.seeder.finish

        async def history(sym, since):
            return SEED_COVERED, None

        def finish(sym, bars, now):
            original_finish(sym, bars, now)
            eng.save({"id": "FAILED-HISTORY", "session_date": eng.session, "symbol": sym})

        eng.seeder.history, eng.seeder.finish = history, finish
        eng.seeding.add(SYM)
        eng.seeder.waiting[SYM] = _Wait(clock["t"], clock["t"])
        await eng.seeder.step(clock["t"])
        task = eng.seeder.task
        await until(lambda: task.done() and not eng.seeder._owned)
        assert any(r.message == "setup scanner: history task failed" and r.exc_info for r in caplog.records)
        assert "fixture commit" in eng.store_error and eng._outbox().pending
        await eng.flush_storage()
        assert not eng._outbox().pending
        eng.store.close()

    asyncio.run(go())
