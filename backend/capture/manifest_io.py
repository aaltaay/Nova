"""Durable manifest I/O for session Record (D-067).

Two jobs, both pure enough to test without a running recorder:

* **Atomic write** -- ``manifest.json`` is the only record of what a session
  contains.  ``Path.write_text`` truncates first, so a crash mid-write leaves a
  zero-byte or half-written file that ``sessions.list_sessions`` silently reads
  as ``{}``; every count, status and source for that session vanishes.  Write to
  a sibling temp file, flush + ``fsync``, then ``os.replace`` (atomic on POSIX
  and Windows).  Same pattern as ``backend/archive/manifest.py``.

* **Merge, never clobber** -- a second Record on the same symbol+day appends to
  the existing jsonl files, so the manifest must accumulate too.  ``merge`` keeps
  the first ``started_et``, appends a ``segments`` entry per run, and carries a
  cumulative ``counts`` that matches the rows actually on disk.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from capture.constants_capture import CAPTURE_STREAM_NAMES

logger = logging.getLogger(__name__)


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    """Write ``payload`` so a crash leaves either the old file or the new one."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp{os.getpid()}")
    try:
        with tmp.open("w", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, indent=2) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)


def read_json(path: Path) -> dict[str, Any]:
    """Best-effort read; a missing or corrupt manifest reads as ``{}``."""
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        logger.warning("CAPTURE: manifest unreadable, treating as empty: %s", path)
        return {}
    return data if isinstance(data, dict) else {}


def prior_counts(manifest: dict[str, Any]) -> dict[str, int]:
    """Cumulative counts recorded by earlier segments, keyed by stream."""
    raw = manifest.get("counts")
    if not isinstance(raw, dict):
        return {}
    out: dict[str, int] = {}
    for name in CAPTURE_STREAM_NAMES:
        try:
            out[name] = int(raw.get(name) or 0)
        except (TypeError, ValueError):
            out[name] = 0
    return out


def merge(
    prior: dict[str, Any],
    *,
    base: dict[str, Any],
    started_et: str,
    stopped_et: str | None,
    status: str,
    counts: dict[str, int],
    segment_counts: dict[str, int],
    error: str | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    """Fold one segment into ``prior`` without destroying what it already holds.

    ``counts`` is cumulative (matches rows on disk); ``segment_counts`` is this
    run's own delta.  The first ``started_et`` ever written is preserved, so the
    forensic record of when the session actually began survives a resume.
    ``reason`` names why the segment ended (operator / rotation / failure /
    restart) so a gap between segments can say what made it.
    """
    man: dict[str, Any] = dict(prior) if prior else {}
    man.update(base)
    # Never let a resume overwrite when the session really began.
    man["started_et"] = prior.get("started_et") or started_et
    man["segment_started_et"] = started_et
    man["stopped_et"] = stopped_et
    man["complete"] = False  # full-day completeness is never assumed
    man["status"] = status
    man["counts"] = dict(counts)

    segments = prior.get("segments")
    segments = list(segments) if isinstance(segments, list) else []
    segments.append(
        {
            "started_et": started_et,
            "stopped_et": stopped_et,
            "status": status,
            "reason": reason,
            "counts": dict(segment_counts),
        }
    )
    man["segments"] = segments
    if error:
        man["error"] = error
    else:
        man.pop("error", None)
    return man


def count_rows(path: Path) -> tuple[int, bool]:
    """Count parseable jsonl rows; report whether the final line is torn.

    Only used to rebuild terminal counts for a session the process died during
    -- one-shot recovery, never the hot ``list_sessions`` path.
    """
    if not path.is_file():
        return 0, False
    rows = 0
    torn = False
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    json.loads(stripped)
                except ValueError:
                    # Only a torn *final* line is expected after a hard kill;
                    # anything earlier is still surfaced by the same warning.
                    torn = True
                    continue
                rows += 1
    except OSError:
        logger.exception("CAPTURE: could not recount %s", path)
        return rows, torn
    if torn:
        logger.warning(
            "CAPTURE: %s has a truncated/unparseable line (torn tail from an "
            "interrupted write) -- %d whole rows kept",
            path,
            rows,
        )
    return rows, torn


def recount_from_disk(session_dir: Path) -> tuple[dict[str, int], bool]:
    """Rebuild counts for every stream in ``session_dir``."""
    counts: dict[str, int] = {}
    any_torn = False
    for name in CAPTURE_STREAM_NAMES:
        rows, torn = count_rows(session_dir / f"{name}.jsonl")
        counts[name] = rows
        any_torn = any_torn or torn
    return counts, any_torn
