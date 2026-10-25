"""The signal table: the Trader's Signals panel, minute by minute, for every in-play stock-day since 2016, so an agent
mixes signals in one query and every agent reads the same answer (``architecture/schema/agent-desk.md``, "The
Trader's signals on past days, and mixing them").

Owner of the files: this module writes them (``write_day`` / ``write_tape``, driven by
``research/signals/build_signals.py``) and lists them for the reads (``research/market_reads/signals.py``).
Invalidation: a ``BUILDER`` bump, or the day's relative-volume row rebuilt after the signal day was built, stales
that day (a signal day reads only its own day and earlier ones that the relative-volume table already holds).
``SCHEMA_VERSION`` is in the manifest and each file's metadata; another version is refused
(``UnknownSignalsSchema``).
"""
from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from market_reads import roots
from market_reads import rvol_store as rs

SCHEMA_VERSION = 1
BUILDER = 3                      # bump when a rule below or a desk rule it calls changes: every day is built again
TAPE_BUILDER = 1
ROOT_ENV = "NOVA_SIGNALS_DIR"
DEFAULT_ROOT_WIN = r"F:\Nova\signals"
RESERVE_GB = 40.0
LOCK_WAIT_SEC = 120.0            # how long a writer waits for the manifest
SHARING_RETRY_SEC = 10.0         # how long a replace / delete waits out another handle on the file (Windows)
LOCK_STALE_SEC = 300.0           # a lock older than this was left by a writer that died
META_KEY = b"nova_signals"
KINDS = ("CS", "ADRC")
PRICE_MIN, PRICE_MAX = 1.0, 20.0         # prev_close, dollars
IN_PLAY_CHANGE = 0.10                    # a bar closed at least 10% over the prior close ...
IN_PLAY_RVOL = 5.0                       # ... or cum / base reached 5 ...
IN_PLAY_VOLUME = 50_000                  # ... with at least this many shares traded since 04:00
LAST_M = rs.RTH_CLOSE_M - 1              # rows run through 15:59
MIN_BASE_SESSIONS = rs.BASE_SESSIONS
RULES = {
    "universe": f"CS / ADRC stock-days of the relative-volume table, prev_close ${PRICE_MIN:g}-${PRICE_MAX:g}, not a "
                f"likely split, {MIN_BASE_SESSIONS}+ baseline sessions, where a bar starting 04:00-15:59 ET closed "
                f"{IN_PLAY_CHANGE:.0%}+ over prev_close or reached cum / base {IN_PLAY_RVOL:g}, with {IN_PLAY_VOLUME:,} "
                "shares or more traded since 04:00; in_play_m is the "
                "first such bar's start, and rows run from it through 15:59",
    "minute": "each signal as the desk's rule reads it at the end of minute m (bars starting at or before m)",
    "intra_bar": "prices inside a minute are its open (1 s in), then its high (long lanes) or low (short lanes) at "
                 "30 s: the order inside a bar is not in the data",
    "unknown": "a fact with no history is the panel's own unknown, never guessed (signal_catalog says which)",
}


class UnknownSignalsSchema(RuntimeError):
    """The table was written by another schema version: refused, never read or rebuilt over as found."""


def root() -> Path:
    explicit = os.environ.get(ROOT_ENV)
    if explicit:
        return Path(explicit)
    if os.name == "nt" and Path(DEFAULT_ROOT_WIN[:3]).exists():
        return Path(DEFAULT_ROOT_WIN)
    return roots.massive() / "signals"


def manifest_path() -> Path:
    return root() / "manifest.json"


def _path(table: str, day: str) -> Path:
    return root() / table / day[:4] / f"{day}.parquet"


def minutes_path(day: str) -> Path:
    return _path("minutes", day)


def days_path(day: str) -> Path:
    return _path("days", day)


def tape_path(day: str) -> Path:
    return _path("tape", day)


def stop_path() -> Path:
    """``<root>/STOP``: a running build stops after the days in hand."""
    return root() / "STOP"


def new_manifest() -> dict[str, Any]:
    return {"schema_version": SCHEMA_VERSION, "builder": BUILDER, "tape_builder": TAPE_BUILDER, "rules": RULES,
            "templates": {}, "days": {}, "tape": {}}


def load_manifest(required: bool = False) -> dict[str, Any]:
    path = manifest_path()
    if not path.is_file():
        if required:
            raise LookupError(f"no signal table at {root()}: build it with py -3 research/signals/build_signals.py")
        return new_manifest()
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != SCHEMA_VERSION:
        raise UnknownSignalsSchema(f"{path} is schema_version {data.get('schema_version')!r}, this reader is "
                                   f"{SCHEMA_VERSION}: build the table again into an empty {ROOT_ENV}")
    data.setdefault("tape", {})
    return data


