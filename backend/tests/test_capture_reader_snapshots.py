"""Recorder readers stay responsive while real stream I/O is blocked (#674)."""
from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from datetime import date, timedelta
from pathlib import Path

import pytest

from capture import bar_buckets, bridge_ibkr, manifest_io, mode, recorder, session_state

WAIT_SECONDS = 5.0
FALLBACK_RELEASE_SECONDS = 0.35
SYMBOL = "BLOCK"
SIBLING = "OTHER"


@pytest.fixture(autouse=True)
def isolated_capture(monkeypatch):
    monkeypatch.setattr(bridge_ibkr, "producer_health", lambda symbol: {
        "state": "receiving", "healthy": True, "last_print_ts": None, "error": None,
    })
    mode.set_capture_mode(False)
    recorder.reset_for_tests()
    session_state.reset_for_tests()
    bar_buckets.reset_for_tests()
    mode.reset_for_tests()
    yield
    mode.set_capture_mode(False)
    recorder.reset_for_tests()
    bar_buckets.reset_for_tests()
    mode.reset_for_tests()


def print_row(symbol=SYMBOL, *, offset=0.0):
    return {"symbol": symbol, "ts": time.time() + offset, "price": 10, "size": 100}


def block_fsync(monkeypatch):
    entered, release = threading.Event(), threading.Event()
    original = recorder.os.fsync
    blocked = False

    def fsync(fd):
        nonlocal blocked
        if not blocked:
            blocked = True
            entered.set()
            assert release.wait(WAIT_SECONDS), "blocked fsync was not released"
        return original(fd)

    monkeypatch.setattr(recorder.os, "fsync", fsync)
    return entered, release


def test_stop_fsync_cannot_stall_status_or_loop_and_leaves_sibling_recording(monkeypatch):
    mode.set_capture_mode(True, symbol=SYMBOL)
    mode.set_capture_mode(True, symbol=SIBLING)
    recorder.record_print(print_row())
    recorder.record_print(print_row(SIBLING))
    directory = Path(recorder.status(SYMBOL)["dir"])
    entered, release = block_fsync(monkeypatch)

    async def exercise():
        stop = asyncio.create_task(asyncio.to_thread(recorder.stop_recorder, symbol=SYMBOL))
        timer = threading.Timer(FALLBACK_RELEASE_SECONDS, release.set)
        try:
            assert await asyncio.to_thread(entered.wait, WAIT_SECONDS)
            timer.start()  # bounds the old synchronous-reader regression too
            heartbeat = asyncio.Event()
            asyncio.get_running_loop().call_soon(heartbeat.set)
            started = time.monotonic()
            payload = mode.status_payload()
            elapsed = time.monotonic() - started
            assert not release.is_set(), f"status waited {elapsed:.3f}s behind stop fsync"
            await asyncio.wait_for(heartbeat.wait(), WAIT_SECONDS)
            assert not release.is_set(), "status starved the independent loop heartbeat"
            assert payload["capture_symbols"] == [SIBLING]
            assert recorder.recording_symbols() == [SIBLING]
            assert not recorder.is_recording(SYMBOL) and recorder.is_recording(SIBLING)
            assert recorder.last_error(SYMBOL) is None
            assert not stop.done(), "stop must finish its accepted disk writes"
            assert recorder._lock.acquire(blocking=False), "fsync held the shared state lock"
            recorder._lock.release()
        finally:
            release.set()
            timer.cancel()
            await asyncio.wait_for(stop, WAIT_SECONDS)
            if timer.ident is not None:
                timer.join(WAIT_SECONDS)

    asyncio.run(exercise())
    terminal = recorder.status(SYMBOL)
    manifest = json.loads((directory / "manifest.json").read_text())
    assert terminal["counts"]["prints"] == manifest["counts"]["prints"] == 1
    assert terminal["error"] is None and manifest["status"] == "stopped_partial_ok"
    assert mode.capture_symbols() == [SIBLING]


