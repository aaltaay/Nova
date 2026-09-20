"""Real recorder regression: blocked disk must not block the API event loop."""
from __future__ import annotations

import asyncio
import json
import threading
from pathlib import Path

import pytest

from capture import bar_buckets, bridge_sim, mode, recorder, session_state, worker

WAIT_SECONDS = 5.0


@pytest.fixture(autouse=True)
def isolated_capture(tmp_path, monkeypatch):
    monkeypatch.setenv("NOVA_SIM_CAPTURE_DIR", str(tmp_path))
    mode.set_capture_mode(False)
    recorder.reset_for_tests()
    session_state.reset_for_tests()
    bar_buckets.reset_for_tests()
    mode.reset_for_tests()
    yield tmp_path
    mode.set_capture_mode(False)
    recorder.reset_for_tests()
    bar_buckets.reset_for_tests()
    mode.reset_for_tests()


def _tick(price: float) -> None:
    bridge_sim.emit_sim_tick(
        {"time": "2026-09-18T14:00:01Z", "price": price, "size": 2},
        {"last": price},
        None,
    )


def _prints(path: Path) -> list[dict]:
    return [json.loads(line) for line in (path / "prints.jsonl").read_text().splitlines()]


def _block_print(monkeypatch):
    entered, release = threading.Event(), threading.Event()
    original = recorder.record_print

    def slow_print(payload):
        entered.set()
        assert release.wait(WAIT_SECONDS), "test failed to release blocked disk"
        original(payload)

    monkeypatch.setattr(recorder, "record_print", slow_print)
    return entered, release


def test_slow_write_keeps_loop_live_and_stop_drains_in_order(monkeypatch):
    mode.set_capture_mode(True, symbol="SIM1")
    directory = Path(recorder.status()["dir"])
    entered, release = _block_print(monkeypatch)

    async def exercise():
        try:
            _tick(10)
            assert await asyncio.to_thread(entered.wait, WAIT_SECONDS)
            _tick(11)
            stop = asyncio.create_task(asyncio.to_thread(mode.set_capture_mode, False))
            # An independently scheduled coroutine completes while disk is blocked.
            heartbeat = asyncio.Event()
            asyncio.get_running_loop().call_soon(heartbeat.set)
            await asyncio.wait_for(heartbeat.wait(), WAIT_SECONDS)
            assert not stop.done(), "Stop must wait for accepted rows to drain"
            release.set()
            result = await asyncio.wait_for(stop, WAIT_SECONDS)
            assert result["capture"] is False
        finally:
            release.set()

    asyncio.run(exercise())
    assert [row["price"] for row in _prints(directory)] == [10, 11]
    manifest = json.loads((directory / "manifest.json").read_text())
    assert manifest["counts"]["prints"] == 2
    assert manifest["status"] == "stopped_partial_ok"
    assert manifest["counts"]["bars_10s"] == 1


def test_session_switch_drains_old_rows_without_cross_contamination(monkeypatch):
    mode.set_capture_mode(True, symbol="SIM1")
    old_dir = Path(recorder.status()["dir"])
    entered, release = _block_print(monkeypatch)

    async def exercise():
        try:
            _tick(10)
            assert await asyncio.to_thread(entered.wait, WAIT_SECONDS)
            switch = asyncio.create_task(
                asyncio.to_thread(mode.set_capture_mode, True, symbol="OTHER")
            )
            await asyncio.sleep(0)
            release.set()
            await asyncio.wait_for(switch, WAIT_SECONDS)
        finally:
            release.set()

    asyncio.run(exercise())
    new_dir = Path(recorder.status()["dir"])
    mode.set_capture_mode(False)
    assert len(_prints(old_dir)) == 1
    assert _prints(new_dir) == []
    assert bar_buckets._buckets == {}


