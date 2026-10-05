"""Thin ctypes wrappers over the Windows APIs Nova reads and sets: the process list, a process's command line and start time, and CPU / I/O / memory priority (ADR 045).

In-process and fast -- a process snapshot is a few milliseconds where a ``tasklist`` or
PowerShell run held the socket loop 0.1-1.7 s. Every call is a no-op answer off Windows
(``available()`` False). Nothing here logs a command line: an IBC-launched Gateway's carries
its encrypted credentials.
"""
from __future__ import annotations

import os


def available() -> bool:
    """True on Windows, where these calls mean something."""
    return os.name == "nt"