def test_rotation_keeps_published_active_segment_until_replacement_is_ready(monkeypatch):
    mode.set_capture_mode(True, symbol=SYMBOL)
    recorder.record_print(print_row())
    original = recorder.status(SYMBOL)
    next_day = (date.fromisoformat(original["session_date"]) + timedelta(days=1)).isoformat()
    entered, release = block_fsync(monkeypatch)

    async def exercise():
        rotate = asyncio.create_task(asyncio.to_thread(recorder.start_recorder, SYMBOL, session_date=next_day))
        timer = threading.Timer(FALLBACK_RELEASE_SECONDS, release.set)
        try:
            assert await asyncio.to_thread(entered.wait, WAIT_SECONDS)
            timer.start()
            during = recorder.status(SYMBOL)
            assert during["recording"], "rotation exposed its half-closed live session"
            assert during["session_date"] == original["session_date"]
            assert during["counts"]["prints"] == 1 and during["error"] is None
            assert mode.status_payload()["capture_symbols"] == [SYMBOL]
            assert not release.is_set(), "rotation blocked the state reader"
        finally:
            release.set()
            timer.cancel()
            await asyncio.wait_for(rotate, WAIT_SECONDS)
            if timer.ident is not None:
                timer.join(WAIT_SECONDS)

    asyncio.run(exercise())
    after = recorder.status(SYMBOL)
    assert after["recording"] and after["session_date"] == next_day
    assert after["counts"]["prints"] == 0 and after["error"] is None
    assert mode.capture_symbols() == [SYMBOL]


def test_reader_payloads_cannot_mutate_published_counts_or_tape_errors():
    recorder.start_recorder(SYMBOL)
    recorder.record_print(print_row())
    recorder.note_tape(SYMBOL, loss={"at": time.time(), "cause": "stale", "detail": "missing tape"})
    payload = recorder.status()
    payload["sessions"][SYMBOL]["counts"]["prints"] = 999
    payload["fidelity"]["tape_losses"][0]["detail"] = "invented"
    current = recorder.status(SYMBOL)
    assert current["counts"]["prints"] == 1
    assert current["fidelity"]["tape_losses"][0]["detail"] == "missing tape"
    later_loss = {"at": time.time(), "cause": "ib_error", "detail": "later loss"}
    recorder.note_tape(SYMBOL, loss=later_loss)
    later_loss["detail"] = "caller mutated its input"
    recorder.record_print(print_row(offset=1))
    after = recorder.status(SYMBOL)
    assert [row["detail"] for row in after["fidelity"]["tape_losses"]] == ["missing tape", "later loss"]
    assert len(current["fidelity"]["tape_losses"]) == 1  # the prior pinned response stays unchanged


def test_slow_row_fsync_keeps_reader_counts_and_timestamp_at_one_committed_prefix(monkeypatch):
    mode.set_capture_mode(True, symbol=SYMBOL)
    first = print_row()
    recorder.record_print(first)
    recorder._primary().last_fsync_mono = 0  # the next row must fsync
    entered, release = block_fsync(monkeypatch)

    async def exercise():
        write = asyncio.create_task(asyncio.to_thread(recorder.record_print, {**first, "ts": first["ts"] + 1}))
        timer = threading.Timer(FALLBACK_RELEASE_SECONDS, release.set)
        try:
            assert await asyncio.to_thread(entered.wait, WAIT_SECONDS)
            timer.start()
            during = recorder.status(SYMBOL)
            assert during["recording"] and during["counts"]["prints"] == 1
            assert during["fidelity"]["last_stream_ts"]["prints"] == first["ts"]
            assert mode.status_payload()["capture_symbols"] == [SYMBOL]
            assert not release.is_set(), "the row writer blocked a status poll"
        finally:
            release.set()
            timer.cancel()
            await asyncio.wait_for(write, WAIT_SECONDS)
            if timer.ident is not None:
                timer.join(WAIT_SECONDS)

    asyncio.run(exercise())
    after = recorder.status(SYMBOL)
    assert after["counts"]["prints"] == 2
    assert after["fidelity"]["last_stream_ts"]["prints"] == first["ts"] + 1


def test_a_start_queued_behind_stop_owns_the_replacement_after_finalization(monkeypatch):
    recorder.start_recorder(SYMBOL)
    first = print_row()
    recorder.record_print(first)
    directory = Path(recorder.status(SYMBOL)["dir"])
    entered, release = block_fsync(monkeypatch)

    async def exercise():
        stop = asyncio.create_task(asyncio.to_thread(recorder.stop_recorder, symbol=SYMBOL))
        start = None
        try:
            assert await asyncio.to_thread(entered.wait, WAIT_SECONDS)
            start = asyncio.create_task(asyncio.to_thread(recorder.start_recorder, SYMBOL))
            await asyncio.sleep(0)
            assert not recorder.is_recording(SYMBOL)
            assert not start.done()
        finally:
            release.set()
            await asyncio.wait_for(stop, WAIT_SECONDS)
            if start is not None:
                await asyncio.wait_for(start, WAIT_SECONDS)

    asyncio.run(exercise())
    assert recorder.is_recording(SYMBOL)
    assert recorder.status(SYMBOL)["counts"]["prints"] == 1
    recorder.record_print({**first, "ts": first["ts"] + 1})
    recorder.stop_recorder(symbol=SYMBOL)
    manifest = json.loads((directory / "manifest.json").read_text())
    assert manifest["counts"]["prints"] == 2
    assert [segment["counts"]["prints"] for segment in manifest["segments"]] == [1, 1]


