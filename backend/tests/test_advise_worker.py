"""Advise worker: stub graph, cancel kills the process, retry from failed."""
from __future__ import annotations

import asyncio

import pytest

from advise import book, pool, service
from advise.engine import run_debate
from advise.worker_main import main as worker_main
from constants_advise import ADVISE_GRAPH_VERSION, advise_model_id


@pytest.fixture
def advise_iso(tmp_path, monkeypatch):
    monkeypatch.setenv("NOVA_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("ADVISE_STUB", "1")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    pool.reset_for_tests()
    book.init_db()
    return tmp_path


def test_stub_engine_emits_full_set(advise_iso, monkeypatch):
    monkeypatch.setenv("ADVISE_STUB_SLEEP_SEC", "0")
    events = []
    result = run_debate("AAPL", 2, events.append)
    agents = [e.get("agent") for e in events if e.get("type") == "message"]
    assert "fundamentals" in agents
    assert "news" in agents
    assert "sentiment" in agents
    assert "technical" in agents
    assert agents.count("bull") == 2
    assert agents.count("bear") == 2
    assert "trader" in agents
    assert "risk_judge" in agents
    assert result["stance"] == "HOLD"
    assert result["ticket"] is None


@pytest.mark.asyncio
async def test_pool_spawn_stub_completes(advise_iso, monkeypatch):
    monkeypatch.setattr(service, "session_key_et", lambda now=None: "2026-09-15")
    started = await service.start_run("META", 1, force_refresh=True)

    async def _wait():
        while True:
            run = book.get_run(started["id"])
            if run and run["status"] in ("complete", "failed", "cancelled"):
                return run
            await asyncio.sleep(0.05)

    run = await asyncio.wait_for(_wait(), timeout=12)
    assert run["status"] == "complete", run.get("fail_reason")
    assert run["result"]["stance"] == "HOLD"


def test_stub_worker_completes_and_saves_book(advise_iso, monkeypatch):
    monkeypatch.setenv("ADVISE_STUB_SLEEP_SEC", "0")
    monkeypatch.setattr(service, "session_key_et", lambda now=None: "2026-09-15")
    started = book.create_run(
        symbol="AAPL",
        model=advise_model_id(),
        graph_version=ADVISE_GRAPH_VERSION,
        depth=1,
        session_date="2026-09-15",
    )
    assert worker_main(["--run-id", str(started["id"])]) == 0
    run = book.get_run(started["id"])
    assert run is not None
    assert run["status"] == "complete", run.get("fail_reason")
    assert run["result"]["stance"] == "HOLD"
    assert any(ev.get("agent") == "risk_judge" for ev in run["transcript"])

    async def _reopen():
        return await service.start_run("AAPL", 1, force_refresh=False)

    again = asyncio.run(_reopen())
    assert again["id"] == started["id"]
    assert again["from_book"] is True


@pytest.mark.asyncio
async def test_cancel_before_spawn_clears_slot(advise_iso, monkeypatch):
    monkeypatch.setattr(service, "session_key_et", lambda now=None: "2026-09-15")
    started = await service.start_run("IBM", 2, force_refresh=True)
    cancelled = await service.cancel_run(started["id"])
    assert cancelled["status"] == "cancelled"
    await asyncio.sleep(0.2)
    assert pool.active_run_for("IBM") is None
    loaded = book.get_run(started["id"])
    assert loaded is not None
    assert loaded["status"] == "cancelled"


@pytest.mark.asyncio
async def test_cancel_kills_slow_stub(advise_iso, monkeypatch):
    monkeypatch.setenv("ADVISE_STUB_HANG_SEC", "20")
    monkeypatch.setattr(service, "session_key_et", lambda now=None: "2026-09-15")
    started = await service.start_run("TSLA", 2, force_refresh=True)
    run_id = started["id"]
    await asyncio.sleep(0.4)
    cancelled = await service.cancel_run(run_id)
    assert cancelled["status"] == "cancelled"
    await asyncio.sleep(0.3)
    assert pool.active_run_for("TSLA") is None
    loaded = book.get_run(run_id)
    assert loaded is not None
    assert loaded["status"] == "cancelled"
    assert loaded["transcript"]  # partial kept


@pytest.mark.asyncio
async def test_failed_retry_starts_new(advise_iso, monkeypatch):
    monkeypatch.setattr(service, "session_key_et", lambda now=None: "2026-09-15")
    failed = book.create_run(
        symbol="AMD",
        model=advise_model_id(),
        graph_version=ADVISE_GRAPH_VERSION,
        depth=2,
        session_date="2026-09-15",
    )
    book.append_event(failed["id"], {"type": "message", "agent": "news", "content": "partial"})
    book.update_status(failed["id"], "failed", fail_reason="boom", finished=True)
    retried = await service.retry_run(failed["id"])
    assert retried["id"] != failed["id"]
    assert retried["symbol"] == "AMD"
    await service.cancel_run(retried["id"])
