"""The files of a rebuilt day's Gappers by the second (ADR 023 amendment 2026-10-13).

Persisted state (persisted-state.mdc). Owner: this module, the only reader and writer of
``<leaderboard root>/seconds/<date>.<board>.sqlite3`` and ``<date>.<board>.json``:

* the data file (``PRAGMA user_version`` = ``LEADERBOARD_SECONDS_SCHEMA_VERSION``) is written as ``.part`` and
  renamed when whole, so it is whole or absent: ``meta(key, value)``, ``candidates(minute_ts, symbol, rank, price,
  volume, prev_close)``, ``seconds(symbol, ts, price, volume)``;
* the job file (``schema_version``) is the build's state, rewritten whole (temp file, rename) at every step.

Invalidated when the rebuilt day changes (``meta.fingerprint``, compared by ``job.request``). An unknown version
of either file is never read (logged): the day reads as never built, and asking builds it again. Shapes:
``architecture/schema/scanner.md``, "A rebuilt day's Gappers by the second".
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from constants_leaderboard import LEADERBOARD_SECONDS_SCHEMA_VERSION, LEADERBOARD_SECONDS_SUBDIR
from leaderboard import store as board_store
from leaderboard.seconds.build import Candidate, Second

logger = logging.getLogger(__name__)
# A reader may hold the data file open for a moment while a rebuilt one replaces it (Windows refuses the rename).
_REPLACE_TRIES = 50
_REPLACE_PAUSE_SEC = 0.1

_DDL = """
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE candidates (
    minute_ts INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    rank INTEGER,
    price REAL,
    volume REAL NOT NULL,
    prev_close REAL NOT NULL,
    PRIMARY KEY (minute_ts, symbol)
) WITHOUT ROWID;
CREATE TABLE seconds (
    symbol TEXT NOT NULL,
    ts INTEGER NOT NULL,
    price REAL,
    volume REAL NOT NULL,
    PRIMARY KEY (symbol, ts)
) WITHOUT ROWID;
"""


def folder() -> Path:
    return board_store.root() / LEADERBOARD_SECONDS_SUBDIR


def data_path(day: str, board: str) -> Path:
    return folder() / f"{day}.{board}.sqlite3"


def job_path(day: str, board: str) -> Path:
    return folder() / f"{day}.{board}.json"


def _replace(source: Path, target: Path) -> None:
    for attempt in range(_REPLACE_TRIES):
        try:
            os.replace(source, target)
            return
        except PermissionError:
            if attempt == _REPLACE_TRIES - 1:
                raise
            time.sleep(_REPLACE_PAUSE_SEC)


# ── The job file ────────────────────────────────────────────────────────────

def read_job(day: str, board: str) -> dict[str, Any] | None:
    """The build's state, or None when none was asked for (or its file is of an unknown version, logged)."""
    path = job_path(day, board)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        logger.warning("Gappers by the second: job file %s unreadable (%s); read as never built", path, exc)
        return None
    if not isinstance(raw, dict) or raw.get("schema_version") != LEADERBOARD_SECONDS_SCHEMA_VERSION:
        logger.warning("Gappers by the second: job file %s is not schema %d; read as never built",
                       path, LEADERBOARD_SECONDS_SCHEMA_VERSION)
        return None
    return raw


def write_job(day: str, board: str, **fields: Any) -> dict[str, Any]:
    """Merge ``fields`` into the job and write it whole; ``updated_ts`` is stamped every time."""
    job = read_job(day, board) or {}
    job.update(fields)
    job.update(schema_version=LEADERBOARD_SECONDS_SCHEMA_VERSION, date=day, board=board, updated_ts=time.time())
    path = job_path(day, board)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    temp.write_text(json.dumps(job, sort_keys=True), encoding="utf-8")
    _replace(temp, path)
    return job


# ── The data file ───────────────────────────────────────────────────────────

class DataWriter:
    """A day's data file being built: rows go into ``.part``; ``finish`` renames it, ``abort`` drops it."""

    def __init__(self, day: str, board: str):
        self.path = data_path(day, board)
        self.part = self.path.with_name(f"{self.path.name}.part")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.part.unlink(missing_ok=True)
        self.db = sqlite3.connect(self.part)
        self.db.executescript(_DDL)
        self.db.execute(f"PRAGMA user_version = {int(LEADERBOARD_SECONDS_SCHEMA_VERSION)}")

    def candidates(self, items: Iterable[Candidate]) -> None:
        self.db.executemany(
            "INSERT OR REPLACE INTO candidates (minute_ts, symbol, rank, price, volume, prev_close)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            ((c.minute, c.symbol, c.rank, c.price, c.volume, c.prev_close) for c in items))

    def seconds(self, symbol: str, rows: Iterable[Second]) -> None:
        self.db.executemany("INSERT OR REPLACE INTO seconds (symbol, ts, price, volume) VALUES (?, ?, ?, ?)",
                            ((symbol, ts, price, volume) for ts, price, volume in rows))

    def finish(self, meta: Mapping[str, Any]) -> Path:
        self.db.executemany("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
                            ((key, json.dumps(value)) for key, value in meta.items()))
        self.db.commit()
        self.db.close()
        _replace(self.part, self.path)
        return self.path

    def abort(self) -> None:
        try:
            self.db.close()
        finally:
            self.part.unlink(missing_ok=True)


def open_data(day: str, board: str) -> sqlite3.Connection | None:
    """The day's data file read-only, or None when it is absent or of an unknown version (logged)."""
    path = data_path(day, board)
    if not path.is_file():
        return None
    db = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    try:
        version = db.execute("PRAGMA user_version").fetchone()[0]
    except sqlite3.Error:
        db.close()
        raise
    if version != LEADERBOARD_SECONDS_SCHEMA_VERSION:
        db.close()
        logger.warning("Gappers by the second: %s is version %s, not %d; read as never built",
                       path, version, LEADERBOARD_SECONDS_SCHEMA_VERSION)
        return None
    return db


def meta(db: sqlite3.Connection) -> dict[str, Any]:
    return {key: json.loads(value) for key, value in db.execute("SELECT key, value FROM meta")}


def candidates_at(db: sqlite3.Connection, minute: int) -> list[Candidate]:
    rows = db.execute("SELECT minute_ts, symbol, price, volume, prev_close, rank FROM candidates"
                      " WHERE minute_ts = ? ORDER BY symbol", (int(minute),)).fetchall()
    return [Candidate(int(m), str(s), p, float(v), float(pc), None if r is None else int(r))
            for m, s, p, v, pc, r in rows]


def seconds_between(db: sqlite3.Connection, symbols: Sequence[str], start: int, end: int) -> dict[str, list[Second]]:
    """Each symbol's seconds in ``[start, end)``, in order."""
    out: dict[str, list[Second]] = {}
    for symbol in symbols:
        rows = db.execute("SELECT ts, price, volume FROM seconds WHERE symbol = ? AND ts >= ? AND ts < ? ORDER BY ts",
                          (symbol, int(start), int(end))).fetchall()
        if rows:
            out[symbol] = [(int(ts), price, float(volume)) for ts, price, volume in rows]
    return out
