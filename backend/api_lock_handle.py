"""OS-held lifetime guard for API startup; never unlink the locked inode.

The JSON instance record is diagnostic metadata, not the exclusion primitive.
Closing the handle (including process death) releases the OS lock automatically.
"""
from __future__ import annotations

import errno
import os
import sys
from pathlib import Path
from typing import BinaryIO

LOCK_BYTES = 1


def guard_path() -> Path:
    """One operator's API guard, shared by all checkouts and packaged engines."""
    if sys.platform == "win32":
        root = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
        runtime = root / "Nova" / "runtime"
    else:
        runtime = Path.home() / ".cache" / "nova" / "runtime"
    return runtime / "api-instance.guard"


def try_lock(path: Path) -> BinaryIO | None:
    """Return a held handle, None for contention; unexpected I/O errors propagate."""
    handle = path.open("a+b")
    try:
        handle.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, LOCK_BYTES)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        handle.close()
        if exc.errno in (errno.EACCES, errno.EAGAIN) or getattr(exc, "winerror", None) in (33, 36):
            return None
        raise
    return handle
