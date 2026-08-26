"""Single-instance API lock -- refuse a second live process."""
from __future__ import annotations

import os
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
