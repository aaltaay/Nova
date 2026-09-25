"""The checkout's revision on disk now: what a restart would load (operator report 2026-09-25).

A Reload at 07:56 ET came up v1017 again because the checkout itself was v1017 until a pull
at 07:57. The reader behind /api/health ``checkout_tag`` must say what is on disk without
ever making the HTTP loop wait on git.
"""
from __future__ import annotations

import subprocess
import threading
import time

import pytest

from diagnostics import checkout_revision
from diagnostics.checkout_revision import CheckoutRevision
from diagnostics.process_info import read_checkout_tag


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def _never_read() -> str | None:
    raise AssertionError("a fresh answer must not read git")


def test_a_fresh_answer_is_served_without_reading_git():
    spawned: list = []
    reader = CheckoutRevision("v1017", _never_read, ttl_sec=10, clock=_Clock(), spawn=spawned.append)
    assert reader.current() == "v1017"
    assert spawned == []


def test_a_stale_answer_starts_one_reread_and_the_next_reader_sees_it():
    clock, spawned = _Clock(), []
    reader = CheckoutRevision("v1017", lambda: "v1024", ttl_sec=10, clock=clock, spawn=spawned.append)
    clock.now = 11
    # The caller gets the last answer at once; the re-read runs elsewhere, once.
    assert reader.current() == "v1017"
    assert reader.current() == "v1017"
    assert len(spawned) == 1
    spawned[0]()
    assert reader.current() == "v1024"
    assert len(spawned) == 1, "a fresh answer starts no second re-read"


def test_a_failed_reread_is_unknown_never_the_old_answer_passed_off_as_now():
    clock, spawned = _Clock(), []

    def broken() -> str | None:
        raise OSError("git vanished")

    reader = CheckoutRevision("v1017", broken, ttl_sec=10, clock=clock, spawn=spawned.append)
    clock.now = 11
    reader.current()
    spawned[0]()
    assert reader.current() is None


def test_a_reader_never_waits_on_a_slow_git():
    release = threading.Event()
    reads: list[str] = []

    def slow() -> str | None:
        release.wait(5)
        reads.append("read")
        return "v1024"

    clock = _Clock()
    reader = CheckoutRevision("v1017", slow, ttl_sec=10, clock=clock)
    clock.now = 11
    started = time.monotonic()
    assert reader.current() == "v1017"
    assert time.monotonic() - started < 1.0, "the caller waited on git"
    release.set()
    deadline = time.monotonic() + 5
    while not reads and time.monotonic() < deadline:
        time.sleep(0.01)
    deadline = time.monotonic() + 5
    while reader.current() != "v1024" and time.monotonic() < deadline:
        time.sleep(0.01)
    assert reader.current() == "v1024"


def test_a_reread_that_cannot_start_waits_for_the_next_interval(caplog):
    clock = _Clock()
    calls = {"spawn": 0}

    def refuse(_fn) -> None:
        calls["spawn"] += 1
        raise RuntimeError("can't start new thread")

    reader = CheckoutRevision("v1017", _never_read, ttl_sec=10, clock=clock, spawn=refuse)
    clock.now = 11
    assert reader.current() == "v1017"
    assert reader.current() == "v1017"
    assert calls["spawn"] == 1, "a refused start must not retry on every request"
    assert "could not start a re-read" in caplog.text
    clock.now = 22
    reader.current()
    assert calls["spawn"] == 2


def test_a_packaged_engine_has_no_checkout(monkeypatch):
    monkeypatch.setattr(checkout_revision, "_FROZEN", True)
    assert checkout_revision.checkout_tag() is None


def _git(cwd, *args: str) -> None:
    subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True)


def test_the_checkout_revision_is_its_commit_count(tmp_path):
    try:
        _git(tmp_path, "init", "-q")
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("git is not available")
    _git(tmp_path, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "one")
    assert read_checkout_tag(tmp_path) == "v1"
    _git(tmp_path, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "two")
    assert read_checkout_tag(tmp_path) == "v2", "a pull moves the checkout; the reader follows the disk"


def test_a_folder_git_cannot_read_has_no_revision(tmp_path):
    assert read_checkout_tag(tmp_path / "not-a-repo") is None
