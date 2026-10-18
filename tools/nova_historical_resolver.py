"""Resolve one exact local minute ticker/day into a frozen native chart bundle.

No backend, market-data service, account, network, environment data root or renderer
is imported. Input schema and SOP: architecture/schema/local-historical-charts.md.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
import time
from datetime import date
from pathlib import Path
from typing import Any

SYMBOL = re.compile(r"[A-Za-z0-9][A-Za-z0-9.^_-]{0,31}\Z")
COLUMNS = ("ticker", "m", "o", "h", "l", "c", "v")
NUMERIC = ("TINYINT", "SMALLINT", "INTEGER", "BIGINT", "HUGEINT", "FLOAT", "DOUBLE", "DECIMAL")


class HistoricalChartError(ValueError):
    """Stable error code for CLI/MCP callers, without leaking provider exceptions."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def validate_request(symbol: str, day: str) -> None:
    if not isinstance(symbol, str) or not SYMBOL.fullmatch(symbol):
        raise HistoricalChartError("invalid_symbol", "An exact ticker identifier is required")
    try:
        parsed = date.fromisoformat(day)
    except (TypeError, ValueError) as error:
        raise HistoricalChartError("invalid_date", "Use an exact YYYY-MM-DD date") from error
    if parsed.isoformat() != day:
        raise HistoricalChartError("invalid_date", "Use an exact YYYY-MM-DD date")


def local_path(value: Path | str, *, must_exist: bool = True) -> Path:
    """Reject traversal, network roots and every existing reparse component."""
    text = str(value)
    path = Path(value)
    if (not path.is_absolute() or "://" in text or text.startswith(("\\\\", "//"))
            or ".." in path.parts):
        raise HistoricalChartError("unsafe_path", "An absolute local path without traversal is required")
    if os.name == "nt":
        import ctypes

        if ctypes.windll.kernel32.GetDriveTypeW(str(path.anchor)) == 4:
            raise HistoricalChartError("unsafe_path", "Network drives are not supported")
    for part in (path, *path.parents):
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise HistoricalChartError("unsafe_path", "Symlink, junction and reparse paths are not supported")
    try:
        return path.resolve(strict=must_exist)
    except FileNotFoundError as error:
        raise HistoricalChartError("missing_path", "The requested local path does not exist") from error


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _descriptor(path: Path) -> dict[str, Any]:
    before = path.stat()
    digest = file_sha256(path)
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise HistoricalChartError("input_changed", "Minute input changed while being hashed")
    return {"path": str(path), "sha256": digest, "size": after.st_size, "mtime_ns": after.st_mtime_ns}


def _read_rows(path: Path, symbol: str) -> list[tuple]:
    try:
        import duckdb
    except ImportError as error:
        raise HistoricalChartError("reader_unavailable", "The optional DuckDB research reader is unavailable") from error
    # Local file allowlist prevents extension/network readers, globbing or arbitrary
    # external access, including if a future query accidentally gains a new reader.
    settings = {"threads": 2, "memory_limit": "256MB", "temp_directory": "",
                "autoinstall_known_extensions": False, "autoload_known_extensions": False}
    try:
        with duckdb.connect(config=settings) as connection:
            allowed = str(path).replace("'", "''")
            connection.execute("SET allowed_paths = ['" + allowed + "']")
            # Lock external access after connection settings: DuckDB rejects
            # setting temp_directory when the lock is applied in connect(config).
            connection.execute("SET enable_external_access = false")
            description = connection.execute(
                "SELECT ticker,m,o,h,l,c,v FROM read_parquet(?, hive_partitioning=false) LIMIT 0", [str(path)]
            ).description
            if str(description[0][1]) != "VARCHAR" or str(description[1][1]) not in NUMERIC[:5]:
                raise HistoricalChartError("invalid_schema", "Expected ticker text and integer ET minute starts")
            if any(not str(column[1]).startswith(NUMERIC) for column in description[2:]):
                raise HistoricalChartError("invalid_schema", "Expected numeric OHLCV columns")
            return connection.execute(
                "SELECT m,o,h,l,c,v FROM read_parquet(?, hive_partitioning=false) "
                "WHERE ticker = ? ORDER BY m NULLS FIRST LIMIT 1441", [str(path), symbol]
            ).fetchall()
    except HistoricalChartError:
        raise
    except duckdb.Error as error:
        raise HistoricalChartError("invalid_input", "The local minute file could not be read with the confirmed schema") from error


