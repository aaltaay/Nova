"""Memory as Windows reports it: this process's (``GetProcessMemoryInfo``), the PC's (``GlobalMemoryStatusEx``)
and another process's private bytes, for the perf recorder (ADR 045) and the memory watch.

Private bytes are the memory a process has committed for itself -- what a leak grows -- and
are never trimmed. The working set is what is in RAM right now; Windows trims it under
pressure, so it can read 211 MB for a process holding 1.9 GB (the API, 2026-10-11 01:15).
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes

from winapi import available

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


class _Counters(ctypes.Structure):
    """``PROCESS_MEMORY_COUNTERS_EX``: the classic counters plus ``PrivateUsage``."""

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
        ("PrivateUsage", ctypes.c_size_t),
    ]


class _MemoryStatus(ctypes.Structure):
    _fields_ = [
        ("dwLength", wintypes.DWORD),
        ("dwMemoryLoad", wintypes.DWORD),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


_k = None


def _kernel32():
    global _k
    if _k is None:
        k = ctypes.WinDLL("kernel32", use_last_error=True)
        k.GetCurrentProcess.restype = wintypes.HANDLE
        k.K32GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(_Counters), wintypes.DWORD]
        k.K32GetProcessMemoryInfo.restype = wintypes.BOOL
        k.GlobalMemoryStatusEx.argtypes = [ctypes.POINTER(_MemoryStatus)]
        k.GlobalMemoryStatusEx.restype = wintypes.BOOL
        k.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        k.OpenProcess.restype = wintypes.HANDLE
        k.CloseHandle.argtypes = [wintypes.HANDLE]
        k.CloseHandle.restype = wintypes.BOOL
        _k = k
    return _k


def _counters(handle) -> _Counters | None:
    counters = _Counters()
    counters.cb = ctypes.sizeof(_Counters)
    if not _kernel32().K32GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
        return None
    return counters


def process_memory() -> tuple[int | None, int | None]:
    """``(page faults since the process started, working set bytes)``; ``(None, None)`` off Windows."""
    if not available():
        return None, None
    counters = _counters(_kernel32().GetCurrentProcess())
    if counters is None:
        return None, None
    return int(counters.PageFaultCount), int(counters.WorkingSetSize)


def private_bytes(pid: int) -> int | None:
    """A process's private bytes, or None when Windows will not open it (a protected or exited process)."""
    if not available():
        return None
    k = _kernel32()
    handle = k.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
    if not handle:
        return None
    try:
        counters = _counters(handle)
        return int(counters.PrivateUsage) if counters is not None else None
    finally:
        k.CloseHandle(handle)


def pc_memory() -> dict[str, int] | None:
    """The PC's memory now, or None off Windows (or when Windows will not say).

    ``load_pct`` is Windows' own share of RAM in use (Task Manager's Memory %); the commit
    charge is what every process has committed, and an allocation fails, in any process,
    once it reaches the limit (RAM plus the page file).
    """
    if not available():
        return None
    status = _MemoryStatus()
    status.dwLength = ctypes.sizeof(_MemoryStatus)
    if not _kernel32().GlobalMemoryStatusEx(ctypes.byref(status)):
        return None
    mb = 2**20
    return {
        "load_pct": int(status.dwMemoryLoad),
        "ram_total_mb": int(status.ullTotalPhys // mb),
        "ram_free_mb": int(status.ullAvailPhys // mb),
        "commit_limit_mb": int(status.ullTotalPageFile // mb),
        "commit_used_mb": int((status.ullTotalPageFile - status.ullAvailPageFile) // mb),
    }
