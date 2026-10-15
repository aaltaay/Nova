"""Windows imported from the Massive flat files, kept on the Massive drive (ADR 046).

One SQLite file beside the files it came from (``<root>/sim/replay.sqlite3``; the
operator keeps everything from Massive on E:), with its own schema version, apart
from the IBKR download store (``history_store``), which it never touches:

- ``jobs``: one row per import -- a stock-day since 2026-10-09 (``start`` 04:00,
  ``end`` 20:00), one window before -- its payload shaped like an IBKR download's
  (``id``, ``symbol``, ``date``, ``start``/``end``, ``status``, ``ranges``, ``count``...)
  plus ``source: "massive"`` and the import's own fields, so the desk lists and
  selects it the same way; ``ranges`` is what it holds;
- ``packed``: the trades it holds (``name`` "prints", a ``PrintTable`` in SIP time
  order, each print's ``seq`` its ordinal) and its NBBO rows ("quotes", a
  ``QuoteSeries``, the one standing at their start first), each one blob of columns
  (schema 2, operator ask 2026-10-14): a load reads two blobs, never a row per print;
- ``candles``: the day's 1-minute bars;
- ``prints`` / ``quotes``: the same, a row each, as imports wrote them before schema 2.
  Still read for those imports, never written.

An import writes its rows in one transaction after reading them all, so it is
either whole or absent; importing it again replaces it, and the same transaction
drops the older imports of that symbol-day it now holds (``drop_held``).
"""
from __future__ import annotations

import bisect
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
from sim.history_quotes import QuoteSeries
from sim.print_table import PrintTable

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
CREATE TABLE IF NOT EXISTS packed (job_id TEXT NOT NULL, name TEXT NOT NULL, data BLOB NOT NULL,
    PRIMARY KEY(job_id, name));
"""
_PACKED_PRINTS, _PACKED_QUOTES = "prints", "quotes"
# Versions this code opens: 1 gains the ``packed`` table and becomes the current one; anything else refuses.
_UPGRADES_FROM = (0, 1)


def path() -> Path:
    return massive_files.root() / SIM_MASSIVE_STORE_SUBDIR / SIM_MASSIVE_STORE_FILE


def _initialize(db: sqlite3.Connection, where: Path) -> None:
    """Create the tables once per file. Version 1 only lacks the ``packed`` table, so it gains it and keeps every
    import it holds; a store of any other version is refused, never rewritten."""
    version = db.execute("PRAGMA user_version").fetchone()[0]
    if version not in (*_UPGRADES_FROM, SIM_MASSIVE_SCHEMA_VERSION):
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
                bar_count=0, quote_count=0, quote_status=None, files=None, elapsed_sec=None,
                focus_start=None, focus_end=None, focus_start_ts=None, focus_end_ts=None, kept_start=None,
                kept_end=None, capped=None)


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


def _held_by(db: sqlite3.Connection, job_id: str, held: tuple[str, str, float, float]) -> list[str]:
    """Other imports of the symbol-day, not running, whose every range (or window, none yet) lies in ``held``'s span."""
    symbol, day, lo, hi = held
    out = []
    for other, payload in db.execute("SELECT id, payload FROM jobs WHERE id != ?", (job_id,)).fetchall():
        job = json.loads(payload)
        if job.get("symbol") != symbol or job.get("date") != day or job.get("status") in ACTIVE:
            continue
        ranges = job.get("ranges") or [[job["start_ts"], job["end_ts"]]]
        if all(lo <= a and b <= hi for a, b in ranges):
            out.append(other)
    return out


def replace_window(job_id: str, prints: PrintTable | Iterable[dict], candles: list[dict],
                   quotes: QuoteSeries | Iterable[tuple], *, drop_held: tuple[str, str, float, float] | None = None) -> list[str]:
    """The import's prints and quotes, packed, and its bars, all at once: whatever an earlier import stored for it
    goes first.

    ``prints`` are in SIP time order; each is stored with ``seq`` = its ordinal. ``drop_held`` ``(symbol, date,
    lo, hi)``: the span it now holds; the older imports of that symbol-day inside it go in the same transaction
    (returned), so the desk lists and plays one copy of the day.
    """
    table = (prints if isinstance(prints, PrintTable) else PrintTable(prints)).numbered("seq")
    series = quotes if isinstance(quotes, QuoteSeries) else QuoteSeries(quotes)
    blobs = ((job_id, _PACKED_PRINTS, table.pack()), (job_id, _PACKED_QUOTES, series.pack()))
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        dropped = _held_by(db, job_id, drop_held) if drop_held is not None else []
        for gone in [job_id, *dropped]:
            for name in ("prints", "candles", "quotes", "packed"):
                db.execute(f"DELETE FROM {name} WHERE job_id=?", (gone,))
        db.executemany("DELETE FROM jobs WHERE id=?", ((gone,) for gone in dropped))
        db.executemany("INSERT INTO packed VALUES (?,?,?)", blobs)
        db.executemany(
            "INSERT OR REPLACE INTO candles VALUES (?,?,?)",
            ((job_id, int(massive_files.minute_start(c)), json.dumps(c)) for c in candles))
    return dropped


