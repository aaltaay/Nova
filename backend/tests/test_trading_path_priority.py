"""The trading path stays above background work, and a freeze names itself (ADR 045).

2026-10-05: the API logged "CPU Normal" at 14:17:12 and read BelowNormal minutes later, as did the IB
Gateway, beside an ASUS game booster that ran explorer.exe BelowNormal; at 08:31 an 8.8 s freeze of the
whole backend left no stack.
"""
from __future__ import annotations

import ctypes
import sys
import time

import pytest

from diagnostics import collect_priority
from perf.freeze_watch import FreezeWatch, freeze_record
from process_priority import trading_path as tp
from winapi import priority as pr


class _FakeWindows:
    """Priority reads and raises on fake pids; ``lower(pid)`` is the game booster."""

    def __init__(self) -> None:
        self.cpu: dict[int, int] = {}
        self.raised: list[tuple[int, int, bool]] = []

    def read(self, pid):
        cpu = self.cpu.get(pid)
        return None if cpu is None else pr.Priority(cpu, pr.IO_NORMAL, pr.MEMORY_NORMAL)

    def raise_to(self, pid, cpu, *, power_unthrottle=False):
        self.raised.append((pid, cpu, power_unthrottle))
        if pr.below(self.cpu.get(pid), cpu):
            self.cpu[pid] = cpu
        return []


@pytest.fixture
def windows(monkeypatch):
    fake = _FakeWindows()
    monkeypatch.setattr(pr, "read", fake.read)
    monkeypatch.setattr(pr, "raise_to", fake.raise_to)
    tp.reset_for_tests()
    yield fake
    tp.reset_for_tests()


def _track(monkeypatch, items):
    monkeypatch.setattr(tp, "_discover", lambda: [tp._Tracked(**i) for i in items])


def test_the_api_and_gateway_are_raised_and_a_later_demotion_is_counted(monkeypatch, windows, caplog):
    windows.cpu = {100: pr.BELOW_NORMAL, 200: pr.NORMAL}
    _track(monkeypatch, [
        dict(role="api", pid=100, name="api", target=pr.ABOVE_NORMAL, unthrottle=True),
        dict(role="gateway", pid=200, name="java.exe", target=pr.ABOVE_NORMAL),
    ])
    tp.check_once(now=0.0)
    assert windows.cpu == {100: pr.ABOVE_NORMAL, 200: pr.ABOVE_NORMAL}
    assert (100, pr.ABOVE_NORMAL, True) in windows.raised          # the API also leaves power throttling
    assert all(p["raised"] == 0 for p in tp.view()["processes"])     # raising at start is not a demotion

    windows.cpu[100] = pr.BELOW_NORMAL                              # something on the PC lowers it
    with caplog.at_level("WARNING", logger=tp.__name__):
        tp.check_once(now=2.0)
    assert windows.cpu[100] == pr.ABOVE_NORMAL
    api = next(p for p in tp.view()["processes"] if p["role"] == "api")
    assert api["raised"] == 1 and api["priority"] == "AboveNormal"
    assert "lowered" in caplog.text


def test_nothing_is_ever_lowered_and_an_exited_gateway_is_dropped(monkeypatch, windows):
    windows.cpu = {100: pr.HIGH, 200: pr.ABOVE_NORMAL}
    _track(monkeypatch, [
        dict(role="api", pid=100, name="api", target=pr.ABOVE_NORMAL, unthrottle=True),
        dict(role="gateway", pid=200, name="java.exe", target=pr.ABOVE_NORMAL),
    ])
    tp.check_once(now=0.0)
    assert windows.cpu[100] == pr.HIGH and windows.raised == []
    del windows.cpu[200]                                            # the Gateway exited
    tp.check_once(now=2.0)
    assert [p["role"] for p in tp.view()["processes"]] == ["api"]


def test_the_checklist_row_says_what_lowered_the_trading_path():
    base = {"enabled": True, "running": True, "checked_at": 1.0}
    ok = collect_priority.priority_rows(view={**base, "processes": [
        {"role": "api", "pid": 1, "name": "api", "priority": "AboveNormal", "raised": 0, "error": None}]})
    assert ok[0]["state"] == "ok"
    warn = collect_priority.priority_rows(view={**base, "processes": [
        {"role": "api", "pid": 1, "name": "api", "priority": "AboveNormal", "raised": 7, "error": None}]})
    assert warn[0]["state"] == "warn" and "7 times" in warn[0]["detail"]
    fail = collect_priority.priority_rows(view={**base, "processes": [
        {"role": "gateway", "pid": 2, "name": "java.exe", "priority": "BelowNormal", "raised": 0, "error": None}]})
    assert fail[0]["state"] == "fail"
    off = collect_priority.priority_rows(view={"enabled": False, "processes": []})
    assert off[0]["state"] == "off"


def test_a_freeze_is_recorded_with_where_its_stacks_are():
    record = freeze_record(armed_at=100.0, noticed_at=108.8, file="2026-10-05.txt", offset=4096)
    assert record == {"schema_version": 1, "armed_at": 100.0, "noticed_at": 108.8, "frozen_sec": 8.8,
                      "file": "2026-10-05.txt", "offset": 4096}
    now = 200.0
    rows = collect_priority.freeze_rows(status={"running": True, "count": 1, "last": {**record, "noticed_at": 190.0}},
                                        now=now)
    assert rows[0]["state"] == "fail" and "byte 4096" in rows[0]["fix"]
    calm = collect_priority.freeze_rows(status={"running": True, "count": 0, "last": None}, now=now)
    assert calm[0]["state"] == "ok"


@pytest.mark.skipif(sys.platform != "win32", reason="holds the GIL through a Windows call")
def test_a_whole_process_freeze_writes_every_threads_stack(tmp_path):
    """Hold Python's lock for 1.5 s, as one long call did at 08:31: the C watchdog writes the stacks."""
    watch = FreezeWatch(tmp_path, dump_sec=0.5, rearm_sec=0.1)
    watch.start()
    try:
        time.sleep(0.3)
        ctypes.PyDLL("kernel32").Sleep(1500)    # a PyDLL call keeps the GIL (a CDLL call would release it)
        time.sleep(0.4)
    finally:
        watch.stop()
    assert watch.count >= 1
    assert watch.last()["frozen_sec"] >= 1.0
    dumped = (tmp_path / "freezes" / watch.last()["file"]).read_text(encoding="utf-8")
    assert "Timeout" in dumped and "test_a_whole_process_freeze_writes_every_threads_stack" in dumped
