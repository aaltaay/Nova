"""Windows' TCP tables, read in-process (``GetExtendedTcpTable``): each connection's state, local port and
owning process id, IPv4 and IPv6 (the port watch, ``perf/port_watch.py``).

A few milliseconds for ~17,000 rows, and nothing is started. No address is returned -- the port watch counts,
it never says where a connection goes. ``dynamic_range()`` asks ``netsh`` once for the ports Windows hands
out to outgoing connections. Empty off Windows; OSError when Windows refuses.
"""
from __future__ import annotations

import ctypes
import re
import subprocess
from ctypes import wintypes
from dataclasses import dataclass

from winapi import available

AF_INET = 2
AF_INET6 = 23
TCP_TABLE_OWNER_PID_ALL = 5
MIB_TCP_STATE_LISTEN = 2
ERROR_INSUFFICIENT_BUFFER = 122
NO_ERROR = 0
_ATTEMPTS = 4                                  # the table can grow between the size ask and the read
DEFAULT_DYNAMIC_START = 49152                  # Windows' default dynamic range since Vista
DEFAULT_DYNAMIC_COUNT = 16384
_NETSH_TIMEOUT_SEC = 5.0


@dataclass(frozen=True)
class Conn:
    state: int         # MIB_TCP_STATE: 2 LISTEN, 5 ESTABLISHED, 11 TIME_WAIT, ...
    local_port: int
    pid: int


class _Row4(ctypes.Structure):
    _fields_ = [
        ("dwState", wintypes.DWORD),
        ("dwLocalAddr", wintypes.DWORD),
        ("dwLocalPort", wintypes.DWORD),
        ("dwRemoteAddr", wintypes.DWORD),
        ("dwRemotePort", wintypes.DWORD),
        ("dwOwningPid", wintypes.DWORD),
    ]


class _Row6(ctypes.Structure):
    _fields_ = [
        ("ucLocalAddr", ctypes.c_ubyte * 16),
        ("dwLocalScopeId", wintypes.DWORD),
        ("dwLocalPort", wintypes.DWORD),
        ("ucRemoteAddr", ctypes.c_ubyte * 16),
        ("dwRemoteScopeId", wintypes.DWORD),
        ("dwRemotePort", wintypes.DWORD),
        ("dwState", wintypes.DWORD),
        ("dwOwningPid", wintypes.DWORD),
    ]


_iphlpapi = None


def _lib():
    global _iphlpapi
    if _iphlpapi is None:
        lib = ctypes.WinDLL("iphlpapi")
        lib.GetExtendedTcpTable.argtypes = [
            ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD), wintypes.BOOL, wintypes.ULONG, ctypes.c_int,
            wintypes.ULONG,
        ]
        lib.GetExtendedTcpTable.restype = wintypes.DWORD
        _iphlpapi = lib
    return _iphlpapi


def port_of(raw: int) -> int:
    """A table's port: network byte order in the low 16 bits of a DWORD."""
    return ((raw & 0xFF) << 8) | ((raw >> 8) & 0xFF)


def _table(family: int, row: type[ctypes.Structure]) -> list[Conn]:
    lib = _lib()
    size = wintypes.DWORD(0)
    for _ in range(_ATTEMPTS):
        buf = ctypes.create_string_buffer(max(int(size.value), 4))
        rc = lib.GetExtendedTcpTable(buf, ctypes.byref(size), False, family, TCP_TABLE_OWNER_PID_ALL, 0)
        if rc == ERROR_INSUFFICIENT_BUFFER:
            size = wintypes.DWORD(int(size.value) + 64 * ctypes.sizeof(row))   # room for rows added meanwhile
            continue
        if rc != NO_ERROR:
            raise ctypes.WinError(rc)
        count = ctypes.c_uint32.from_buffer(buf).value
        rows = (row * count).from_buffer(buf, 4)          # the rows follow dwNumEntries, DWORD-aligned
        return [Conn(int(r.dwState), port_of(int(r.dwLocalPort)), int(r.dwOwningPid)) for r in rows]
    raise OSError("GetExtendedTcpTable: the table kept growing past its buffer")


def connections() -> list[Conn]:
    """Every TCP connection and listener now, IPv4 then IPv6. Empty off Windows."""
    if not available():
        return []
    return _table(AF_INET, _Row4) + _table(AF_INET6, _Row6)


def parse_dynamic_range(text: str) -> tuple[int, int] | None:
    """``netsh int ipv4 show dynamicport tcp``'s start port and number of ports: the first two numbers after a
    colon (the labels are translated on a localized Windows). None when the text holds no such pair."""
    numbers = [int(n) for n in re.findall(r":\s*(\d+)\s*$", text, flags=re.MULTILINE)]
    if len(numbers) < 2 or not (0 < numbers[0] < 65536) or not (0 < numbers[1] <= 65536):
        return None
    return numbers[0], numbers[1]


def dynamic_range() -> tuple[int, int, str]:
    """The ports Windows hands out to outgoing connections: ``(start, count, "netsh")``, or Windows' default
    with ``"default"`` when ``netsh`` cannot say."""
    if available():
        try:
            out = subprocess.run(
                ["netsh", "int", "ipv4", "show", "dynamicport", "tcp"], capture_output=True, text=True,
                timeout=_NETSH_TIMEOUT_SEC, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), check=False,
            ).stdout
        except (OSError, subprocess.SubprocessError):
            out = ""
        parsed = parse_dynamic_range(out or "")
        if parsed is not None:
            return parsed[0], parsed[1], "netsh"
    return DEFAULT_DYNAMIC_START, DEFAULT_DYNAMIC_COUNT, "default"
