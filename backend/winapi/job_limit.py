"""A hard cap on this process's committed memory: a Windows job object with ``JOB_OBJECT_LIMIT_PROCESS_MEMORY``.

Past the cap Windows refuses the allocation (``MemoryError`` in Python), so a reader that keeps
what it reads fails its own work instead of taking the PC's memory from the API, IB Gateway and
the desk (2026-10-11: a day-file reader under test held 8.3 GB and grew ~2 MB/s with the PC at
72 of 80 GB committed). For a worker whose failure costs only its own job, never the API, which
must never be ended by a limit.

The job lives as long as the process (its handle is kept here, never closed). Windows 8 and later
nest jobs, so the cap holds inside a job the process already belongs to (a terminal's, Electron's).
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes

from winapi import available

JOB_OBJECT_EXTENDED_LIMIT_INFORMATION_CLASS = 9
JOB_OBJECT_LIMIT_PROCESS_MEMORY = 0x00000100


class _BasicLimits(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_longlong),
        ("PerJobUserTimeLimit", ctypes.c_longlong),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]


class _IoCounters(ctypes.Structure):
    _fields_ = [(name, ctypes.c_ulonglong) for name in (
        "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
        "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]


class _ExtendedLimits(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _BasicLimits),
        ("IoInfo", _IoCounters),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


_job = None     # the job's handle, kept open for the life of the process


def cap_this_process(limit_bytes: int) -> bool:
    """Cap this process's committed memory at ``limit_bytes``. True when the cap holds, False off Windows.

    Raises ``OSError`` when Windows refuses to create, set or join the job; the caller says so
    and runs uncapped, never guesses that it is capped. A second call replaces the first cap.
    """
    global _job
    if not available():
        return False
    if limit_bytes <= 0:
        raise ValueError("the memory cap must be above zero")
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    k.CreateJobObjectW.restype = wintypes.HANDLE
    k.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    k.SetInformationJobObject.restype = wintypes.BOOL
    k.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    k.AssignProcessToJobObject.restype = wintypes.BOOL
    k.GetCurrentProcess.restype = wintypes.HANDLE
    k.CloseHandle.argtypes = [wintypes.HANDLE]
    k.CloseHandle.restype = wintypes.BOOL
    job = _job or k.CreateJobObjectW(None, None)
    if not job:
        raise ctypes.WinError(ctypes.get_last_error())
    limits = _ExtendedLimits()
    limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_PROCESS_MEMORY
    limits.ProcessMemoryLimit = int(limit_bytes)
    if not k.SetInformationJobObject(job, JOB_OBJECT_EXTENDED_LIMIT_INFORMATION_CLASS, ctypes.byref(limits),
                                     ctypes.sizeof(limits)):
        error = ctypes.WinError(ctypes.get_last_error())
        if _job is None:
            k.CloseHandle(job)
        raise error
    if _job is None:
        if not k.AssignProcessToJobObject(job, k.GetCurrentProcess()):
            error = ctypes.WinError(ctypes.get_last_error())
            k.CloseHandle(job)
            raise error
        _job = job
    return True
