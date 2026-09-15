"""Advise worker pool: max 3, one active per symbol, other symbols still start."""
from __future__ import annotations

import asyncio

import pytest

from advise import book, pool
from constants_advise import ADVISE_GRAPH_VERSION, ADVISE_MAX_WORKERS


@pytest.fixture
def advise_iso(tmp_path, monkeypatch):
    monkeypatch.setenv("NOVA_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("ADVISE_STUB", "1")
    pool.reset_for_tests()
    book.init_db()
    return tmp_path


def _queued(symbol: str) -> dict:
    return book.create_run(
        symbol=symbol,
        model="stub",
        graph_version=ADVISE_GRAPH_VERSION,
        depth=1,
        session_date="2026-09-15",
    )


@pytest.mark.asyncio
async def test_max_three_workers_queue_the_fourth(advise_iso, monkeypatch):
    hold = asyncio.Event()

    async def _hold(_run_id: int) -> None:
        await hold.wait()

    monkeypatch.setattr(pool, "_spawn", _hold)
    ids = []
    for symbol in ("AAA", "BBB", "CCC", "DDD"):
        run = _queued(symbol)
        ids.append(run["id"])
        await pool.enqueue(run["id"])
    await asyncio.sleep(0)
    assert ADVISE_MAX_WORKERS == 3
    assert len(pool._reserved) == 3
    assert pool.queued_run_ids() == [ids[3]]
    assert pool.active_run_for("DDD") is None
    hold.set()


@pytest.mark.asyncio
async def test_same_symbol_queues_other_symbols_still_start(advise_iso, monkeypatch):
    hold = asyncio.Event()

    async def _hold(_run_id: int) -> None:
        await hold.wait()

    monkeypatch.setattr(pool, "_spawn", _hold)
    first = _queued("AAPL")
    extra = _queued("AAPL")
    other = _queued("MSFT")
    await pool.enqueue(first["id"])
    await pool.enqueue(extra["id"])
    await pool.enqueue(other["id"])
    await asyncio.sleep(0)
    assert pool.active_run_for("AAPL") == first["id"]
    assert pool.active_run_for("MSFT") == other["id"]
    assert extra["id"] in pool.queued_run_ids()
    hold.set()
