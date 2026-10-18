"""How many heavy reads run at once across every process on the PC (ADR 059).

Many agents share one trading PC and one E: drive: three full scans of the 1 GB movers store stalled each other on
2026-10-18. A heavy read (a bulk scan, a reference index build, a stock-day read through the MCP) takes one of
``NOVA_MARKET_READ_SLOTS`` (default 2) lock files and waits for a free one; a lock dies with its process, so a
crashed reader never holds a slot. Nothing else is written. The lock files live in the OS temp folder.
"""
from __future__ import annotations

import os
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

DEFAULT_SLOTS = 2
WAIT_SECONDS = 600.0
POLL_SECONDS = 0.25


class Busy(TimeoutError):
    """Every slot stayed taken for the whole wait."""


def _count() -> int:
    try:
        return max(1, int(os.environ.get("NOVA_MARKET_READ_SLOTS") or DEFAULT_SLOTS))
    except ValueError:
        return DEFAULT_SLOTS


def _folder() -> Path:
    path = Path(tempfile.gettempdir()) / "nova-market-read-slots"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _try_lock(handle) -> bool:
    if os.name == "nt":
        import msvcrt
        handle.seek(0)
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            return True
        except OSError:
            return False
    import fcntl
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


def _unlock(handle) -> None:
    if os.name == "nt":
        import msvcrt
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextmanager
def heavy(what: str, wait: float = WAIT_SECONDS):
    """Hold one slot for the block; raise ``Busy`` naming ``what`` after ``wait`` seconds with none free."""
    deadline = time.monotonic() + wait
    folder = _folder()
    while True:
        for n in range(_count()):
            handle = open(folder / f"slot-{n}.lock", "a+b")
            if _try_lock(handle):
                try:
                    yield n
                finally:
                    _unlock(handle)
                    handle.close()
                return
            handle.close()
        if time.monotonic() >= deadline:
            raise Busy(f"{what}: all {_count()} heavy-read slots stayed busy for {wait:.0f} s "
                       "(NOVA_MARKET_READ_SLOTS raises the count)")
        time.sleep(POLL_SECONDS)
