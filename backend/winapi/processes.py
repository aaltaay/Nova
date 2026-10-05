"""The Windows process list, read in-process (Toolhelp32), and a process's command line and start time.

``snapshot()`` costs a few milliseconds and starts nothing; ``command_line(pid)`` and
``created_at(pid)`` open the process for limited query only. A process that has exited, or one
Windows will not open (another user's, a protected one), reads None -- never a guess.
"""
from __future__ import annotations

import ctypes
import logging
from ctypes import wintypes
from dataclasses import dataclass

from winapi import available

logger = logging.getLogger(__name__)

TH32CS_SNAPPROCESS = 0x00000002
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
PROCESS_COMMAND_LINE_INFORMATION = 60          # NtQueryInformationProcess class (Windows 8.1+)
STATUS_INFO_LENGTH_MISMATCH = 0xC0000004
MAX_PATH = 260


@dataclass(frozen=True)
class Proc:
    pid: int
    ppid: int
    name: str          # the image name, e.g. ``java.exe``


class _ProcessEntry32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.c_size_t),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", ctypes.c_wchar * MAX_PATH),
    ]


class _UnicodeString(ctypes.Structure):
    _fields_ = [
        ("Length", wintypes.USHORT),
        ("MaximumLength", wintypes.USHORT),
        ("Buffer", ctypes.c_void_p),
    ]


_kernel32 = None
_ntdll = None


def _libs():
    global _kernel32, _ntdll
    if _kernel32 is None:
        k = ctypes.WinDLL("kernel32", use_last_error=True)
        k.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
        k.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        k.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_ProcessEntry32W)]
        k.Process32FirstW.restype = wintypes.BOOL
        k.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_ProcessEntry32W)]
        k.Process32NextW.restype = wintypes.BOOL
        k.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        k.OpenProcess.restype = wintypes.HANDLE
        k.CloseHandle.argtypes = [wintypes.HANDLE]
        k.CloseHandle.restype = wintypes.BOOL
        k.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
        k.GetProcessTimes.restype = wintypes.BOOL
        n = ctypes.WinDLL("ntdll")
        n.NtQueryInformationProcess.argtypes = [
            wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.ULONG, ctypes.POINTER(wintypes.ULONG),
        ]
        n.NtQueryInformationProcess.restype = ctypes.c_long
        _kernel32, _ntdll = k, n
    return _kernel32, _ntdll


_INVALID_HANDLE = ctypes.c_void_p(-1).value


def snapshot() -> list[Proc]:
    """Every process now: pid, parent pid and image name. Empty off Windows; OSError when Windows refuses."""
    if not available():
        return []
    k, _ = _libs()
    handle = k.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if not handle or handle == _INVALID_HANDLE:
        raise ctypes.WinError(ctypes.get_last_error())
    out: list[Proc] = []
    try:
        entry = _ProcessEntry32W()
        entry.dwSize = ctypes.sizeof(_ProcessEntry32W)
        ok = k.Process32FirstW(handle, ctypes.byref(entry))
        while ok:
            out.append(Proc(int(entry.th32ProcessID), int(entry.th32ParentProcessID), entry.szExeFile))
            ok = k.Process32NextW(handle, ctypes.byref(entry))
    finally:
        k.CloseHandle(handle)
    return out


def _open_query(pid: int):
    k, _ = _libs()
    handle = k.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
    return handle or None


def command_line(pid: int) -> str | None:
    """The process's command line, or None when it cannot be read. Never log it: it can hold secrets."""
    if not available():
        return None
    k, n = _libs()
    handle = _open_query(pid)
    if handle is None:
        return None
    try:
        size = wintypes.ULONG(0)
        status = n.NtQueryInformationProcess(handle, PROCESS_COMMAND_LINE_INFORMATION, None, 0, ctypes.byref(size))
        if (status & 0xFFFFFFFF) != STATUS_INFO_LENGTH_MISMATCH or not size.value:
            return None
        buf = ctypes.create_string_buffer(size.value)
        status = n.NtQueryInformationProcess(
            handle, PROCESS_COMMAND_LINE_INFORMATION, buf, size.value, ctypes.byref(size)
        )
        if status != 0:
            return None
        text = ctypes.cast(buf, ctypes.POINTER(_UnicodeString)).contents
        if not text.Buffer or not text.Length:
            return ""
        return ctypes.wstring_at(text.Buffer, text.Length // 2)
    finally:
        k.CloseHandle(handle)


def created_at(pid: int) -> float | None:
    """When the process started (epoch seconds), or None when Windows will not say."""
    if not available():
        return None
    k, _ = _libs()
    handle = _open_query(pid)
    if handle is None:
        return None
    try:
        times = [wintypes.FILETIME() for _ in range(4)]
        if not k.GetProcessTimes(handle, *(ctypes.byref(t) for t in times)):
            return None
        ticks = (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime
        return ticks / 1e7 - 11644473600.0   # FILETIME counts 100 ns from 1601
    finally:
        k.CloseHandle(handle)
