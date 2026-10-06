"""Windows imported from the Massive flat files, kept on the Massive drive (ADR 046).

One SQLite file beside the files it came from (``<root>/sim/replay.sqlite3``; the
operator keeps everything from Massive on E:), with its own schema version, apart
from the IBKR download store (``history_store``), which it never touches:

- ``jobs``: one row per imported window, its payload shaped like an IBKR download's
  (``id``, ``symbol``, ``date``, ``start``/``end``, ``status``, ``ranges``, ``count``...)
  plus ``source: "massive"`` and the import's own fields, so the desk lists and
  selects it the same way;
- ``prints``: the window's trades, typed columns, in SIP time order;
- ``candles``: the window's 1-minute bars;
- ``quotes``: the window's NBBO rows.

An import writes a window's rows in one transaction after reading them all, so a
window is either whole or absent; importing it again replaces it.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
from collections.abc import Iterable
from contextlib import contextmanager
from pathlib import Path

from constants_sim import (
    SIM_HISTORY_SQLITE_TIMEOUT_SEC, SIM_MASSIVE_SCHEMA_VERSION, SIM_MASSIVE_SOURCE, SIM_MASSIVE_STORE_FILE,
    SIM_MASSIVE_STORE_SUBDIR,
)
from sim import massive_files

ACTIVE = ("queued", "running")
_SPEC_KEYS = ("symbol", "date", "start", "end", "start_ts", "end_ts", "timezone", "source")
_init_lock = threading.Lock()
_initialized: set[str] = set()

_DDL = """
CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS prints (
    job_id TEXT NOT NULL, ordinal INTEGER NOT NULL, ts REAL NOT NULL, ns INTEGER NOT NULL,
    price REAL NOT NULL, size REAL NOT NULL, exchange TEXT, exchange_id INTEGER, conditions TEXT,
    correction INTEGER, trf_id INTEGER, sequence INTEGER, tape INTEGER, sets_price INTEGER NOT NULL,
    PRIMARY KEY(job_id, ordinal));
CREATE TABLE IF NOT EXISTS candles (job_id TEXT NOT NULL, ts INTEGER NOT NULL, payload TEXT NOT NULL,
    PRIMARY KEY(job_id, ts));
CREATE TABLE IF NOT EXISTS quotes (
    job_id TEXT NOT NULL, ordinal INTEGER NOT NULL, ts REAL NOT NULL, bid REAL, bid_size REAL, bid_x INTEGER,
    ask REAL, ask_size REAL, ask_x INTEGER, conditions TEXT, indicators TEXT, PRIMARY KEY(job_id, ordinal));
