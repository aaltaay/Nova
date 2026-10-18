"""Run control every Massive archive job shares: the archive log, the STOP file, CPU priority, the free-memory hold,
the orphan check, and one copy of a job at a time.

Create ``<NOVA_MARKET_DATA_DIR>/STOP`` to make every job stop after the file in hand. There are no quiet hours (the
operator removed them on 2026-10-02: "when I ask you to do something, you do it immediately, unless I tell you
explicitly to stop or pause").
"""
from __future__ import annotations

import ctypes
import sys
import time
from datetime import datetime

from massive_env import NY, ROOT

LOG = ROOT / "archive.log"
STOP = ROOT / "STOP"
MIN_FREE_RAM_GB = 3.0                    # a worker holds its next day while the PC has less free memory than this


def idle_priority() -> None:
    """Below normal, not idle: full speed whenever the processor is free (idle also throttled the disk), and the
    desk's order path still goes first when it needs a core."""
    if sys.platform == "win32":
        ctypes.windll.kernel32.SetPriorityClass(ctypes.c_void_p(-1), 0x00004000)


def log(msg: str) -> None:
    line = f"{datetime.now(NY).strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    with open(LOG, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    print(line, flush=True)


def wait_for_quiet(light: bool = False) -> bool:
    """True when work may go on; False when the STOP file asks to end. There are no quiet hours any more: the name
    and the argument are kept for the callers; only the operator's STOP file holds the job."""
    return not STOP.exists()


def free_ram_gb() -> float:
    """Physical memory the PC has free right now (the desk and the Gateway share this machine)."""
    if sys.platform != "win32":
        return 1e9

    class MS(ctypes.Structure):
        _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong), ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong), ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong), ("sullAvailExtendedVirtual", ctypes.c_ulonglong)]
    m = MS(); m.dwLength = ctypes.sizeof(MS)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
    return m.ullAvailPhys / 2**30


def wait_for_memory() -> bool:
    """Hold while free memory is short (a resource check, not a clock rule). False when the STOP file asks to end."""
    said = False
    while free_ram_gb() < MIN_FREE_RAM_GB:
        if STOP.exists():
            return False
        if not said:
            log(f"holding: {free_ram_gb():.1f} GB of memory free, under {MIN_FREE_RAM_GB:.0f} GB; continues when memory frees"); said = True
        time.sleep(30)
    return True


def pid_alive(pid: int) -> bool:
    k = ctypes.windll.kernel32
    h = k.OpenProcess(0x1000, False, pid)           # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return False
    try:
        code = ctypes.c_ulong()
        return bool(k.GetExitCodeProcess(h, ctypes.byref(code))) and code.value == 259   # STILL_ACTIVE
    finally:
        k.CloseHandle(h)


def parent_gone() -> bool:
    """True in a worker whose parent process has died: an orphan must not go on downloading (on 2026-10-05 thirteen of
    them outlived a killed supervisor and kept writing into a folder that had been emptied)."""
    import multiprocessing
    pp = multiprocessing.parent_process()
    return pp is not None and not pp.is_alive()


def single_instance(name: str = "NovaLabMassiveArchive") -> bool:
    """False when another copy of the job already runs (a named mutex that dies with its owner)."""
    if sys.platform != "win32":
        return True
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.CreateMutexW.restype = ctypes.c_void_p
    k.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
    handle = k.CreateMutexW(None, False, f"Local\\{name}")
    globals()["_MUTEX"] = handle                     # kept for the life of the process
    return ctypes.get_last_error() != 183            # ERROR_ALREADY_EXISTS
