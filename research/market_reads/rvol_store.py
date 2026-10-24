"""The relative-volume table (#1100): every minute bar of every common stock with its baselines, and one row per
stock-day, built once from the Massive minute and day files so a question over every stock and every day reads it in
seconds instead of re-reading 46 GB of minute files (``architecture/schema/agent-desk.md``, "Relative volume across
every stock, and what came next").

Owner of the files: this module writes them (``write_day``, driven by ``research/rvol/build_rvol.py``) and lists them
for the reads (``research/market_reads/rvol.py``). Invalidation: a day whose minute file, day file or movers session
changed since it was built, a split-table change, or a ``BUILDER`` bump stales that day and every later one (a
baseline reads earlier days). ``SCHEMA_VERSION`` is in the manifest and in each file's metadata; another version is
refused (``UnknownRvolSchema``), never read as found.
"""
from __future__ import annotations

import json
import os
import shutil
import time
from datetime import date
from pathlib import Path
from typing import Any

from market_reads import roots

SCHEMA_VERSION = 1
BUILDER = 1                      # bump when a rule below changes: every day is built again
ROOT_ENV = "NOVA_RVOL_DIR"
DEFAULT_ROOT_WIN = r"F:\Nova\rvol"
RESERVE_GB = 60.0                # never fill the drive the recordings and the read cache share
META_KEY = b"nova_rvol"
KINDS = ("CS", "ADRC", "unknown")
BASE_SESSIONS = 20               # sessions in a minute baseline
DAY_AVG_SESSIONS = 50            # sessions in the day-volume average ("5x the 50-day average")
BASE_MAX_AGE_DAYS = 100          # no baseline session is older than this many calendar days; a longer gap resets
PREV_CLOSE_LOOKBACK_DAYS = 31    # daily.PREV_LOOKBACK_DAYS: how far back the previous session's close is looked for
SESSION_START_M, SESSION_END_M = 4 * 60, 20 * 60
RTH_OPEN_M, RTH_CLOSE_M = 9 * 60 + 30, 16 * 60
MINUTES = SESSION_END_M - SESSION_START_M
# Row groups by time of day, so a read of the premarket or one window skips the rest of the session.
BANDS = ((240, 420), (420, 570), (570, 600), (600, 720), (720, 960), (960, 1200))
RESETS = ("first_seen", "holder_changed", "likely_split")
RULES = {
    "minute": "m is the bar's start, minutes after ET midnight (240 = 04:00); a measure 'at m' counts bars starting "
              "at or before m, known at the end of that minute",
    "cum": "the stock-day's volume of bars starting 04:00 through m",
    "base": "the mean of the baseline sessions' cum through the same minute, on today's share basis",
    "vol5": "volume of bars starting in (m-5, m]; base5 the baseline sessions' mean of the same five minutes",
    "baseline_sessions": f"the symbol's earlier rows here in the same epoch: at most {BASE_SESSIONS} (minute "
                         f"baselines) / {DAY_AVG_SESSIONS} (day_avg_volume), none more than {BASE_MAX_AGE_DAYS} "
                         "calendar days before the day; a session before a listed split counts x basis today / "
                         "basis then",
    "epoch": "the ET date ordinal the baseline started: the first time a symbol is seen (or after a gap over "
             f"{BASE_MAX_AGE_DAYS} days), when the company holding the ticker changes, and on a likely unlisted "
             "split (the movers store's rule); basis restarts at 1.0 with each epoch",
    "prev_close": f"the day file's close of the previous session within {PREV_CLOSE_LOOKBACK_DAYS} days, times the "
                  "listed split factor through the day",
    "volume": "minute bars are Massive's minute file as delivered (Massive's own minute rule, not the consolidated "
              "tape's: no closing cross at 16:00, no prior-reference or odd-lot-only minutes); day_volume is the day "
              "file's whole session with odd lots",
    "kinds": "CS, ADRC and unknown (unlisted or untyped in Massive's ticker list): the type of the company that held "
             "the ticker that day; ETFs, warrants, units, rights and preferreds are not in the table",
}


class UnknownRvolSchema(RuntimeError):
    """The table was written by another schema version: refused, never read or rebuilt over as found."""


def root() -> Path:
    explicit = os.environ.get(ROOT_ENV)
    if explicit:
        return Path(explicit)
    if os.name == "nt" and Path(DEFAULT_ROOT_WIN[:3]).exists():
        return Path(DEFAULT_ROOT_WIN)
    return roots.massive() / "rvol"


