"""Resolve local minute ticker/day inputs into a frozen native chart bundle.

maintainer: one-concern local minute source resolution, DuckDB read lock, and frozen bundle hashing must live in one module
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
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
SYMBOL = re.compile(r"[A-Za-z0-9][A-Za-z0-9.^_-]{0,31}\Z")
COLUMNS = ("ticker", "m", "o", "h", "l", "c", "v")
CSV_COLUMNS = ("ticker", "volume", "open", "close", "high", "low", "window_start", "transactions")
NUMERIC = ("TINYINT", "SMALLINT", "INTEGER", "BIGINT", "HUGEINT", "FLOAT", "DOUBLE", "DECIMAL")
COLORS = {"blue", "gold", "grey", "green", "red"}


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


def _valid_label(value: Any, limit: int) -> bool:
    return (
        isinstance(value, str)
        and 1 <= len(value) <= limit
        and value == value.strip()
        and all(ord(c) >= 32 and ord(c) != 127 for c in value)
    )


def validate_as_of_m(as_of_m: Any) -> int | None:
    if as_of_m is None:
        return None
    if isinstance(as_of_m, bool) or not isinstance(as_of_m, int) or not 0 <= as_of_m <= 1440:
        raise HistoricalChartError("invalid_as_of_m", "as_of_m must be an integer minute boundary from 0 through 1440")
    return as_of_m


def validate_annotations(annotations: Any) -> list[dict[str, Any]]:
    if annotations is None:
        return []
    if not isinstance(annotations, list) or len(annotations) > 32:
        raise HistoricalChartError("invalid_annotations", "Annotations must be a list of at most 32 objects")
    result: list[dict[str, Any]] = []
    for item in annotations:
        if not isinstance(item, dict) or item.get("kind") not in {"horizontal_line", "time_marker"}:
            raise HistoricalChartError("invalid_annotations", "Annotation kind must be horizontal_line or time_marker")
        kind = item["kind"]
        field = "price" if kind == "horizontal_line" else "minute"
        required = {"kind", field, "label"}
        if not required <= item.keys() or item.keys() - required - {"color"}:
            raise HistoricalChartError("invalid_annotations", "Annotation contains unsupported or missing fields")
        if not _valid_label(item["label"], 80):
            raise HistoricalChartError("invalid_annotations", "Annotation label must be 1..80 printable characters")
        color = item.get("color", "blue")
        if not isinstance(color, str) or color not in COLORS:
            raise HistoricalChartError("invalid_annotations", "Annotation color must be blue, gold, grey, green or red")
        val = item[field]
        if field == "minute":
            if isinstance(val, bool) or not isinstance(val, int) or not 0 <= val <= 1439:
                raise HistoricalChartError("invalid_annotations", "time_marker minute must be an integer 0..1439")
        else:
            if isinstance(val, bool) or not isinstance(val, (int, float)) or not math.isfinite(val) or val <= 0:
                raise HistoricalChartError("invalid_annotations", "horizontal_line price must be finite and positive")
        cleaned: dict[str, Any] = {"kind": kind, field: float(val) if field == "price" else int(val), "label": item["label"]}
        if "color" in item:
            cleaned["color"] = color
        result.append(cleaned)
    return result


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


def resolve_source(massive_root: Path, day: str, fallback_root: Path | None = None) -> tuple[Path, Path]:
    """Find the approved local day file (.parquet or Massive .csv.gz) across primary and optional fallback roots."""
    roots = [local_path(massive_root)]
    if fallback_root is not None:
        roots.append(local_path(fallback_root))
    for root in roots:
        if not root.is_dir():
            raise HistoricalChartError("unsafe_path", "The minute root must be a local directory")
    year, month = day[:4], day[5:7]
    for root in roots:
        candidates = (
            root / f"d={day}" / "part.parquet",
            root / "minute" / f"d={day}" / "part.parquet",
            root / "minute_aggs_v1" / year / month / f"{day}.csv.gz",
            root / year / month / f"{day}.csv.gz",
        )
        for candidate in candidates:
            try:
                resolved = local_path(candidate)
            except HistoricalChartError as error:
                if error.code == "missing_path":
                    continue
                raise
            if not resolved.is_relative_to(root) or not resolved.is_file():
                raise HistoricalChartError("unsafe_path", "Minute input must be a file inside the approved root")
            return root, resolved
    raise HistoricalChartError("day_missing", "The requested minute day partition is not on disk")


def _read_rows(path: Path, symbol: str, day: str = "") -> list[tuple]:
    try:
        import duckdb
    except ImportError as error:
        raise HistoricalChartError("reader_unavailable", "The optional DuckDB research reader is unavailable") from error
    settings = {"threads": 2, "memory_limit": "256MB", "temp_directory": "",
                "autoinstall_known_extensions": False, "autoload_known_extensions": False}
    try:
        with duckdb.connect(config=settings) as connection:
            allowed = str(path).replace("'", "''")
            connection.execute("SET allowed_paths = ['" + allowed + "']")
            connection.execute("SET enable_external_access = false")
            if path.name.endswith(".csv.gz"):
                csv_cols = (
                    "{'ticker':'VARCHAR','volume':'DOUBLE','open':'DOUBLE','close':'DOUBLE',"
                    "'high':'DOUBLE','low':'DOUBLE','window_start':'BIGINT','transactions':'BIGINT'}"
                )
                raw = connection.execute(
                    f"SELECT window_start,open,high,low,close,volume FROM read_csv(?, header=true, auto_detect=false, columns={csv_cols}) "
                    "WHERE ticker = ? ORDER BY window_start NULLS FIRST LIMIT 1441",
                    [str(path), symbol],
                ).fetchall()
                converted: list[tuple] = []
                for ws, o, h, low, c, v in raw:
                    if ws is None or isinstance(ws, bool) or not isinstance(ws, int):
                        converted.append((None, o, h, low, c, v))
                        continue
                    dt = datetime.fromtimestamp(ws / 1_000_000_000, timezone.utc).astimezone(ET)
                    if (day and dt.date().isoformat() != day) or dt.second != 0 or dt.microsecond != 0:
                        converted.append((-1, o, h, low, c, v))
                        continue
                    converted.append((dt.hour * 60 + dt.minute, o, h, low, c, v))
                return converted
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


def _project_one(massive_root: Path, symbol: str, day: str, fallback_root: Path | None) -> tuple[list[dict[str, int | float]], dict[str, Any]]:
    validate_request(symbol, day)
    _, source = resolve_source(massive_root, day, fallback_root)
    before = _descriptor(source)
    raw = _read_rows(source, symbol, day) if source.name.endswith(".csv.gz") else _read_rows(source, symbol)
    bars = validate_rows(raw)
    local_path(source)
    after = _descriptor(source)
    if before != after:
        raise HistoricalChartError("input_changed", "Minute input changed during the exact ticker projection")
    is_csv = source.name.endswith(".csv.gz")
    source_info = dict(
        before,
        columns=list(CSV_COLUMNS if is_csv else COLUMNS),
        exact_ticker=symbol,
        reader="local_duckdb_massive_csv_gz" if is_csv else "local_duckdb_parquet",
        price_adjustment="none_same_session",
    )
    return bars, source_info


def resolve_bundle(
    massive_root: Path,
    symbol: str,
    day: str,
    output: Path,
    *,
    as_of_m: int | None = None,
    annotations: list[dict[str, Any]] | None = None,
    fallback_root: Path | None = None,
) -> dict[str, Any]:
    """Validate/read one local file and claim a new bundle; no export or desk side effects."""
    began = time.perf_counter()
    validate_request(symbol, day)
    checked_as_of = validate_as_of_m(as_of_m)
    checked_notes = validate_annotations(annotations)
    target = local_path(output, must_exist=False)
    parent = local_path(target.parent)
    if not parent.is_dir() or target.exists():
        raise HistoricalChartError("output_exists", "Use a new output directory with an existing local parent")
    bars, source_info = _project_one(massive_root, symbol, day, fallback_root)
    try:
        target.mkdir(exist_ok=False)
    except FileExistsError as error:
        raise HistoricalChartError("output_exists", "Output was already claimed") from error
    local_path(target)
    (target / "bars").mkdir()
    projection = target / "bars" / "01.json"
    _write_json(projection, {"day": day, "ticker": symbol,
        "time_zone": "America/New_York", "m_semantics": "minute_START",
        "price_units": "raw_same_session_" + day, "observed_source_start_m": 0,
        "observed_source_end_exclusive_m": 1440, "bars": bars})
    entry: dict[str, Any] = {
        "day": day,
        "ticker": symbol,
        "annotations": checked_notes,
        "bar_projection": {"path": str(projection), "sha256": file_sha256(projection)},
    }
    if checked_as_of is not None:
        entry["as_of_m"] = checked_as_of
    selection = target / "selection.json"
    _write_json(selection, {"schema_version": 1, "kind": "historical_ohlcv", "family": "historical-chart",
        "selected": [entry]})
    receipt: dict[str, Any] = {
        "selection_path": str(selection),
        "selection_sha256": file_sha256(selection),
        "bars": len(bars),
        "symbol": symbol,
        "date": day,
        "source": source_info,
        "resolve_freeze_ms": (time.perf_counter() - began) * 1000,
    }
    if checked_as_of is not None:
        receipt["as_of_m"] = checked_as_of
    _write_json(target / "provenance.json", receipt)
    return receipt


def resolve_gallery_bundle(
    massive_root: Path,
    entries: list[dict[str, Any]],
    output: Path,
    *,
    family: str = "historical-chart",
    fallback_root: Path | None = None,
) -> dict[str, Any]:
    """Validate/read 1..9 local symbol/day entries into a single frozen gallery bundle."""
    began = time.perf_counter()
    if not _valid_label(family, 80):
        raise HistoricalChartError("invalid_family", "Family label must be 1..80 printable characters")
    if not isinstance(entries, list) or not 1 <= len(entries) <= 9:
        raise HistoricalChartError("invalid_entries", "Gallery requires 1 through 9 entry objects")
    normalized: list[tuple[tuple[str, str, int], str, str, int | None, list[dict[str, Any]]]] = []
    seen_identities: set[tuple[str, str, int]] = set()
    for raw in entries:
        if not isinstance(raw, dict):
            raise HistoricalChartError("invalid_entries", "Each gallery entry must be an object")
        symbol = raw.get("symbol") or raw.get("ticker")
        day = raw.get("date") or raw.get("day")
        validate_request(symbol, day)
        as_of_m = validate_as_of_m(raw.get("as_of_m"))
        notes = validate_annotations(raw.get("annotations"))
        ident = (day, symbol, -1 if as_of_m is None else as_of_m)
        if ident in seen_identities:
            raise HistoricalChartError("duplicate_entry", "Gallery entries must have unique (date, symbol, as_of_m) identities")
        seen_identities.add(ident)
        normalized.append((ident, symbol, day, as_of_m, notes))
    normalized.sort(key=lambda item: item[0])
    target = local_path(output, must_exist=False)
    parent = local_path(target.parent)
    if not parent.is_dir() or target.exists():
        raise HistoricalChartError("output_exists", "Use a new output directory with an existing local parent")
    projected = [
        (symbol, day, as_of_m, notes, *_project_one(massive_root, symbol, day, fallback_root))
        for _, symbol, day, as_of_m, notes in normalized
    ]
    try:
        target.mkdir(exist_ok=False)
    except FileExistsError as error:
        raise HistoricalChartError("output_exists", "Output was already claimed") from error
    local_path(target)
    (target / "bars").mkdir()
    selected: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    total_bars = 0
    for idx, (symbol, day, as_of_m, notes, bars, source_info) in enumerate(projected, 1):
        projection = target / "bars" / f"{idx:02d}.json"
        _write_json(projection, {"day": day, "ticker": symbol,
            "time_zone": "America/New_York", "m_semantics": "minute_START",
            "price_units": "raw_same_session_" + day, "observed_source_start_m": 0,
            "observed_source_end_exclusive_m": 1440, "bars": bars})
        entry_obj: dict[str, Any] = {
            "day": day,
            "ticker": symbol,
            "annotations": notes,
            "bar_projection": {"path": str(projection), "sha256": file_sha256(projection)},
        }
        if as_of_m is not None:
            entry_obj["as_of_m"] = as_of_m
        selected.append(entry_obj)
        sources.append(source_info)
        total_bars += len(bars)
    selection = target / "selection.json"
    _write_json(selection, {"schema_version": 1, "kind": "historical_ohlcv", "family": family, "selected": selected})
    receipt: dict[str, Any] = {
        "selection_path": str(selection),
        "selection_sha256": file_sha256(selection),
        "selected_count": len(selected),
        "bars": total_bars,
        "family": family,
        "sources": sources,
        "resolve_freeze_ms": (time.perf_counter() - began) * 1000,
    }
    if len(selected) == 1:
        receipt["symbol"] = selected[0]["ticker"]
        receipt["date"] = selected[0]["day"]
        receipt["source"] = sources[0]
    _write_json(target / "provenance.json", receipt)
    return receipt
