"""Validate compatibility capture files and report every discarded row."""
from __future__ import annotations

import json
import logging
import math
from pathlib import Path
from typing import Any

from capture.schema import validate_version, valid_timestamp

logger = logging.getLogger(__name__)


def new_diagnostics() -> dict:
    return dict(malformed_rows=0, invalid_timestamp_rows=0, invalid_rows=0,
                l2_total=0, l2_loaded=0, l2_decimated=False, legacy_schema=False)


def read_jsonl(path: Path, diagnostics: dict | None = None) -> list[dict[str, Any]]:
    stats = diagnostics if diagnostics is not None else new_diagnostics()
    if not path.is_file() or path.stat().st_size == 0:
        return []
    rows: list[dict[str, Any]] = []
    dropped = 0
    with path.open("rb") as fh:
        for line in fh:
            if not line.strip():
                continue
            try:
                row = json.loads(line.decode("utf-8"))
                if not isinstance(row, dict):
                    raise ValueError("capture row must be an object")
            except (ValueError, UnicodeError):
                dropped += 1
                continue
            stats["legacy_schema"] = validate_version(row) or stats["legacy_schema"]
            rows.append(row)
    stats["malformed_rows"] += dropped
    if dropped:
        logger.warning("CAPTURE replay: dropped %d unparseable line(s) from %s; %d rows loaded",
                       dropped, path, len(rows))
    return rows


def _positive(value: Any) -> bool:
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value) and value > 0)


def _nonnegative(value: Any) -> bool:
    return value == 0 and not isinstance(value, bool) or _positive(value)


def _optional_numbers(row: dict, fields: tuple[str, ...], predicate=_nonnegative) -> bool:
    return all(row.get(key) is None or predicate(row[key]) for key in fields)


def _levels(value: Any) -> bool:
    return isinstance(value, list) and all(
        isinstance(level, dict) and _positive(level.get("price")) and _nonnegative(level.get("size"))
        for level in value)


def usable_rows(rows: list[dict[str, Any]], kind: str, symbol: str,
                diagnostics: dict | None = None) -> list[dict[str, Any]]:
    """All streams need finite timestamps and kind-specific valid content."""
    stats = diagnostics if diagnostics is not None else new_diagnostics()
    accepted = []
    for row in rows:
        if not valid_timestamp(row.get("ts")):
            stats["invalid_timestamp_rows"] += 1
            continue
        valid = str(row.get("symbol") or symbol).upper() == symbol.upper()
        if kind == "prints":
            valid = (valid and _positive(row.get("price")) and _optional_numbers(row, ("size",))
                     and _optional_numbers(row, ("bid", "ask"), _positive))
        elif kind == "quotes":
            # The recorder writes the top of book with ``last: null`` (``capture.bridge_ibkr``):
            # a quote row needs one positive price of any kind, and every price it carries
            # positive. Requiring a last discarded every recorded quote (QA 2026-09-22, R12).
            valid = (valid and any(_positive(row.get(key)) for key in ("last", "price", "bid", "ask"))
                     and _optional_numbers(row, ("bid_size", "ask_size", "volume"))
                     and _optional_numbers(row, ("bid", "ask", "prev_close", "last", "price"), _positive))
        elif kind == "l2":
            valid = valid and all(_levels(row.get(side, [])) for side in ("bids", "asks"))
        else:
            valid = valid and all(_positive(row.get(long) or row.get(short))
                                  for long, short in (("open", "o"), ("high", "h"), ("low", "l"), ("close", "c")))
            valid = valid and _optional_numbers(row, ("volume", "v"))
        if not valid:
            stats["invalid_rows"] += 1
            continue
        accepted.append({**row, "symbol": symbol.upper()})
    if len(accepted) != len(rows):
        logger.warning("CAPTURE replay: dropped %d unusable %s rows", len(rows) - len(accepted), kind)
    return sorted(accepted, key=lambda row: row["ts"])


def sample_l2(rows: list[dict], limit: int, diagnostics: dict) -> list[dict]:
    """Bound memory retained by playback while preserving first and final books."""
    total = len(rows)
    if total > limit:
        rows = [rows[i * (total - 1) // (limit - 1)] for i in range(limit)]
        logger.warning("CAPTURE replay: L2 decimated from %d to %d snapshots", total, len(rows))
    diagnostics.update(l2_total=total, l2_loaded=len(rows), l2_decimated=total > len(rows))
    return rows