def test_failed_start_closes_partial_streams_publishes_error_and_preserves_sibling(monkeypatch):
    recorder.start_recorder(SIBLING)
    original = Path.open
    opened = []

    def open_stream(path, *args, **kwargs):
        if path.parent.name == SYMBOL and path.name == "quotes.jsonl":
            raise OSError("quotes stream unavailable")
        handle = original(path, *args, **kwargs)
        if path.parent.name == SYMBOL and path.name == "prints.jsonl":
            opened.append(handle)
        return handle

    with monkeypatch.context() as patch:
        patch.setattr(Path, "open", open_stream)
        with pytest.raises(OSError, match="quotes stream unavailable"):
            recorder.start_recorder(SYMBOL)
    assert opened and all(handle.closed for handle in opened)
    assert not recorder.is_recording(SYMBOL) and recorder.is_recording(SIBLING)
    assert "quotes stream unavailable" in recorder.last_error(SYMBOL)
    assert recorder.status(SYMBOL)["counts"]["prints"] == 0
    assert recorder.status(SIBLING)["error"] is None
    recorder.start_recorder(SYMBOL)
    assert recorder.is_recording(SYMBOL) and recorder.last_error(SYMBOL) is None


def test_empty_segment_logs_received_prints_without_inventing_write_failures(caplog):
    recorder.start_recorder(SYMBOL)
    with caplog.at_level(logging.ERROR, logger="capture.recorder"):
        recorder.stop_recorder(symbol=SYMBOL)
    assert "No IBKR prints received" in caplog.text
    assert "0 consecutive write failures" not in caplog.text
    assert recorder.status(SYMBOL)["write_failures"] == 0


def test_failed_stop_fsync_closes_all_streams_and_persists_failed_counts(monkeypatch):
    recorder.start_recorder(SYMBOL)
    recorder.record_print(print_row())
    directory = Path(recorder.status(SYMBOL)["dir"])
    handles = list(recorder._primary().files.values())
    original = recorder.os.fsync
    failed = False

    def fsync(fd):
        nonlocal failed
        if not failed:
            failed = True
            raise OSError("stop fsync unavailable")
        return original(fd)

    monkeypatch.setattr(recorder.os, "fsync", fsync)
    recorder.stop_recorder(symbol=SYMBOL)
    terminal = recorder.status(SYMBOL)
    manifest = json.loads((directory / "manifest.json").read_text())
    assert all(handle.closed for handle in handles)
    assert not terminal["recording"]
    assert "stop fsync unavailable" in (terminal["error"] or "")
    assert manifest["status"] == "failed" and manifest["error"] == terminal["error"]
    assert manifest["counts"]["prints"] == terminal["counts"]["prints"] == 1


def test_failed_terminal_manifest_keeps_recovery_marker_and_retries_without_duplicate_rows(monkeypatch):
    recorder.start_recorder(SYMBOL)
    recorder.record_print(print_row())
    directory = Path(recorder.status(SYMBOL)["dir"])
    handles = list(recorder._primary().files.values())
    original = manifest_io.write_json_atomic

    def fail_manifest(path, payload):
        if path.name == "manifest.json":
            raise OSError("terminal manifest unavailable")
        return original(path, payload)

    with monkeypatch.context() as patch:
        patch.setattr(manifest_io, "write_json_atomic", fail_manifest)
        recorder.stop_recorder(symbol=SYMBOL)
        with pytest.raises(OSError, match="terminal manifest unavailable"):
            recorder.start_recorder(SYMBOL)  # never append against stale terminal counts
    terminal = recorder.status(SYMBOL)
    assert not terminal["recording"] and all(handle.closed for handle in handles)
    assert "terminal manifest unavailable" in terminal["error"]
    marker = session_state.read_active(directory.parent.parent)
    assert [row["symbol"] for row in session_state.active_rows(marker)] == [SYMBOL]
    recorder.stop_recorder(symbol=SYMBOL)  # complete the same segment, without reopening streams
    manifest = json.loads((directory / "manifest.json").read_text())
    assert manifest["status"] == "failed" and manifest["error"] == terminal["error"]
    assert manifest["counts"]["prints"] == 1 and len(manifest["segments"]) == 1
    assert session_state.read_active(directory.parent.parent) == {}
