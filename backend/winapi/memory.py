"""This process's page faults and working set (``GetProcessMemoryInfo``), for the perf recorder (ADR 045)."""
from __future__ import annotations

import ctypes
from ctypes import wintypes

from winapi import available


class _Counters(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("PageFaultCount", wintypes.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]


_fn = None


def process_memory() -> tuple[int | None, int | None]:
    """``(page faults since the process started, working set bytes)``; ``(None, None)`` off Windows."""
    global _fn
    if not available():
        return None, None
    if _fn is None:
        k = ctypes.WinDLL("kernel32", use_last_error=True)
        k.GetCurrentProcess.restype = wintypes.HANDLE
        fn = k.K32GetProcessMemoryInfo
        fn.argtypes = [wintypes.HANDLE, ctypes.POINTER(_Counters), wintypes.DWORD]
        fn.restype = wintypes.BOOL
        _fn = (k.GetCurrentProcess, fn)
    counters = _Counters()
    counters.cb = ctypes.sizeof(_Counters)
    if not _fn[1](_fn[0](), ctypes.byref(counters), counters.cb):
        return None, None
    return int(counters.PageFaultCount), int(counters.WorkingSetSize)
