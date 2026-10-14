"""A short setup's five-year result is never read from disk on a caller's thread once it was read (operator
report 2026-10-14): the setup board re-read the five files on the request loop every 30 s, and on a busy
drive that froze the loop an order runs on for 230 to 830 ms."""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pytest

from constants_bot import BOT_SHORT_SETUPS
from constants_short_setups import SHORT_TESTS_CACHE_SEC
from setup_scanner import short_tests

SETUP = "bear_flag"


def _write(state: str, setup: str = SETUP) -> None:
    folder = short_tests.folder()
    folder.mkdir(parents=True, exist_ok=True)
    body = {"schema_version": 1, "setup": setup, "state": state, "passed": None, "updated_at": time.time(),
            "progress": None, "main": None, "criteria": None}
    (folder / f"{setup}.json").write_text(json.dumps(body), encoding="utf-8")


@pytest.fixture(autouse=True)
def fresh():
    short_tests.reset_for_tests()
    yield
    short_tests.reset_for_tests()


@pytest.fixture
def slow_disk(monkeypatch):
    """The result file's reads wait until the test lets them go; every read is counted."""
    gate, reads = threading.Event(), []
    real = Path.read_text

    def read_text(self, *args, **kwargs):
        if self.name == f"{SETUP}.json":
            reads.append(time.monotonic())
            assert gate.wait(10), "the test never let the read go"
        return real(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", read_text)
    return gate, reads


def _wait_until(check, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while not check():
        assert time.monotonic() < deadline, "timed out"
        time.sleep(0.01)


def test_a_result_read_before_answers_at_once_while_the_disk_is_slow(slow_disk):
    gate, reads = slow_disk
    _write("running")
    gate.set()
    now = time.time()
    assert short_tests.test(SETUP, None, now=now)["state"] == "running"   # this process's first read
    gate.clear()
    _write("failed")
    later = now + SHORT_TESTS_CACHE_SEC + 1
    started = time.monotonic()
    assert short_tests.test(SETUP, None, now=later)["state"] == "running"  # the last read, at once
    assert short_tests.test(SETUP, None, now=later)["state"] == "running"
    assert time.monotonic() - started < 1.0
    _wait_until(lambda: len(reads) == 2)                                   # one thread reads it again
    gate.set()
    _wait_until(lambda: short_tests.test(SETUP, None, now=later)["state"] == "error")  # failed without passed
    assert len(reads) == 2


def test_a_fresh_read_is_not_read_again(slow_disk):
    gate, reads = slow_disk
    gate.set()
    _write("running")
    now = time.time()
    short_tests.test(SETUP, None, now=now)
    short_tests.test(SETUP, None, now=now + SHORT_TESTS_CACHE_SEC - 1)
    time.sleep(0.05)
    assert len(reads) == 1


def test_a_read_again_that_breaks_keeps_the_last_read(monkeypatch, caplog):
    _write("running")
    now = time.time()
    assert short_tests.test(SETUP, None, now=now)["state"] == "running"

    def broken(self, *args, **kwargs):
        raise RuntimeError("disk gone mid-read")

    monkeypatch.setattr(Path, "read_text", broken)
    later = now + SHORT_TESTS_CACHE_SEC + 1
    with caplog.at_level("ERROR", logger="setup_scanner.short_tests"):
        assert short_tests.test(SETUP, None, now=later)["state"] == "running"
        _wait_until(lambda: "could not be read again" in caplog.text)
    _wait_until(lambda: SETUP not in short_tests._reading)
    assert short_tests.test(SETUP, None, now=later)["state"] == "running"


def test_warm_reads_every_short_setup_once(monkeypatch):
    reads: list[str] = []
    real = Path.read_text

    def read_text(self, *args, **kwargs):
        reads.append(self.stem)
        return real(self, *args, **kwargs)

    _write("running")
    monkeypatch.setattr(Path, "read_text", read_text)
    short_tests.warm()
    assert sorted(reads) == sorted(BOT_SHORT_SETUPS)
    now = time.time()
    assert short_tests.test(SETUP, None, now=now)["state"] == "running"
    assert short_tests.test("lost_vwap", None, now=now)["state"] == "queued"   # no file: queued, not re-read
    assert len(reads) == len(BOT_SHORT_SETUPS)