def test_overflow_reports_immediately_then_drains_and_marks_failed(monkeypatch):
    monkeypatch.setattr(worker, "CAPTURE_PENDING_BATCHES", 2)
    mode.set_capture_mode(True, symbol="SIM1")
    directory = Path(recorder.status()["dir"])
    entered, release = _block_print(monkeypatch)
    try:
        _tick(10)
        assert entered.wait(WAIT_SECONDS)
        _tick(11)
        _tick(12)
        status = mode.status_payload()
        assert "backlog full" in status["error"]
        assert status["writer"]["pending_batches"] == 2
        assert status["writer"]["accepting"] is False
    finally:
        release.set()
    mode.set_capture_mode(False)
    assert [row["price"] for row in _prints(directory)] == [10, 11]
    manifest = json.loads((directory / "manifest.json").read_text())
    assert manifest["status"] == "failed"
    assert "backlog full" in recorder.status()["error"]
    assert worker.status()["pending_batches"] == 0
    # Starting a fresh session clears the worker error and opens ingress again.
    status = mode.set_capture_mode(True, symbol="NEW")
    assert "error" not in status
    assert status["writer"]["accepting"] is True


def test_sync_lifecycle_refuses_event_loop_thread():
    async def exercise():
        with pytest.raises(RuntimeError, match="asyncio.to_thread"):
            mode.set_capture_mode(True, symbol="SIM1")

    asyncio.run(exercise())
    assert not recorder.is_recording()


def test_enqueue_copies_payload_before_caller_mutation(monkeypatch):
    mode.set_capture_mode(True, symbol="SIM1")
    directory = Path(recorder.status()["dir"])
    entered, release = _block_print(monkeypatch)
    try:
        _tick(10)
        assert entered.wait(WAIT_SECONDS)
        payload = {"time": "2026-09-18T14:00:02Z", "price": 11, "size": 2}
        bridge_sim.emit_sim_tick(payload, None, None)
        payload["price"] = 999
    finally:
        release.set()
    mode.set_capture_mode(False)
    assert [row["price"] for row in _prints(directory)] == [10, 11]


@pytest.mark.parametrize("next_symbol", ["OTHER", "SIM1"])
def test_late_old_batch_is_rejected_after_session_switch(next_symbol):
    mode.set_capture_mode(True, symbol="SIM1")
    token = worker.session_token("SIM1")
    mode.set_capture_mode(True, symbol=next_symbol)
    assert not worker.submit(recorder.record_print, {"price": 99}, token=token)
    assert recorder.status()["counts"]["prints"] == 0


def test_batch_exception_finalizes_failure_and_worker_can_restart(monkeypatch):
    mode.set_capture_mode(True, symbol="SIM1")

    def broken_batch(*_args):
        raise RuntimeError("bad capture batch")

    monkeypatch.setattr(bridge_sim, "_write_sim_tick", broken_batch)
    _tick(10)
    mode.set_capture_mode(False)
    assert "bad capture batch" in recorder.status()["error"]
    assert "bad capture batch" in mode.status_payload()["error"]
    assert mode.set_capture_mode(True, symbol="NEW")["capture"] is True


def test_async_app_shutdown_waits_off_loop_for_recorder(monkeypatch):
    import app_lifespan
    from fastapi import FastAPI

    mode.set_capture_mode(True, symbol="SIM1")
    entered, release = threading.Event(), threading.Event()
    original = recorder.stop_recorder

    def slow_stop():
        entered.set()
        assert release.wait(WAIT_SECONDS), "shutdown test did not release disk"
        original()

    async def no_bootstrap():
        await asyncio.Event().wait()

    monkeypatch.setattr(recorder, "stop_recorder", slow_stop)
    monkeypatch.setattr(app_lifespan, "_bootstrap_runtime", no_bootstrap)

    async def run_lifespan():
        async with app_lifespan.lifespan(FastAPI()):
            pass

    async def exercise():
        shutdown = asyncio.create_task(run_lifespan())
        try:
            assert await asyncio.to_thread(entered.wait, WAIT_SECONDS)
            heartbeat = asyncio.Event()
            asyncio.get_running_loop().call_soon(heartbeat.set)
            await asyncio.wait_for(heartbeat.wait(), WAIT_SECONDS)
            assert not shutdown.done()
        finally:
            release.set()
        await asyncio.wait_for(shutdown, WAIT_SECONDS)

    asyncio.run(exercise())
    assert not recorder.is_recording()
