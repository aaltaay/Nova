"""One kept execution-ledger connection per thread.

Every ledger read and write used to open its own SQLite connection and close it
again: about 20 per Paper order (2026-10-05). On the desk PC an open costs ~5 ms
(the file, the WAL and its index, the schema), and the close of the last
connection checkpoints the WAL -- so a Paper order spent ~100 ms of its ~150 ms
reply opening and closing the same file, and so did every Live order's ack,
facts and fill rows. Measured in-process: 20 opens, 77 of 92 ms in SQLite.

Each thread now keeps one connection to the ledger file it last used. Callers
keep the pattern they always had -- ``conn = store.get_connection()`` and
``conn.close()`` in a ``finally`` -- and nothing else changes: the same file,
the same ``synchronous`` (SQLite's default FULL in WAL), the same commit per
write. ``close()`` on a kept connection ends what a real close ends: an open
transaction is rolled back (sqlite3 never commits on close), and the
connection is handed back for its thread's next use.

- **Never shared while in use.** A use inside another use on the same thread
  (none today) gets a fresh connection of its own, closed for real, so it can
  never roll back or commit the outer caller's work. A caller that forgets
  ``close()`` leaves its thread on fresh connections, the old behaviour.
- **Never shared across threads.** Thread-local; ``check_same_thread`` is off
  only so :func:`close_all` can close every thread's kept connection.
- **Another file, another connection.** The ledger's path and the file's
  identity (device and file id: stable across writes, new for a file replaced
  at the same path) are read on every use; a kept connection to another file is
  closed. Windows refuses to replace or delete a file SQLite holds open, so a
  ledger is restored, moved or deleted with Nova stopped (``tools/data_root.py``
  already refuses while it runs); tests call :func:`close_all` first.
- **A broken connection is dropped.** A rollback that fails closes it for real;
  the thread's next use opens a fresh one.
"""
from __future__ import annotations

import logging
import os
import sqlite3
import threading
import weakref
from pathlib import Path

logger = logging.getLogger(__name__)

_local = threading.local()
_lock = threading.Lock()
_kept: "weakref.WeakSet[KeptConnection]" = weakref.WeakSet()


class KeptConnection(sqlite3.Connection):
    """A thread's ledger connection: ``close()`` ends the use, not the connection."""

    in_use: bool = False
    alive: bool = True
    path: str = ""
    ident: tuple[int, int] | None = None

    def close(self) -> None:  # noqa: D401 - the callers' close, see the module docstring
        self.in_use = False
        try:
            if self.in_transaction:
                self.rollback()
        except sqlite3.Error:
            logger.warning("execution ledger: a kept connection could not roll back; dropping it", exc_info=True)
            self.close_for_real()

    def close_for_real(self) -> None:
        self.in_use = False
        self.alive = False
        if getattr(_local, "conn", None) is self:
            _local.conn = None
        try:
            sqlite3.Connection.close(self)
        except sqlite3.Error:
            logger.warning("execution ledger: a kept connection failed to close", exc_info=True)


def _open(path: str, factory: type[sqlite3.Connection], *, kept: bool) -> sqlite3.Connection:
    conn = sqlite3.connect(path, timeout=5.0, factory=factory, check_same_thread=not kept)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def fresh(path: Path | str) -> sqlite3.Connection:
    """A connection of its own, closed for real by ``close()`` (the schema migration's)."""
    return _open(str(path), sqlite3.Connection, kept=False)


def _identity(path: str) -> tuple[int, int] | None:
    """The file at ``path``: device and file id, ``None`` while there is none."""
    try:
        st = os.stat(path)
    except OSError:
        return None
    return st.st_dev, st.st_ino


def connection(path: Path | str) -> sqlite3.Connection:
    """This thread's kept connection to ``path`` (fresh and unkept while it is in use)."""
    key = str(path)
    conn: KeptConnection | None = getattr(_local, "conn", None)
    if conn is not None and not conn.alive:
        conn = None  # closed by close_all() from another thread
    if conn is not None and conn.in_use:
        return fresh(key)  # a use inside a use: its own connection
    if conn is not None and (conn.path != key or conn.ident != _identity(key)):
        conn.close_for_real()  # another ledger file, or this one replaced
        conn = None
    if conn is None:
        conn = _open(key, KeptConnection, kept=True)  # type: ignore[assignment]
        conn.path = key
        conn.ident = _identity(key)
        _local.conn = conn
        with _lock:
            _kept.add(conn)
    conn.in_use = True
    return conn


def close_all() -> None:
    """Close every thread's kept connection (tests that delete or replace the ledger file)."""
    with _lock:
        conns = list(_kept)
        _kept.clear()
    for conn in conns:
        conn.close_for_real()
    _local.conn = None