def _packed(db: sqlite3.Connection, job_id: str, name: str) -> bytes | None:
    row = db.execute("SELECT data FROM packed WHERE job_id=? AND name=?", (job_id, name)).fetchone()
    return row[0] if row else None


_PRINT_COLUMNS = ("ordinal", "ts", "ns", "price", "size", "exchange", "exchange_id", "conditions", "correction",
                  "trf_id", "sequence", "tape", "sets_price")


_EVER = (float("-inf"), float("inf"))


def read_print_table(job_id: str, symbol: str, *, between: tuple[float, float] = _EVER) -> PrintTable:
    """The prints in ``[lo, hi)`` in SIP time order (``seq`` is the stored ordinal): the packed blob, sliced; an
    import stored before schema 2 is read from its rows."""
    with connect() as db:
        blob = _packed(db, job_id, _PACKED_PRINTS)
        if blob is None:
            rows = db.execute(f"SELECT {', '.join(_PRINT_COLUMNS)} FROM prints WHERE job_id=? AND ts >= ? AND ts < ? "
                              "ORDER BY ordinal", (job_id, *between))
            return PrintTable(_legacy_print(dict(zip(_PRINT_COLUMNS, row, strict=True)), symbol) for row in rows)
    table = PrintTable.unpack(blob)
    ts = table.values("ts")
    return table.span(bisect.bisect_left(ts, between[0]), bisect.bisect_left(ts, between[1]))


def _legacy_print(item: dict, symbol: str) -> dict:
    return dict(ts=item["ts"], ns=item["ns"], symbol=symbol, price=item["price"], size=item["size"],
                exchange=item["exchange"], exchange_id=item["exchange_id"], conditions=item["conditions"],
                correction=item["correction"], trf_id=item["trf_id"], sequence=item["sequence"],
                tape=item["tape"], sets_price=bool(item["sets_price"]), unreported=False, seq=item["ordinal"])


def read_prints(job_id: str, symbol: str, *, limit: int = -1, between: tuple[float, float] = _EVER) -> list[dict]:
    """``read_print_table`` as replay print dicts, at most ``limit`` of them (-1: all)."""
    table = read_print_table(job_id, symbol, between=between)
    return table[:limit] if limit >= 0 else list(table)


def read_candles(job_id: str) -> list[dict]:
    with connect() as db:
        return [json.loads(r[0]) for r in db.execute("SELECT payload FROM candles WHERE job_id=? ORDER BY ts", (job_id,))]


def read_quote_series(job_id: str, *, between: tuple[float, float] | None = None) -> QuoteSeries:
    """The NBBO rows in time order: all of them, or those in ``[lo, hi)`` after the one standing at ``lo``. The
    packed blob, sliced; an import stored before schema 2 is read from its rows."""
    columns = "SELECT ts, bid, bid_size, bid_x, ask, ask_size, ask_x FROM quotes WHERE job_id=?"
    with connect() as db:
        blob = _packed(db, job_id, _PACKED_QUOTES)
        if blob is None:
            if between is None:
                return QuoteSeries(db.execute(f"{columns} ORDER BY ordinal", (job_id,)))
            series = QuoteSeries(db.execute(f"{columns} AND ts < ? ORDER BY ordinal DESC LIMIT 1", (job_id, between[0])))
            series.extend(QuoteSeries(db.execute(f"{columns} AND ts >= ? AND ts < ? ORDER BY ordinal", (job_id, *between))))
            return series
    series = QuoteSeries.unpack(blob)
    return series if between is None else series.between(*between)


def read_quotes(job_id: str, *, limit: int = -1, between: tuple[float, float] | None = None) -> list[tuple]:
    """``read_quote_series`` as ``(ts, bid, bid_size, bid_x, ask, ask_size, ask_x)`` rows, at most ``limit``."""
    rows = read_quote_series(job_id, between=between).rows()
    return rows[:limit] if limit >= 0 else rows