def save_manifest(data: dict[str, Any]) -> None:
    path = manifest_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(f".json.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, indent=1, sort_keys=True), encoding="utf-8")
    _until_windows_lets_go(lambda: os.replace(tmp, path))


def _until_windows_lets_go(step) -> None:
    """Run ``step``, retrying a ``PermissionError`` for up to ``SHARING_RETRY_SEC``. On Windows a file another handle
    has open (a reader of the manifest, a waiter's ``stat`` of the lock, a virus scan) cannot be replaced or deleted
    for that moment: a lasting refusal still raises (#1221)."""
    deadline = time.monotonic() + SHARING_RETRY_SEC
    while True:
        try:
            step()
            return
        except PermissionError:
            if time.monotonic() > deadline:
                raise
            time.sleep(0.01)


@contextmanager
def manifest_lock():
    """``<root>/manifest.lock``, created exclusively: one read-modify-write of the manifest at a time across processes
    (the minute and tape stages may run at once). A lock older than ``LOCK_STALE_SEC`` is a dead writer's.

    On Windows a lock file just released can still be pending delete while another handle is open on it, and
    creating it then is ``PermissionError``, not ``FileExistsError``: that is a held lock, waited for like one. It
    once killed a writer mid-build and lost the rest of its days (#1221)."""
    path = root() / "manifest.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + LOCK_WAIT_SEC
    while True:
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except (FileExistsError, PermissionError) as refused:
            try:
                if time.time() - path.stat().st_mtime > LOCK_STALE_SEC:
                    path.unlink()
                    continue
            except FileNotFoundError:
                if isinstance(refused, FileExistsError):
                    continue             # released between the two calls: try again at once
                # refused with no lock on disk: the folder denies creating it, so wait out the deadline, then fail
            except PermissionError:
                pass                     # pending delete, or held open this instant: still someone's lock
            if time.monotonic() > deadline:
                raise TimeoutError(f"{path} held (or refused) for over {LOCK_WAIT_SEC:.0f} s") from None
            time.sleep(0.05)
    try:
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        yield
    finally:
        _until_windows_lets_go(lambda: path.unlink(missing_ok=True))


def update_manifest(change) -> dict[str, Any]:
    """Read the manifest, ``change(data)`` it and write it back, under ``manifest_lock``."""
    with manifest_lock():
        data = load_manifest()
        change(data)
        save_manifest(data)
        return data


def _write(table, path: Path, day: str, name: str) -> None:
    import pyarrow.parquet as pq
    if rs.free_gb(root()) < RESERVE_GB:
        raise OSError(f"{root()} has under {RESERVE_GB:.0f} GB free: the signal table stops here")
    meta = dict(table.schema.metadata or {})
    meta[META_KEY] = json.dumps({"schema_version": SCHEMA_VERSION, "builder": BUILDER, "day": day,
                                 "table": name}).encode()
    table = table.replace_schema_metadata(meta)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".parquet.tmp")
    labels = [f.name for f in table.schema if str(f.type) in ("string", "large_string")]
    pq.write_table(table, tmp, compression="zstd", compression_level=3, use_dictionary=labels or False)
    _until_windows_lets_go(lambda: os.replace(tmp, path))     # a reader may hold the old day file open


def write_day(day: str, minutes, days) -> None:
    """One session's two files, each written whole then renamed into place."""
    _write(minutes, minutes_path(day), day, "minutes")
    _write(days, days_path(day), day, "days")


def write_tape(day: str, tape) -> None:
    _write(tape, tape_path(day), day, "tape")


def built_days(data: dict[str, Any], first: str | None = None, last: str | None = None) -> list[str]:
    return sorted(d for d in data.get("days", {}) if (first is None or d >= first) and (last is None or d <= last))


def tape_days(data: dict[str, Any]) -> set[str]:
    return set(data.get("tape", {}))


def status() -> dict[str, Any]:
    """What ``data_status`` says about the table: days built, the tape stage's days, where, and whether stale."""
    try:
        data = load_manifest()
    except (UnknownSignalsSchema, ValueError) as exc:
        return {"error": f"{type(exc).__name__}: {exc}", "root": str(root())}
    days = built_days(data)
    out: dict[str, Any] = {"root": str(root()), "days": len(days), "first": days[0] if days else None,
                           "last": days[-1] if days else None, "tape_days": len(data.get("tape", {})),
                           "stock_days": sum(int(v.get("stock_days") or 0) for v in data.get("days", {}).values()),
                           "builder": data.get("builder")}
    if data.get("builder") != BUILDER:
        out["stale"] = f"built by builder {data.get('builder')}, this code is {BUILDER}: build again"
    if not days:
        out["note"] = "not built: py -3 research/signals/build_signals.py"
    updated = manifest_path().stat().st_mtime if manifest_path().is_file() else None
    out["updated"] = time.strftime("%Y-%m-%d %H:%M", time.localtime(updated)) if updated else None
    return out
