"""Raise this process to Normal CPU, I/O and memory priority on Windows; never lower one.

A process-level change reaches the threads that already exist. That was checked on the desk PC on
2026-10-01: a thread started before the change read the new I/O and memory priority after it. Every
thread and child process created afterwards starts from the new values, so the IB Gateway that the
API launches inherits them too. Off Windows this does nothing.
"""
from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from typing import Any, Protocol

logger = logging.getLogger(__name__)

# GetPriorityClass / SetPriorityClass values.
IDLE_PRIORITY_CLASS = 0x40
BELOW_NORMAL_PRIORITY_CLASS = 0x4000
NORMAL_PRIORITY_CLASS = 0x20
# ProcessIoPriority: 0 very low, 1 low, 2 normal, 3 high. ProcessMemoryPriority: 1 very low .. 5 normal.
IO_PRIORITY_NORMAL = 2
MEMORY_PRIORITY_NORMAL = 5
# Information classes: NtQuery/SetInformationProcess and Get/SetProcessInformation.
_PROCESS_IO_PRIORITY = 33
_PROCESS_MEMORY_PRIORITY = 0

_CLASS_NAMES = {
    IDLE_PRIORITY_CLASS: "Idle",
    BELOW_NORMAL_PRIORITY_CLASS: "BelowNormal",
    NORMAL_PRIORITY_CLASS: "Normal",
    0x8000: "AboveNormal",
    0x80: "High",
    0x100: "RealTime",
}
_IO_NAMES = {0: "VeryLow", 1: "Low", 2: "Normal", 3: "High", 4: "Critical"}


@dataclass(frozen=True)
class Priority:
    """One reading; ``None`` where Windows would not say."""

    cpu_class: int | None
    io: int | None
    memory: int | None

    def low(self) -> bool:
        return (
            self.cpu_class in (IDLE_PRIORITY_CLASS, BELOW_NORMAL_PRIORITY_CLASS)
            or (self.io is not None and self.io < IO_PRIORITY_NORMAL)
            or (self.memory is not None and self.memory < MEMORY_PRIORITY_NORMAL)
        )

    def text(self) -> str:
        cpu = "unknown" if self.cpu_class is None else _CLASS_NAMES.get(self.cpu_class, hex(self.cpu_class))
        io = "unknown" if self.io is None else _IO_NAMES.get(self.io, str(self.io))
        memory = "unknown" if self.memory is None else f"{self.memory}/5"
        return f"CPU {cpu}, I/O {io}, memory {memory}"

    def as_dict(self) -> dict[str, Any]:
        return {"cpu_class": self.cpu_class, "io": self.io, "memory": self.memory, "text": self.text()}


class Native(Protocol):
    """The calls on this process; each setter returns what Windows refused, or None."""

    def read(self) -> Priority: ...

    def set_cpu_class(self, value: int) -> str | None: ...

    def set_io(self, value: int) -> str | None: ...

    def set_memory(self, value: int) -> str | None: ...


class _WindowsNative:
    def __init__(self) -> None:
        import ctypes
        from ctypes import wintypes

        self._ctypes = ctypes
        self._k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._nt = ctypes.WinDLL("ntdll")
        k32, nt = self._k32, self._nt
        k32.GetCurrentProcess.restype = wintypes.HANDLE
        k32.GetPriorityClass.argtypes = [wintypes.HANDLE]
        k32.GetPriorityClass.restype = wintypes.DWORD
        k32.SetPriorityClass.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        k32.SetPriorityClass.restype = wintypes.BOOL
        for name in ("GetProcessInformation", "SetProcessInformation"):
            fn = getattr(k32, name)
            fn.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
            fn.restype = wintypes.BOOL
        nt.NtQueryInformationProcess.argtypes = [
            wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.ULONG, ctypes.c_void_p,
        ]
        nt.NtQueryInformationProcess.restype = ctypes.c_long
        nt.NtSetInformationProcess.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.ULONG]
        nt.NtSetInformationProcess.restype = ctypes.c_long
        self._process = k32.GetCurrentProcess()

    def read(self) -> Priority:
        ctypes = self._ctypes
        cpu_class = self._k32.GetPriorityClass(self._process)
        io = ctypes.c_ulong(0)
        io_ok = self._nt.NtQueryInformationProcess(
            self._process, _PROCESS_IO_PRIORITY, ctypes.byref(io), ctypes.sizeof(io), None,
        ) == 0
        memory = ctypes.c_ulong(0)
        memory_ok = self._k32.GetProcessInformation(
            self._process, _PROCESS_MEMORY_PRIORITY, ctypes.byref(memory), ctypes.sizeof(memory),
        )
        return Priority(
            cpu_class=cpu_class or None,
            io=io.value if io_ok else None,
            memory=memory.value if memory_ok else None,
        )

    def set_cpu_class(self, value: int) -> str | None:
        if self._k32.SetPriorityClass(self._process, value):
            return None
        return f"Win32 error {self._ctypes.get_last_error()}"

    def set_io(self, value: int) -> str | None:
        target = self._ctypes.c_ulong(value)
        status = self._nt.NtSetInformationProcess(
            self._process, _PROCESS_IO_PRIORITY, self._ctypes.byref(target), self._ctypes.sizeof(target),
        )
        return None if status == 0 else f"NTSTATUS 0x{status & 0xFFFFFFFF:08X}"

    def set_memory(self, value: int) -> str | None:
        target = self._ctypes.c_ulong(value)
        if self._k32.SetProcessInformation(
            self._process, _PROCESS_MEMORY_PRIORITY, self._ctypes.byref(target), self._ctypes.sizeof(target),
        ):
            return None
        return f"Win32 error {self._ctypes.get_last_error()}"


def raise_to_normal(native: Native | None = None) -> dict[str, Any]:
    """Raise a BelowNormal or Idle CPU class, and an I/O or memory priority under normal, to Normal.

    Returns ``{"supported": False}`` off Windows, else ``{"supported": True, "before", "after",
    "refused"}``. Logs one line; never raises.
    """
    if native is None:
        if sys.platform != "win32":
            return {"supported": False}
        try:
            native = _WindowsNative()
        except Exception as exc:
            logger.warning("process priority: cannot read it (%s)", exc)
            return {"supported": True, "error": str(exc)}
    try:
        before = native.read()
        refused: list[str] = []
        if before.cpu_class in (IDLE_PRIORITY_CLASS, BELOW_NORMAL_PRIORITY_CLASS):
            err = native.set_cpu_class(NORMAL_PRIORITY_CLASS)
            if err:
                refused.append(f"CPU class ({err})")
        if before.io is not None and before.io < IO_PRIORITY_NORMAL:
            err = native.set_io(IO_PRIORITY_NORMAL)
            if err:
                refused.append(f"I/O priority ({err})")
        if before.memory is not None and before.memory < MEMORY_PRIORITY_NORMAL:
            err = native.set_memory(MEMORY_PRIORITY_NORMAL)
            if err:
                refused.append(f"memory priority ({err})")
        after = native.read() if before.low() else before
    except Exception as exc:
        logger.warning("process priority: unchanged (%s)", exc, exc_info=True)
        return {"supported": True, "error": str(exc)}
    if refused or after.low():
        logger.warning(
            "process priority: %s -> %s; Windows refused %s",
            before.text(), after.text(), "; ".join(refused) or "nothing, yet it reads low",
        )
    elif before.low():
        logger.info("process priority: raised %s -> %s", before.text(), after.text())
    else:
        logger.info("process priority: %s", after.text())
    return {"supported": True, "before": before.as_dict(), "after": after.as_dict(), "refused": refused}
