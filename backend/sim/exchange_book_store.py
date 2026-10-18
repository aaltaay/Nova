"""The Sim's store of exchange books imported from MBP-10 files (ADR 057).

One SQLite file beside the Massive imports (``<NOVA_MARKET_DATA_DIR>/sim/exchange_books.sqlite3``), with its
own schema version, apart from every other replay store:

- ``books``: one row per symbol-day and venue (``id`` ``SYMBOL|YYYY-MM-DD|DATASET``), its payload what the
  import read and what the book covers (``known_from_ns`` / ``known_to_ns``);
- ``chunks``: the book's events in file order, ``SIM_EXCHANGE_BOOK_CHUNK_EVENTS`` to a chunk, each one blob
  of packed columns (``print_table.pack_columns``, then zlib) with its first and last capture time, so a
  playhead inflates one chunk however long the day.

An import writes inside one transaction (``Writer``): the book's old rows go at its start and come back if it
fails, so a book is whole or absent and the old one plays until the new one commits. The file is in WAL mode,
so the desk's reads never wait on an import. A read never creates the store.
"""
from __future__ import annotations

import json
import sqlite3
import zlib
from array import array
from pathlib import Path

from constants_sim import (
    SIM_EXCHANGE_BOOK_SCHEMA_VERSION, SIM_EXCHANGE_BOOK_SQLITE_TIMEOUT_SEC, SIM_EXCHANGE_BOOK_STORE_FILE,
    SIM_HISTORY_SQLITE_TIMEOUT_SEC, SIM_MASSIVE_STORE_SUBDIR,
)
from sim import massive_files
from sim.print_table import pack_columns, unpack_columns

_DDL = """
CREATE TABLE IF NOT EXISTS books (id TEXT PRIMARY KEY, symbol TEXT NOT NULL, date TEXT NOT NULL,
    dataset TEXT NOT NULL, payload TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS books_by_day ON books (symbol, date);
CREATE TABLE IF NOT EXISTS chunks (book_id TEXT NOT NULL, ordinal INTEGER NOT NULL, start_ns INTEGER NOT NULL,
    end_ns INTEGER NOT NULL, events INTEGER NOT NULL, data BLOB NOT NULL, PRIMARY KEY (book_id, ordinal));
"""
_ZLIB_LEVEL = 6


def path() -> Path:
    return massive_files.root() / SIM_MASSIVE_STORE_SUBDIR / SIM_EXCHANGE_BOOK_STORE_FILE


def book_id(symbol: str, date: str, dataset: str) -> str:
    return f"{symbol}|{date}|{dataset}"


def _checked(db: sqlite3.Connection, where: Path, *, allow_new: bool) -> None:
    version = db.execute("PRAGMA user_version").fetchone()[0]
    if version == SIM_EXCHANGE_BOOK_SCHEMA_VERSION or (allow_new and version == 0):
        return
    raise sqlite3.DatabaseError(f"Unsupported exchange book store version {version} at {where}")


def reader(where: Path | None = None) -> sqlite3.Connection | None:
    """A connection for reading, or None when there is no store (a read never creates one)."""
    where = where or path()
    if not where.is_file():
        return None
    db = sqlite3.connect(where, timeout=SIM_EXCHANGE_BOOK_SQLITE_TIMEOUT_SEC)
    try:
        _checked(db, where, allow_new=False)
    except BaseException:
        db.close()
        raise
    return db


def pack_chunk(columns: dict[str, array]) -> bytes:
    return zlib.compress(pack_columns(columns, {}), _ZLIB_LEVEL)


def unpack_chunk(blob: bytes, events: int) -> dict[str, array]:
    """A chunk's columns; refused when a column's length is not the chunk's event count."""
    columns, _extra = unpack_columns(zlib.decompress(blob))
    if any(len(col) != events for col in columns.values()):
        raise ValueError(f"A stored exchange book chunk does not hold its {events} events")
    return columns


def books_for(db: sqlite3.Connection, symbol: str, date: str) -> list[dict]:
    rows = db.execute("SELECT payload FROM books WHERE symbol = ? AND date = ? ORDER BY dataset", (symbol, date))
    return [json.loads(payload) for (payload,) in rows]


def listing(db: sqlite3.Connection, symbol: str | None = None, date: str | None = None) -> list[dict]:
    query, args = "SELECT payload FROM books WHERE 1 = 1", []
    if symbol:
        query, args = query + " AND symbol = ?", [*args, symbol]
    if date:
        query, args = query + " AND date = ?", [*args, date]
    return [json.loads(payload) for (payload,) in db.execute(query + " ORDER BY date DESC, symbol, dataset", args)]


def chunk_index(db: sqlite3.Connection, book: str) -> tuple[array, array]:
    """``(start_ns, events)`` of the book's chunks, by ordinal."""
    starts, counts = array("q"), array("q")
    for start, events in db.execute("SELECT start_ns, events FROM chunks WHERE book_id = ? ORDER BY ordinal", (book,)):
        starts.append(start)
        counts.append(events)
    return starts, counts


def read_chunk(db: sqlite3.Connection, book: str, ordinal: int) -> tuple[bytes, int]:
    row = db.execute("SELECT data, events FROM chunks WHERE book_id = ? AND ordinal = ?", (book, ordinal)).fetchone()
    if row is None:
        raise KeyError(f"exchange book {book} has no chunk {ordinal}")
    return row[0], row[1]


def remove(where: Path, book: str) -> bool:
    """Drop one book and its events; False when there was none."""
    db = reader(where)
    if db is None:
        return False
    try:
        with db:
            db.execute("DELETE FROM chunks WHERE book_id = ?", (book,))
            return db.execute("DELETE FROM books WHERE id = ?", (book,)).rowcount > 0
    finally:
        db.close()


class Writer:
    """One import's transaction: ``put`` each chunk as it fills, ``finish`` with the book's payload.

    Leaving without ``finish`` -- an error, a refusal -- rolls everything back, the old book included.
    """

    def __init__(self, where: Path, book: str):
        self.where, self.book, self.chunks, self._done = where, book, 0, False
        where.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(where, timeout=SIM_HISTORY_SQLITE_TIMEOUT_SEC, isolation_level=None)

    def __enter__(self) -> Writer:
        db = self._db
        try:
            _checked(db, self.where, allow_new=True)
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript(_DDL)
            db.execute(f"PRAGMA user_version = {SIM_EXCHANGE_BOOK_SCHEMA_VERSION}")
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM chunks WHERE book_id = ?", (self.book,))
            db.execute("DELETE FROM books WHERE id = ?", (self.book,))
        except BaseException:
            db.close()
            raise
        return self

    def put(self, columns: dict[str, array]) -> None:
        ns = columns["ns"]
        self._db.execute("INSERT INTO chunks (book_id, ordinal, start_ns, end_ns, events, data) VALUES (?, ?, ?, ?, ?, ?)",
                         (self.book, self.chunks, ns[0], ns[-1], len(ns), pack_chunk(columns)))
        self.chunks += 1

    def finish(self, payload: dict) -> None:
        self._db.execute("INSERT INTO books (id, symbol, date, dataset, payload) VALUES (?, ?, ?, ?, ?)",
                         (self.book, payload["symbol"], payload["date"], payload["dataset"],
                          json.dumps(payload, separators=(",", ":"))))
        self._db.execute("COMMIT")
        self._done = True

    def __exit__(self, *_exc) -> None:
        try:
            if not self._done and self._db.in_transaction:
                self._db.execute("ROLLBACK")
        finally:
            self._db.close()
