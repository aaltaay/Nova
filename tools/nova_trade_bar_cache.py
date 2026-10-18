"""Whole-session sub-minute bars per stock-day, kept so a second chart of the same stock-day skips the trades read.

Owner: this module is the only reader and writer of ``<cache_dir>/trade-chart-bars/<date>/<SYMBOL>_<n>s.json``.
Invalidation: an entry is used only while the Massive day file's path, size and modification time and the hash of
the reader's code still match; anything else is a miss that is read again and rewritten. ``schema_version`` 1; an
unknown version is a miss, never a guess. Contract: "Trade charts" in architecture/schema/local-historical-charts.md.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import secrets
import sys
from pathlib import Path
from typing import Any, Callable

REPO = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = 1
MAX_ENTRIES = 2000
FOLDER = "trade-chart-bars"
READER_SOURCES = ("research/market_reads/reads.py", "backend/sim/massive_files.py", "backend/constants_sim.py")
Rows = list[list[float | None]]


def default_root() -> Path:
    sys.path.insert(0, str(REPO / "backend"))
    from paths import cache_dir
    return cache_dir() / FOLDER


def reader_sha256(repo: Path = REPO) -> str:
    digest = hashlib.sha256()
    for relative in READER_SOURCES:
        digest.update(relative.encode() + b"\0" + (repo / relative).read_bytes() + b"\0")
    return digest.hexdigest()


def _source(path: Path) -> dict[str, Any]:
    info = path.stat()
    return {"path": str(path), "size": info.st_size, "mtime_ns": info.st_mtime_ns}


def _entry(root: Path, symbol: str, day: str, bar_seconds: int) -> Path:
    return root / day / f"{symbol}_{bar_seconds}s.json"


def load(root: Path, source: Path, symbol: str, day: str, bar_seconds: int, reader: str) -> Rows | None:
    """The cached rows when every key still matches, else ``None``."""
    try:
        cached = json.loads(_entry(root, symbol, day, bar_seconds).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if (not isinstance(cached, dict) or cached.get("schema_version") != SCHEMA_VERSION
            or cached.get("symbol") != symbol or cached.get("day") != day
            or cached.get("bar_seconds") != bar_seconds or cached.get("reader_sha256") != reader
            or cached.get("source") != _source(source) or not isinstance(cached.get("bars"), list)):
        return None
    return cached["bars"]


def save(root: Path, source: Path, symbol: str, day: str, bar_seconds: int, reader: str, rows: Rows,
         before: dict[str, Any]) -> None:
    """Write atomically, and only when the day file did not change while it was read."""
    if _source(source) != before:
        return
    target = _entry(root, symbol, day, bar_seconds)
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = target.with_name(f".{target.name}.{secrets.token_hex(4)}.tmp")
    staging.write_text(json.dumps({"schema_version": SCHEMA_VERSION, "symbol": symbol, "day": day,
                                   "bar_seconds": bar_seconds, "source": before, "reader_sha256": reader,
                                   "bars": rows}, separators=(",", ":"), allow_nan=False), encoding="utf-8")
    os.replace(staging, target)
    _prune(root)


def _prune(root: Path) -> None:
    entries = sorted(root.glob("*/*.json"), key=lambda p: p.stat().st_mtime_ns)
    for old in entries[:max(0, len(entries) - MAX_ENTRIES)]:
        old.unlink(missing_ok=True)


def rows_from_frame(frame: Any) -> Rows:
    """``market_reads.bars`` output as ``[s, o, h, l, c, v]``; a bucket with no price-setting print keeps ``None``s."""
    rows: Rows = []
    for row in frame.itertuples(index=False):
        stamp = row.time_et
        prices = [float(v) for v in (row.open, row.high, row.low, row.close)]
        rows.append([stamp.hour * 3600 + stamp.minute * 60 + stamp.second,
                     *(None if math.isnan(p) else p for p in prices), float(row.volume)])
    return rows


def day_rows(root: Path, source: Path, symbol: str, day: str, bar_seconds: int,
             read: Callable[[], Any]) -> tuple[Rows, str]:
    """The stock-day's rows and ``"hit"``, ``"miss"`` or ``"miss_unsaved: <why>"``; ``read`` (the front door) runs
    only on a miss. A cache that cannot be written never fails the chart; provenance says so."""
    reader = reader_sha256()
    cached = load(root, source, symbol, day, bar_seconds, reader)
    if cached is not None:
        return cached, "hit"
    before = _source(source)
    rows = rows_from_frame(read())
    try:
        save(root, source, symbol, day, bar_seconds, reader, rows, before)
    except OSError as error:
        return rows, f"miss_unsaved: {type(error).__name__}: {error}"
    return rows, "miss"
