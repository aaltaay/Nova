"""Single-instance API lock -- refuse a second live process."""
from __future__ import annotations

import os
import json
import subprocess
import sys

import pytest
from pathlib import Path

import api_instance_lock as lock


def test_pid_alive_sees_this_process():
    assert lock._pid_alive(os.getpid()) is True
    assert lock._pid_alive(0) is False
    assert lock._pid_alive(999_999_999) is False


def test_acquire_same_pid_is_idempotent(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("NOVA_CACHE_DIR", str(tmp_path))
    ok1, reason1 = lock.acquire()
    ok2, reason2 = lock.acquire()
    assert ok1 and reason1 == "ok"
    assert ok2 and reason2 == "ok"
    body = (tmp_path / lock.LOCK_NAME).read_text(encoding="utf-8")
    assert '"schema_version": 1' in body
    assert f'"pid": {os.getpid()}' in body


def test_acquire_refuses_live_foreign_pid(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("NOVA_CACHE_DIR", str(tmp_path))
    holder = os.getpid()
    (tmp_path / lock.LOCK_NAME).write_text(
        '{"schema_version": 1, "pid": %d, "parent_pid": 1, "argv0": "other"}\n'
        % holder,
        encoding="utf-8",
    )
    # Same PID is treated as re-entry, not a foreign holder. Use a fake
    # alive-check so the written pid looks like another process.
    monkeypatch.setattr(lock, "_pid_alive", lambda pid: pid == 424242)
    (tmp_path / lock.LOCK_NAME).write_text(
        '{"schema_version": 1, "pid": 424242, "parent_pid": 1, "argv0": "uvicorn"}\n',
        encoding="utf-8",
    )
    ok, detail = lock.acquire()
    assert ok is False
    assert "424242" in detail
    assert "clientId 17" in detail


def test_acquire_reclaims_dead_pid(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("NOVA_CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(lock, "_pid_alive", lambda _pid: False)
    (tmp_path / lock.LOCK_NAME).write_text(
        '{"schema_version": 1, "pid": 9, "parent_pid": 1, "argv0": "dead"}\n',
        encoding="utf-8",
    )
    ok, reason = lock.acquire()
    assert ok is True
    assert reason == "reclaimed"
    body = (tmp_path / lock.LOCK_NAME).read_text(encoding="utf-8")
    assert f'"pid": {os.getpid()}' in body


def test_unknown_schema_is_stale(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("NOVA_CACHE_DIR", str(tmp_path))
    (tmp_path / lock.LOCK_NAME).write_text(
        '{"schema_version": 99, "pid": 1}\n',
        encoding="utf-8",
    )
    ok, reason = lock.acquire()
    assert ok is True
    assert reason == "ok"


def test_classify_holder_ownership_rule():
    assert lock.classify_holder(alive=False, listening=False, age_sec=99) == "dead"
    assert lock.classify_holder(alive=True, listening=True, age_sec=99) == "healthy"
    assert lock.classify_holder(alive=True, listening=False, age_sec=1) == "starting"
    assert lock.classify_holder(alive=True, listening=False, age_sec=99) == "orphan"


def test_acquire_refuses_healthy_listener(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("NOVA_CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(lock, "_pid_alive", lambda pid: pid == 424242)
    monkeypatch.setattr(lock, "_port_listening", lambda host, port: True)
    (tmp_path / lock.LOCK_NAME).write_text(
        '{"schema_version": 1, "pid": 424242, "parent_pid": 1, '
        '"argv0": "uvicorn", "started_at": 1}\n',
        encoding="utf-8",
    )
    ok, detail = lock.acquire()
    assert ok is False
    assert "424242" in detail
    assert "clientId 17" in detail


def test_acquire_refuses_starting_dark_port(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("NOVA_CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(lock, "_pid_alive", lambda pid: pid == 7)
    monkeypatch.setattr(lock, "_port_listening", lambda host, port: False)
    monkeypatch.setattr(lock, "_holder_age_sec", lambda existing, path: 0.2)
    killed: list[int] = []
    monkeypatch.setattr(lock, "_terminate_pid", lambda pid: killed.append(pid))
    (tmp_path / lock.LOCK_NAME).write_text(
        '{"schema_version": 1, "pid": 7, "parent_pid": 1, "argv0": "run_api"}\n',
        encoding="utf-8",
    )
    ok, detail = lock.acquire()
    assert ok is False
    assert killed == []
    assert "still starting" in detail


def test_acquire_terminates_orphan_then_reclaims(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("NOVA_CACHE_DIR", str(tmp_path))
    alive = {9: True}

    def pid_alive(pid: int) -> bool:
        return alive.get(pid, False)

    def terminate(pid: int) -> None:
        alive[pid] = False

    monkeypatch.setattr(lock, "_pid_alive", pid_alive)
    monkeypatch.setattr(lock, "_port_listening", lambda host, port: False)
    monkeypatch.setattr(lock, "_holder_age_sec", lambda existing, path: 30.0)
    monkeypatch.setattr(lock, "_terminate_pid", terminate)
    (tmp_path / lock.LOCK_NAME).write_text(
        '{"schema_version": 1, "pid": 9, "parent_pid": 1, "argv0": "orphan"}\n',
        encoding="utf-8",
    )
    ok, reason = lock.acquire()
    assert ok is True
    assert reason == "reclaimed"
    body = (tmp_path / lock.LOCK_NAME).read_text(encoding="utf-8")
    assert f'"pid": {os.getpid()}' in body
    assert '"started_at"' in body


def test_acquire_refuses_if_orphan_kill_fails(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("NOVA_CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(lock, "_pid_alive", lambda pid: pid == 11)
    monkeypatch.setattr(lock, "_port_listening", lambda host, port: False)
    monkeypatch.setattr(lock, "_holder_age_sec", lambda existing, path: 30.0)
    monkeypatch.setattr(lock, "_terminate_pid", lambda pid: None)
    (tmp_path / lock.LOCK_NAME).write_text(
        '{"schema_version": 1, "pid": 11, "parent_pid": 1, "argv0": "stuck"}\n',
        encoding="utf-8",
    )
    ok, detail = lock.acquire()
    assert ok is False
    assert "still alive" in detail
    assert "clientId 17" in detail


@pytest.fixture(autouse=True)
def release_test_guard():
    lock.reset_for_testing()
    yield
    lock.reset_for_testing()


_CHILD = """
import json, sys, time
import api_instance_lock as lock
original_read = lock._read_lock
def widened_read(path):
    value = original_read(path)
    time.sleep(0.2)  # widen the old read/write race without weakening the OS guard
    return value
lock._read_lock = widened_read
sys.stdin.readline()
print(json.dumps(lock.acquire()), flush=True)
sys.stdin.readline()  # keep the winning handle alive until the parent ends the process
"""


def _contender(cache):
    return subprocess.Popen(
        [sys.executable, "-c", _CHILD], cwd=Path(lock.__file__).parent,
        env={**os.environ, "NOVA_CACHE_DIR": str(cache)},
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True,
    )


def _start_contender(child):
    child.stdin.write("go\n")
    child.stdin.flush()


def _end_contender(child):
    if child.poll() is None:
        child.kill()
    child.communicate(timeout=10)


def test_concurrent_processes_cannot_both_claim_and_death_releases_guard(tmp_path):
    children = [_contender(tmp_path), _contender(tmp_path)]
    try:
        for child in children:
            _start_contender(child)
        results = [json.loads(child.stdout.readline()) for child in children]
        assert sorted(result[0] for result in results) == [False, True]
        winner = children[next(i for i, result in enumerate(results) if result[0])]
        # Destroy diagnostic metadata while a live process holds the guard: still exclusive.
        (tmp_path / lock.LOCK_NAME).write_text('{"schema_version": 99}')
        late = _contender(tmp_path)
        children.append(late)
        _start_contender(late)
        assert json.loads(late.stdout.readline())[0] is False
        _end_contender(winner)
        fresh = _contender(tmp_path)
        children.append(fresh)
        _start_contender(fresh)
        assert json.loads(fresh.stdout.readline())[0] is True
    finally:
        for child in children:
            _end_contender(child)


def test_metadata_write_failure_refuses_and_releases_guard(tmp_path, monkeypatch):
    monkeypatch.setenv("NOVA_CACHE_DIR", str(tmp_path))
    with monkeypatch.context() as patch:
        def full_disk(*args, **kwargs):
            raise OSError("disk full")
        patch.setattr(Path, "write_text", full_disk)
        ok, detail = lock.acquire()
        assert not ok and "disk full" in detail
    assert lock.acquire()[0] is True
