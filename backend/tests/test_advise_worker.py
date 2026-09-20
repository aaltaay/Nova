"""Advise worker: stub graph, cancel kills the process, retry from failed."""
from __future__ import annotations

import asyncio

import pytest

from advise import book, pool, service
from advise.engine import run_debate
from advise.worker_main import main as worker_main
from constants_advise import ADVISE_GRAPH_VERSION, advise_model_id

# Bounded waits, not fixed sleeps (#326). A fixed 0.4s "the stub has surely
# written a partial transcript by now" was a CPU-load lottery: under a
# concurrent full vitest run the spawned worker had written nothing yet and
# test_cancel_kills_slow_stub failed with `assert []`. Poll instead, so a slow
# machine waits longer and a fast one finishes sooner.
_WAIT_TIMEOUT_SEC = 10.0
_WAIT_POLL_SEC = 0.02


async def _wait_until(predicate, what: str, timeout: float = _WAIT_TIMEOUT_SEC):
    """Poll ``predicate`` until truthy; fail with a readable message on timeout."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while True:
        value = predicate()
        if value:
            return value
        if loop.time() >= deadline:
            raise AssertionError(f"timed out after {timeout:.1f}s waiting for {what}")
        await asyncio.sleep(_WAIT_POLL_SEC)


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
    usage = {}
    result = run_debate("AAPL", 2, events.append, usage_out=usage)
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
    assert usage["prompt_tokens"] > 0
    assert usage["completion_tokens"] > 0
    assert usage["actual_usd"] is not None
    assert usage["actual_usd"] > 0


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
    assert run["prompt_tokens"] > 0
    assert run["completion_tokens"] > 0
    assert run["actual_usd"] is not None
    assert run["actual_usd"] > 0

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
    await _wait_until(
        lambda: pool.active_run_for("IBM") is None,
        "the IBM pool slot to clear after cancel",
    )
    loaded = book.get_run(started["id"])
    assert loaded is not None
    assert loaded["status"] == "cancelled"


@pytest.mark.asyncio
async def test_cancel_kills_slow_stub(advise_iso, monkeypatch):
    monkeypatch.setenv("ADVISE_STUB_HANG_SEC", "20")
    monkeypatch.setattr(service, "session_key_et", lambda now=None: "2026-09-15")
    started = await service.start_run("TSLA", 2, force_refresh=True)
    run_id = started["id"]
    # Cancel only once the stub has actually written a partial transcript --
    # that partial surviving cancel is the whole point of the test.
    await _wait_until(
        lambda: (book.get_run(run_id) or {}).get("transcript"),
        f"run {run_id} to write a partial transcript",
    )
    cancelled = await service.cancel_run(run_id)
    assert cancelled["status"] == "cancelled"
    await _wait_until(
        lambda: pool.active_run_for("TSLA") is None,
        "the TSLA pool slot to clear after cancel",
    )
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


def test_stub_fail_records_partial_usage(advise_iso, monkeypatch):
    monkeypatch.setenv("ADVISE_STUB_SLEEP_SEC", "0")
    monkeypatch.setenv("ADVISE_STUB_FAIL_AFTER", "3")
    started = book.create_run(
        symbol="SPCX",
        model=advise_model_id(),
        graph_version=ADVISE_GRAPH_VERSION,
        depth=2,
        session_date="2026-09-16",
    )
    assert worker_main(["--run-id", str(started["id"])]) == 1
    run = book.get_run(started["id"])
    assert run is not None
    assert run["status"] == "failed"
    assert "ADVISE_STUB_FAIL_AFTER" in (run["fail_reason"] or "")
    assert run["transcript"]
    assert run["prompt_tokens"] > 0
    assert run["completion_tokens"] > 0
    assert run["actual_usd"] is not None
    assert run["actual_usd"] > 0
    monkeypatch.delenv("ADVISE_STUB_FAIL_AFTER", raising=False)
    complete_usage = {}
    run_debate("SPCX", 2, lambda _e: None, usage_out=complete_usage)
    assert run["prompt_tokens"] < complete_usage["prompt_tokens"]
    assert run["actual_usd"] < complete_usage["actual_usd"]