"""


def path() -> Path:
    return massive_files.root() / SIM_MASSIVE_STORE_SUBDIR / SIM_MASSIVE_STORE_FILE


def _initialize(db: sqlite3.Connection, where: Path) -> None:
    """Create the tables once per file; a store of another schema version is refused, never rewritten."""
    version = db.execute("PRAGMA user_version").fetchone()[0]
    if version not in (0, SIM_MASSIVE_SCHEMA_VERSION):
        raise sqlite3.DatabaseError(f"Unsupported Massive replay store version {version} at {where}")
    key = str(where.resolve())
    with _init_lock:
        if version == SIM_MASSIVE_SCHEMA_VERSION and key in _initialized:
            return
        db.execute("PRAGMA journal_mode=WAL")
        db.executescript(_DDL)
        db.execute(f"PRAGMA user_version={SIM_MASSIVE_SCHEMA_VERSION}")
        db.commit()
        _initialized.add(key)


@contextmanager
def connect():
    where = path()
    where.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(where, timeout=SIM_HISTORY_SQLITE_TIMEOUT_SEC)
    try:
        _initialize(db, where)
        with db:
            yield db
    finally:
        db.close()


def exists() -> bool:
    try:
        return path().is_file()
    except OSError:
        return False


def job_id_for(spec: dict) -> str:
    core = {key: spec.get(key) for key in _SPEC_KEYS}
    return hashlib.sha256(json.dumps([core, SIM_MASSIVE_SOURCE], sort_keys=True).encode()).hexdigest()[:24]


def new_job(spec: dict) -> dict:
    core = {key: spec.get(key) for key in _SPEC_KEYS}
    return dict(core, id=job_id_for(spec), kind="trades", status="queued", cursor=spec["start_ts"], ranges=[],
                seek=None, count=0, volume=0, pages=0, error=None, contract=None, storage=str(path()),
                precision="nanoseconds", updated=time.time(), started=None, stage=None, scan_pct=0.0,
                bar_count=0, quote_count=0, quote_status=None, files=None, elapsed_sec=None)


def save(job: dict) -> dict:
    with connect() as db:
        db.execute("INSERT OR REPLACE INTO jobs VALUES (?,?)", (job["id"], json.dumps(job)))
    return job


def get(job_id: str) -> dict | None:
    """The job, or ``None`` when this store does not hold it (or does not exist yet)."""
    if not exists():
        return None
    with connect() as db:
        row = db.execute("SELECT payload FROM jobs WHERE id=?", (job_id,)).fetchone()
    return json.loads(row[0]) if row else None


def find(spec: dict) -> dict | None:
    return get(job_id_for(spec))


def jobs() -> list[dict]:
    if not exists():
        return []
    with connect() as db:
        return [json.loads(r[0]) for r in db.execute("SELECT payload FROM jobs ORDER BY rowid DESC")]


def update(job_id: str, **fields) -> dict:
    """Atomic read-modify-write of one job."""
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT payload FROM jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            raise ValueError("Import not found")
        job = json.loads(row[0])
        job.update(fields, updated=time.time())
        db.execute("INSERT OR REPLACE INTO jobs VALUES (?,?)", (job_id, json.dumps(job)))
        return job


def replace_window(job_id: str, prints: list[dict], candles: list[dict], quotes: Iterable[tuple]) -> None:
    """The window's rows, all at once: whatever an earlier import stored for it goes first."""
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        for table in ("prints", "candles", "quotes"):
            db.execute(f"DELETE FROM {table} WHERE job_id=?", (job_id,))
        db.executemany(
            "INSERT INTO prints VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ((job_id, i, p["ts"], p["ns"], p["price"], p["size"], p["exchange"], p["exchange_id"], p["conditions"],
              p["correction"], p["trf_id"], p["sequence"], p["tape"], int(p["sets_price"])) for i, p in enumerate(prints)))
        db.executemany(
            "INSERT OR REPLACE INTO candles VALUES (?,?,?)",
            ((job_id, int(massive_files.minute_start(c)), json.dumps(c)) for c in candles))
        db.executemany("INSERT INTO quotes VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                       ((job_id, i, *q) for i, q in enumerate(quotes)))


_PRINT_COLUMNS = ("ordinal", "ts", "ns", "price", "size", "exchange", "exchange_id", "conditions", "correction",
                  "trf_id", "sequence", "tape", "sets_price")


def read_prints(job_id: str, symbol: str, *, limit: int = -1) -> list[dict]:
    """The window's prints in SIP time order, as replay print dicts (``seq`` is the stored ordinal)."""
    with connect() as db:
        rows = db.execute(f"SELECT {', '.join(_PRINT_COLUMNS)} FROM prints WHERE job_id=? ORDER BY ordinal LIMIT ?",
                          (job_id, limit)).fetchall()
    out = []
    for row in rows:
        item = dict(zip(_PRINT_COLUMNS, row, strict=True))
        out.append(dict(ts=item["ts"], ns=item["ns"], symbol=symbol, price=item["price"], size=item["size"],
                        exchange=item["exchange"], exchange_id=item["exchange_id"], conditions=item["conditions"],
                        correction=item["correction"], trf_id=item["trf_id"], sequence=item["sequence"],
                        tape=item["tape"], sets_price=bool(item["sets_price"]), unreported=False, seq=item["ordinal"]))
    return out


def read_candles(job_id: str) -> list[dict]:
    with connect() as db:
        return [json.loads(r[0]) for r in db.execute("SELECT payload FROM candles WHERE job_id=? ORDER BY ts", (job_id,))]


def read_quotes(job_id: str, *, limit: int = -1) -> list[tuple]:
    """``(ts, bid, bid_size, bid_x, ask, ask_size, ask_x)`` in time order."""
    with connect() as db:
        return db.execute("SELECT ts, bid, bid_size, bid_x, ask, ask_size, ask_x FROM quotes WHERE job_id=? "
                          "ORDER BY ordinal LIMIT ?", (job_id, limit)).fetchall()