def validate_rows(rows: list[tuple]) -> list[dict[str, int | float]]:
    if not rows:
        raise HistoricalChartError("symbol_missing", "The exact ticker has no bars in the requested day file")
    if len(rows) > 1440:
        raise HistoricalChartError("invalid_rows", "A single ticker/day cannot contain more than 1440 unique minutes")
    bars = []
    previous = -1
    for row in rows:
        try:
            minute, *values = row
            if isinstance(minute, bool) or not isinstance(minute, int) or not previous < minute < 1440:
                raise ValueError("noninteger, duplicate or out-of-range minute")
            o, h, low, c, v = (float(value) for value in values)
            if (not all(math.isfinite(x) for x in (o, h, low, c, v)) or min(o, h, low, c) <= 0
                    or v < 0 or h < max(o, low, c) or low > min(o, h, c)):
                raise ValueError("invalid OHLCV")
        except (TypeError, ValueError, OverflowError) as error:
            raise HistoricalChartError("invalid_rows", "The ticker/day contains invalid or duplicate minute bars") from error
        bars.append(dict(m=minute, o=o, h=h, l=low, c=c, v=v))
        previous = minute
    return bars


def _write_json(path: Path, value: Any) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")


def resolve_bundle(massive_root: Path, symbol: str, day: str, output: Path) -> dict[str, Any]:
    """Validate/read one local file and claim a new bundle; no export or desk side effects."""
    began = time.perf_counter()
    validate_request(symbol, day)
    root = local_path(massive_root)
    if not root.is_dir():
        raise HistoricalChartError("unsafe_path", "The minute root must be a local directory")
    source = root / ("d=" + day) / "part.parquet"
    try:
        source = local_path(source)
    except HistoricalChartError as error:
        if error.code == "missing_path":
            raise HistoricalChartError("day_missing", "The requested minute day partition is not on disk") from error
        raise
    if not source.is_relative_to(root) or not source.is_file():
        raise HistoricalChartError("unsafe_path", "Minute input must be a file inside the approved root")
    target = local_path(output, must_exist=False)
    parent = local_path(target.parent)
    if not parent.is_dir() or target.exists():
        raise HistoricalChartError("output_exists", "Use a new output directory with an existing local parent")
    before = _descriptor(source)
    bars = validate_rows(_read_rows(source, symbol))
    local_path(source)
    after = _descriptor(source)
    if before != after:
        raise HistoricalChartError("input_changed", "Minute input changed during the exact ticker projection")
    source_info = dict(before, columns=list(COLUMNS), exact_ticker=symbol,
                       reader="local_duckdb_parquet", price_adjustment="none_same_session")
    try:
        target.mkdir(exist_ok=False)
    except FileExistsError as error:
        raise HistoricalChartError("output_exists", "Output was already claimed") from error
    local_path(target)  # Recheck every parent after claiming the output directory.
    # Fixed child names: a ticker never becomes a filesystem path.
    (target / "bars").mkdir()
    projection = target / "bars" / "01.json"
    _write_json(projection, {"day": day, "ticker": symbol,
        "time_zone": "America/New_York", "m_semantics": "minute_START",
        "price_units": "raw_same_session_" + day, "observed_source_start_m": 0,
        "observed_source_end_exclusive_m": 1440, "bars": bars})
    selection = target / "selection.json"
    _write_json(selection, {"schema_version": 1, "kind": "historical_ohlcv", "family": "historical-chart",
        "selected": [{"day": day, "ticker": symbol, "annotations": [],
                      "bar_projection": {"path": str(projection), "sha256": file_sha256(projection)}}]})
    receipt = {"selection_path": str(selection), "selection_sha256": file_sha256(selection),
               "bars": len(bars), "symbol": symbol, "date": day, "source": source_info,
               "resolve_freeze_ms": (time.perf_counter() - began) * 1000}
    _write_json(target / "provenance.json", receipt)
    return receipt
