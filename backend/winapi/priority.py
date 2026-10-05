"""A process's CPU priority class, I/O and memory priority, power throttling, and a thread's priority (Windows).

Mirrors ``scripts/NovaProcessPriority.ps1`` (the same calls, measured on the desk) in-process:
``read`` never changes anything; ``raise_to`` only ever raises and returns what Windows refused.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass

from winapi import available

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
PROCESS_SET_INFORMATION = 0x0200
IO_PRIORITY_CLASS = 33          # ProcessIoPriority (NtQuery / NtSetInformationProcess)
MEMORY_PRIORITY_CLASS = 0       # ProcessMemoryPriority (Get / SetProcessInformation)
POWER_THROTTLING_CLASS = 4      # ProcessPowerThrottling (SetProcessInformation)
POWER_THROTTLING_VERSION = 1
POWER_THROTTLING_EXECUTION_SPEED = 0x1
POWER_THROTTLING_IGNORE_TIMER_RESOLUTION = 0x4
THREAD_PRIORITY_ABOVE_NORMAL = 1

IDLE = 0x40
BELOW_NORMAL = 0x4000
NORMAL = 0x20
ABOVE_NORMAL = 0x8000
HIGH = 0x80
REALTIME = 0x100
IO_NORMAL = 2                   # 0 very low, 1 low, 2 normal, 3 high
MEMORY_NORMAL = 5               # 1 very low .. 5 normal

CLASS_NAMES = {IDLE: "Idle", BELOW_NORMAL: "BelowNormal", NORMAL: "Normal",
               ABOVE_NORMAL: "AboveNormal", HIGH: "High", REALTIME: "RealTime"}
_CLASS_RANK = {IDLE: 0, BELOW_NORMAL: 1, NORMAL: 2, ABOVE_NORMAL: 3, HIGH: 4, REALTIME: 5}


@dataclass(frozen=True)
class Priority:
    """``cpu`` a priority class (``CLASS_NAMES``), ``io`` 0-4, ``memory`` 1-5; None where Windows would not say."""

    cpu: int | None
    io: int | None
    memory: int | None

    @property
    def cpu_name(self) -> str:
        return CLASS_NAMES.get(self.cpu or -1, "unknown") if self.cpu is not None else "unknown"


def below(cpu: int | None, target: int) -> bool:
    """``cpu`` ranks under ``target`` (an unknown class never does)."""
    return cpu is not None and _CLASS_RANK.get(cpu, 99) < _CLASS_RANK[target]


class _PowerThrottlingState(ctypes.Structure):
    _fields_ = [("Version", wintypes.ULONG), ("ControlMask", wintypes.ULONG), ("StateMask", wintypes.ULONG)]


_kernel32 = None
_ntdll = None


def _libs():
    global _kernel32, _ntdll
    if _kernel32 is None:
        k = ctypes.WinDLL("kernel32", use_last_error=True)
        k.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        k.OpenProcess.restype = wintypes.HANDLE
        k.CloseHandle.argtypes = [wintypes.HANDLE]
        k.CloseHandle.restype = wintypes.BOOL
        k.GetPriorityClass.argtypes = [wintypes.HANDLE]
        k.GetPriorityClass.restype = wintypes.DWORD
        k.SetPriorityClass.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        k.SetPriorityClass.restype = wintypes.BOOL
        k.GetProcessInformation.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        k.GetProcessInformation.restype = wintypes.BOOL
        k.SetProcessInformation.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        k.SetProcessInformation.restype = wintypes.BOOL
        k.GetCurrentThread.argtypes = []
        k.GetCurrentThread.restype = wintypes.HANDLE
        k.SetThreadPriority.argtypes = [wintypes.HANDLE, ctypes.c_int]
        k.SetThreadPriority.restype = wintypes.BOOL
        k.GetThreadPriority.argtypes = [wintypes.HANDLE]
        k.GetThreadPriority.restype = ctypes.c_int
        n = ctypes.WinDLL("ntdll")
        n.NtQueryInformationProcess.argtypes = [
            wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.ULONG, ctypes.c_void_p,
        ]
        n.NtQueryInformationProcess.restype = ctypes.c_long
        n.NtSetInformationProcess.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.ULONG]
        n.NtSetInformationProcess.restype = ctypes.c_long
        _kernel32, _ntdll = k, n
    return _kernel32, _ntdll


def _open(pid: int, access: int):
    k, _ = _libs()
    return k.OpenProcess(access, False, int(pid)) or None


def _read_handle(handle) -> Priority:
    k, n = _libs()
    cls = k.GetPriorityClass(handle)
    io = ctypes.c_ulong(0)
    mem = ctypes.c_ulong(0)
    io_ok = n.NtQueryInformationProcess(handle, IO_PRIORITY_CLASS, ctypes.byref(io), 4, None) == 0
    mem_ok = bool(k.GetProcessInformation(handle, MEMORY_PRIORITY_CLASS, ctypes.byref(mem), 4))
    return Priority(cls or None, io.value if io_ok else None, mem.value if mem_ok else None)


def read(pid: int) -> Priority | None:
    """The process's priority now, or None when Windows will not open it (or off Windows)."""
    if not available():
        return None
    k, _ = _libs()
    handle = _open(pid, PROCESS_QUERY_LIMITED_INFORMATION)
    if handle is None:
        return None
    try:
        return _read_handle(handle)
    finally:
        k.CloseHandle(handle)


