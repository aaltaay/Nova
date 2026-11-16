"""Test helper: pytest keeps the scheduling priority it started with (#1244, #1079).

In-process, the API's pid is pytest's own. The trading-path keeper (ADR 045) that one booted app started raised
pytest to Above Normal every 2 s, and its socket-loop raise lifted pytest's main thread, for the rest of the run
(#1244); the builds' ``below_normal`` called in-process lowered pytest instead, and Windows passes a lowered class on
to every child it starts (#1079). The suite's autouse guard (``conftest._hold_pytest_priority``) reads both after
every test, puts back what moved and fails that test. Off Windows there is nothing to read.
"""
from __future__ import annotations

import ctypes
from dataclasses import dataclass

from winapi import available
from winapi.priority import CLASS_NAMES

_THREAD_PRIORITY_ERROR_RETURN = 0x7FFFFFFF      # GetThreadPriority's failure value (MAXLONG)
_THREAD_NAMES = {-15: "Idle", -2: "Lowest", -1: "BelowNormal", 0: "Normal", 1: "AboveNormal", 2: "Highest",
                 15: "TimeCritical"}

_kernel32 = None


@dataclass(frozen=True)
class Held:
    """pytest's CPU priority class, and its main thread's priority within that class."""

    cpu_class: int
    main_thread: int

    def text(self) -> str:
        cpu = CLASS_NAMES.get(self.cpu_class, hex(self.cpu_class))
        return f"CPU class {cpu}, main thread {_THREAD_NAMES.get(self.main_thread, str(self.main_thread))}"


def _k32():
    global _kernel32
    if _kernel32 is None:
        from ctypes import wintypes

        k = ctypes.WinDLL("kernel32", use_last_error=True)
        k.GetCurrentProcess.argtypes = []
        k.GetCurrentProcess.restype = wintypes.HANDLE
        k.GetCurrentThread.argtypes = []
        k.GetCurrentThread.restype = wintypes.HANDLE
        k.GetPriorityClass.argtypes = [wintypes.HANDLE]
        k.GetPriorityClass.restype = wintypes.DWORD
        k.SetPriorityClass.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        k.SetPriorityClass.restype = wintypes.BOOL
        k.GetThreadPriority.argtypes = [wintypes.HANDLE]
        k.GetThreadPriority.restype = ctypes.c_int
        k.SetThreadPriority.argtypes = [wintypes.HANDLE, ctypes.c_int]
        k.SetThreadPriority.restype = wintypes.BOOL
        _kernel32 = k
    return _kernel32


def read() -> Held | None:
    """pytest's priority now, read on its main thread; None off Windows, or when Windows will not say."""
    if not available():
        return None
    k = _k32()
    cpu_class = k.GetPriorityClass(k.GetCurrentProcess())
    main_thread = k.GetThreadPriority(k.GetCurrentThread())
    if not cpu_class or main_thread == _THREAD_PRIORITY_ERROR_RETURN:
        return None
    return Held(cpu_class, main_thread)


def move_to(held: Held) -> bool:
    """Set pytest's class and its main thread's priority (on the main thread); True when Windows took both."""
    k = _k32()
    cpu_ok = bool(k.SetPriorityClass(k.GetCurrentProcess(), held.cpu_class))
    thread_ok = bool(k.SetThreadPriority(k.GetCurrentThread(), held.main_thread))
    return cpu_ok and thread_ok


def put_back(start: Held | None) -> str | None:
    """When pytest's priority has moved from ``start``: put it back, and say how it moved. None when it has not."""
    if start is None:
        return None
    now = read()
    if now is None or now == start:
        return None
    outcome = "put back" if move_to(start) else f"Windows refused to put it back ({ctypes.get_last_error()})"
    return (
        f"pytest's own priority moved from {start.text()} to {now.text()} during this test, its fixtures, or a "
        f"thread an earlier test left running; {outcome}. In-process, an app a test boots and a worker's own "
        "priority drop change pytest itself (#1244, #1079)."
    )
