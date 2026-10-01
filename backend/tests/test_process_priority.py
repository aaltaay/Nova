"""The API raises itself to Normal CPU, I/O and memory priority, whatever started it (2026-10-01)."""
from __future__ import annotations

import dataclasses
import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from process_priority.normal import (
    BELOW_NORMAL_PRIORITY_CLASS,
    IDLE_PRIORITY_CLASS,
    NORMAL_PRIORITY_CLASS,
    Priority,
    raise_to_normal,
)

ABOVE_NORMAL_PRIORITY_CLASS = 0x8000
_BACKEND = Path(__file__).resolve().parents[1]


class FakeNative:
    def __init__(self, priority: Priority, refuse: tuple[str, ...] = ()) -> None:
        self.priority = priority
        self.refuse = set(refuse)
        self.calls: list[tuple[str, int]] = []

    def read(self) -> Priority:
        return self.priority

    def _set(self, field: str, value: int) -> str | None:
        self.calls.append((field, value))
        if field in self.refuse:
            return "Win32 error 5"
        self.priority = dataclasses.replace(self.priority, **{field: value})
        return None

    def set_cpu_class(self, value: int) -> str | None:
        return self._set("cpu_class", value)

    def set_io(self, value: int) -> str | None:
        return self._set("io", value)

    def set_memory(self, value: int) -> str | None:
        return self._set("memory", value)


def test_task_scheduler_default_is_raised_on_all_three() -> None:
    # Task Scheduler's priority 7: BelowNormal CPU, Low I/O, memory 2 (the live API on 2026-10-01).
    native = FakeNative(Priority(BELOW_NORMAL_PRIORITY_CLASS, 1, 2))
    out = raise_to_normal(native)
    assert native.calls == [("cpu_class", NORMAL_PRIORITY_CLASS), ("io", 2), ("memory", 5)]
    assert out["before"]["text"] == "CPU BelowNormal, I/O Low, memory 2/5"
    assert out["after"]["text"] == "CPU Normal, I/O Normal, memory 5/5"
    assert out["refused"] == []


def test_a_below_normal_shell_passes_on_the_cpu_class_only() -> None:
    native = FakeNative(Priority(BELOW_NORMAL_PRIORITY_CLASS, 2, 5))
    raise_to_normal(native)
    assert native.calls == [("cpu_class", NORMAL_PRIORITY_CLASS)]


def test_idle_is_raised_too() -> None:
    native = FakeNative(Priority(IDLE_PRIORITY_CLASS, 0, 1))
    raise_to_normal(native)
    assert native.priority == Priority(NORMAL_PRIORITY_CLASS, 2, 5)


def test_normal_is_left_alone() -> None:
    native = FakeNative(Priority(NORMAL_PRIORITY_CLASS, 2, 5))
    out = raise_to_normal(native)
    assert native.calls == []
    assert out["before"] == out["after"]


def test_never_lowers() -> None:
    native = FakeNative(Priority(ABOVE_NORMAL_PRIORITY_CLASS, 3, 5))
    raise_to_normal(native)
    assert native.calls == []


def test_an_unread_value_is_not_touched() -> None:
    native = FakeNative(Priority(None, None, None))
    out = raise_to_normal(native)
    assert native.calls == []
    assert out["after"]["text"] == "CPU unknown, I/O unknown, memory unknown"


def test_a_refusal_is_said(caplog: pytest.LogCaptureFixture) -> None:
    native = FakeNative(Priority(BELOW_NORMAL_PRIORITY_CLASS, 1, 2), refuse=("io",))
    with caplog.at_level("INFO", logger="process_priority.normal"):
        out = raise_to_normal(native)
    assert out["refused"] == ["I/O priority (Win32 error 5)"]
    assert out["after"]["text"] == "CPU Normal, I/O Low, memory 5/5"
    assert any(r.levelname == "WARNING" and "refused I/O priority" in r.getMessage() for r in caplog.records)


def test_a_failed_read_never_raises() -> None:
    class Broken(FakeNative):
        def read(self) -> Priority:
            raise OSError("no access")

    out = raise_to_normal(Broken(Priority(None, None, None)))
    assert out == {"supported": True, "error": "no access"}


def test_off_windows_it_does_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    assert raise_to_normal() == {"supported": False}


@pytest.mark.skipif(sys.platform != "win32", reason="Windows scheduling priority")
def test_windows_raise_and_what_a_child_inherits() -> None:
    """A process started like a priority-7 task raises itself; a child it starts next is Normal."""
    child = textwrap.dedent(
        """
        import json, subprocess, sys
        from process_priority.normal import _WindowsNative, raise_to_normal
        native = _WindowsNative()
        native.set_io(1)
        native.set_memory(2)
        out = raise_to_normal()
        probe = "from process_priority.normal import _WindowsNative; print(_WindowsNative().read().text())"
        grandchild = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, check=True)
        print(json.dumps({"out": out, "grandchild": grandchild.stdout.strip()}))
        """
    )
    done = subprocess.run(
        [sys.executable, "-c", child],
        cwd=_BACKEND,
        capture_output=True,
        text=True,
        check=True,
        creationflags=subprocess.BELOW_NORMAL_PRIORITY_CLASS,
    )
    seen = json.loads(done.stdout.strip().splitlines()[-1])
    assert seen["out"]["before"]["text"] == "CPU BelowNormal, I/O Low, memory 2/5"
    assert seen["out"]["after"]["text"] == "CPU Normal, I/O Normal, memory 5/5"
    assert seen["grandchild"] == "CPU Normal, I/O Normal, memory 5/5"