def raise_to(pid: int, cpu: int, *, power_unthrottle: bool = False) -> list[str]:
    """Raise the process to at least ``cpu`` and to normal I/O and memory priority; never lower one.

    With ``power_unthrottle`` it also opts the process out of Windows power throttling (EcoQoS).
    Returns what Windows refused, as words (empty when all held). Off Windows: nothing to raise.
    """
    if not available():
        return []
    k, n = _libs()
    handle = _open(pid, PROCESS_QUERY_LIMITED_INFORMATION | PROCESS_SET_INFORMATION)
    if handle is None:
        return [f"cannot open the process (Win32 error {ctypes.get_last_error()})"]
    refused: list[str] = []
    try:
        now = _read_handle(handle)
        if below(now.cpu, cpu) and not k.SetPriorityClass(handle, cpu):
            refused.append(f"CPU class (Win32 error {ctypes.get_last_error()})")
        if now.io is not None and now.io < IO_NORMAL:
            target = ctypes.c_ulong(IO_NORMAL)
            status = n.NtSetInformationProcess(handle, IO_PRIORITY_CLASS, ctypes.byref(target), 4)
            if status != 0:
                refused.append(f"I/O priority (NTSTATUS 0x{status & 0xFFFFFFFF:08X})")
        if now.memory is not None and now.memory < MEMORY_NORMAL:
            target = ctypes.c_ulong(MEMORY_NORMAL)
            if not k.SetProcessInformation(handle, MEMORY_PRIORITY_CLASS, ctypes.byref(target), 4):
                refused.append(f"memory priority (Win32 error {ctypes.get_last_error()})")
        if power_unthrottle:
            state = _PowerThrottlingState(
                POWER_THROTTLING_VERSION,
                POWER_THROTTLING_EXECUTION_SPEED | POWER_THROTTLING_IGNORE_TIMER_RESOLUTION,
                0,
            )
            if not k.SetProcessInformation(handle, POWER_THROTTLING_CLASS, ctypes.byref(state),
                                           ctypes.sizeof(state)):
                refused.append(f"power throttling (Win32 error {ctypes.get_last_error()})")
    finally:
        k.CloseHandle(handle)
    return refused


def raise_current_thread() -> bool:
    """Raise the calling thread to Above Normal within its process; True when it now is (or higher)."""
    if not available():
        return False
    k, _ = _libs()
    handle = k.GetCurrentThread()
    if k.GetThreadPriority(handle) >= THREAD_PRIORITY_ABOVE_NORMAL:
        return True
    return bool(k.SetThreadPriority(handle, THREAD_PRIORITY_ABOVE_NORMAL))
