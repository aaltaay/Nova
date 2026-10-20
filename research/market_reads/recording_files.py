"""A Session Record's jsonl streams, read by byte offset (ADR 059, #1064).

``<capture root>/<day>/<SYMBOL>/{prints,quotes,l2}.jsonl`` hold one JSON row per line, written in ``ts`` order: the
recorder refuses a row that moves backwards (``capture/fidelity.py`` ``admit``). A moment or a window is therefore
found by bisecting byte offsets -- a few 64 KB reads of the drive the desk also uses -- and never by reading a
multi-hundred-megabyte file from its start. Files are opened ``rb`` and never written; a line the live recorder is
still writing (no newline, torn) is skipped like any unparseable line.

``SLACK_SEC`` widens a window search on both ends so a file written before that rule, with a row a second or two out of
order, still gives its row; a row further out of order than that is not searched for.
"""
from __future__ import annotations

import json
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any, BinaryIO

from market_reads import REPO, roots  # noqa: F401  (REPO puts backend/ on sys.path)

from capture.schema import valid_timestamp
from capture.storage import session_path

BLOCK = 64 * 1024
SLACK_SEC = 2.0


def session_dir(day: str, symbol: str) -> Path:
    """The Session Record's folder (``ValueError`` for a day or symbol that names none; it need not exist)."""
    return session_path(day, symbol, root=roots.sim_capture())


def read_manifest(folder: Path) -> tuple[dict[str, Any], str | None]:
    """``(manifest, problem)``: ``{}`` and what is wrong when the manifest is missing or unreadable."""
    path = folder / "manifest.json"
    if not path.is_file():
        return {}, f"{path} is not there"
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {}, f"{path} is unreadable: {type(exc).__name__}"
    return (manifest, None) if isinstance(manifest, dict) else ({}, f"{path} is not a manifest object")


def _row(line: bytes) -> dict[str, Any] | None:
    """The line's row when it parses to an object with a usable ``ts``; None for anything else."""
    try:
        row = json.loads(line)
    except (ValueError, UnicodeError):
        return None
    return row if isinstance(row, dict) and valid_timestamp(row.get("ts")) else None


def _first_line_at(fh: BinaryIO, offset: int, size: int) -> tuple[int, bytes] | None:
    """``(start, line)`` of the first whole line that begins at or after ``offset``; None past the last one."""
    if offset <= 0:
        start = 0
        fh.seek(0)
    else:
        fh.seek(offset - 1)
        fh.readline()
        start = fh.tell()
    if start >= size:
        return None
    line = fh.readline()
    return (start, line) if line else None


def seek_before(fh: BinaryIO, size: int, target: float) -> int:
    """A byte offset to scan forward from: every row with ``ts >= target`` is at or after the first whole line from it."""
    lo, hi = 0, size
    while hi - lo > BLOCK:
        mid = (lo + hi) // 2
        probe = _first_line_at(fh, mid, size)
        if probe is None:
            hi = mid
            continue
        row = _row(probe[1])
        if row is None or row["ts"] < target:
            lo = mid
        else:
            hi = mid
    return lo


def _rows_from(fh: BinaryIO, offset: int, size: int) -> Iterator[dict[str, Any]]:
    probe = _first_line_at(fh, offset, size)
    if probe is None:
        return
    fh.seek(probe[0])
    for line in fh:
        row = _row(line)
        if row is not None:
            yield row


def newest_at_or_before(path: Path, at_ts: float, symbol: str | None = None) -> dict[str, Any] | None:
    """The newest row with ``ts <= at_ts`` (of ``symbol`` when a row names one), or None."""
    if not path.is_file():
        return None
    newest = None
    with path.open("rb") as fh:
        size = os.fstat(fh.fileno()).st_size
        for row in _rows_from(fh, seek_before(fh, size, at_ts), size):
            if row["ts"] > at_ts:
                break
            if symbol is None or str(row.get("symbol") or symbol).upper() == symbol:
                newest = row
    return newest


def rows_between(path: Path, start_ts: float, end_ts: float, limit: int,
                 symbol: str | None = None) -> tuple[list[dict[str, Any]], bool]:
    """``(rows, capped)``: rows with ``start_ts <= ts < end_ts`` in file order, at most ``limit`` of them; ``capped``
    says more matched."""
    out: list[dict[str, Any]] = []
    if not path.is_file():
        return out, False
    with path.open("rb") as fh:
        size = os.fstat(fh.fileno()).st_size
        for row in _rows_from(fh, seek_before(fh, size, start_ts - SLACK_SEC), size):
            ts = row["ts"]
            if ts >= end_ts + SLACK_SEC:
                break
            if ts < start_ts or ts >= end_ts:
                continue
            if symbol is not None and str(row.get("symbol") or symbol).upper() != symbol:
                continue
            if len(out) >= limit:
                return out, True
            out.append(row)
    return out, False