def manifest_path() -> Path:
    return root() / "manifest.json"


def minutes_path(day: str) -> Path:
    return root() / "minutes" / day[:4] / f"{day}.parquet"


def days_path(day: str) -> Path:
    return root() / "days" / day[:4] / f"{day}.parquet"


def stop_path() -> Path:
    """``<root>/STOP``: a running build stops after the day in hand."""
    return root() / "STOP"


def new_manifest() -> dict[str, Any]:
    return {"schema_version": SCHEMA_VERSION, "builder": BUILDER, "kinds": list(KINDS), "rules": RULES,
            "splits_fingerprint": None, "days": {}}


def load_manifest(required: bool = False) -> dict[str, Any]:
    """The manifest, or a new empty one; ``required`` raises ``LookupError`` when the table was never built."""
    path = manifest_path()
    if not path.is_file():
        if required:
            raise LookupError(f"no relative-volume table at {root()}: build it with "
                              "py -3 research/rvol/build_rvol.py (about an hour for 2016 on)")
        return new_manifest()
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != SCHEMA_VERSION:
        raise UnknownRvolSchema(f"{path} is schema_version {data.get('schema_version')!r}, this reader is "
                                f"{SCHEMA_VERSION}: build the table again into an empty {ROOT_ENV}")
    return data


def save_manifest(data: dict[str, Any]) -> None:
    path = manifest_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=1, sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)


def free_gb(folder: Path | None = None) -> float:
    folder = folder or root()
    probe = folder
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    return shutil.disk_usage(probe).free / 1e9


def _write(table, path: Path, day: str, name: str, row_groups: list[int] | None) -> None:
    import pyarrow.parquet as pq
    meta = dict(table.schema.metadata or {})
    meta[META_KEY] = json.dumps({"schema_version": SCHEMA_VERSION, "builder": BUILDER, "day": day,
                                 "table": name}).encode()
    table = table.replace_schema_metadata(meta)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".parquet.tmp")
    labels = [c for c in ("date", "symbol", "kind", "split", "reset") if c in table.column_names]
    with pq.ParquetWriter(tmp, table.schema, compression="zstd", compression_level=3,
                          use_dictionary=labels) as writer:
        if row_groups is None:
            writer.write_table(table)
        else:
            start = 0
            for size in row_groups:
                if size:
                    writer.write_table(table.slice(start, size), row_group_size=size)
                start += size
    os.replace(tmp, path)


def write_day(day: str, minutes, days, band_rows: list[int]) -> None:
    """One session's two files, each written whole then renamed into place (a crash leaves the old file or none).
    ``minutes`` is ordered by band, then ``symbol, m``; ``band_rows`` is how many rows each of ``BANDS`` holds."""
    if free_gb() < RESERVE_GB:
        raise OSError(f"{root()} has under {RESERVE_GB:.0f} GB free: the relative-volume table stops here")
    _write(minutes, minutes_path(day), day, "minutes", band_rows)
    _write(days, days_path(day), day, "days", None)


def source_identity(path: Path | None) -> dict[str, int] | None:
    if path is None:
        return None
    stat = Path(path).stat()
    return {"size": int(stat.st_size), "mtime_ns": int(stat.st_mtime_ns)}


def built_days(data: dict[str, Any], first: str | None = None, last: str | None = None) -> list[str]:
    """Built sessions in ``[first, last]``, oldest first."""
    return sorted(d for d in data.get("days", {}) if (first is None or d >= first) and (last is None or d <= last))


def ordinal(day: str) -> int:
    return date.fromisoformat(day).toordinal()


def status() -> dict[str, Any]:
    """What ``data_status`` says about the table: days built, the range, where, and whether a build is stale."""
    try:
        data = load_manifest()
    except (UnknownRvolSchema, ValueError) as exc:
        return {"error": f"{type(exc).__name__}: {exc}", "root": str(root())}
    days = built_days(data)
    out: dict[str, Any] = {"root": str(root()), "days": len(days), "first": days[0] if days else None,
                           "last": days[-1] if days else None, "builder": data.get("builder")}
    if data.get("builder") != BUILDER:
        out["stale"] = f"built by builder {data.get('builder')}, this code is {BUILDER}: build again"
    if not days:
        out["note"] = "not built: py -3 research/rvol/build_rvol.py"
    updated = manifest_path().stat().st_mtime if manifest_path().is_file() else None
    out["updated"] = time.strftime("%Y-%m-%d %H:%M", time.localtime(updated)) if updated else None
    return out
