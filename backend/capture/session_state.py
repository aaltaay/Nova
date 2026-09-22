"""Crash-recovery marker for session Record (D-067).

``recorder`` keeps its sessions in process memory, so a crash, ``--reload``,
Ctrl-C or a Desktop sidecar respawn used to leave a session directory in a
state nothing could ever finalize: ``manifest.json`` still held only the
``start_recorder`` shape, so ``sessions.list_sessions`` reported ``prints: -1``
("present but unknown") for that day forever, and the only recovery was the
operator deleting the directory by hand.

A tiny marker file under the capture root names every in-flight session.  It
is rewritten on each start and stop and removed when nothing records, so
finding one at startup means exactly one thing: the previous process died
mid-recording.  Startup then recounts each named session from disk, stamps a
terminal ``restart`` segment, and hands the summaries to ``capture.keepalive``.

Owner: ``capture.recorder``.  Invalidation: rewritten on every lifecycle change,
consumed and removed by ``finalize_orphaned_sessions`` at startup.
``schema_version`` is carried so a future shape change can be detected rather
than misread; v1 (one session, flat) is still read.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from capture.constants_capture import (
    CAPTURE_ACTIVE_STATE_NAME,
    CAPTURE_MANIFEST_NAME,
    CAPTURE_STATUS_INTERRUPTED,
    CAPTURE_STOP_RESTART,
    CAPTURE_STREAM_NAMES,
)
from capture.manifest_io import merge, read_json, recount_from_disk, write_json_atomic

logger = logging.getLogger(__name__)
ET = ZoneInfo("America/New_York")

ACTIVE_STATE_SCHEMA_VERSION = 2

# Set by finalize_orphaned_sessions so /api/capture can tell the operator that a
# recording was interrupted rather than silently showing nothing.
_interrupted: list[dict[str, Any]] = []


def reset_for_tests() -> None:
    _interrupted.clear()


def _state_path(root: Path) -> Path:
    return root / CAPTURE_ACTIVE_STATE_NAME


def mark_active(root: Path, *, sessions: list[dict[str, Any]]) -> None:
    """Name every session in flight. Best effort -- never blocks Record.

    Each row is ``{symbol, dir, started_et}``. No rows means nothing records,
    and the marker is removed so startup sees no orphan.
    """
    if not sessions:
        clear_active(root)
        return
    try:
        write_json_atomic(
            _state_path(root),
            {
                "schema_version": ACTIVE_STATE_SCHEMA_VERSION,
                "pid": os.getpid(),
                "sessions": [
                    {
                        "symbol": str(row.get("symbol") or "").upper(),
                        "dir": str(row.get("dir") or ""),
                        "started_et": row.get("started_et"),
                    }
                    for row in sessions
                ],
            },
        )
    except OSError:
        logger.exception("CAPTURE: could not write active-session marker")


def clear_active(root: Path) -> None:
    """Drop the marker after a clean stop, so startup sees no orphan."""
    try:
        _state_path(root).unlink(missing_ok=True)
    except OSError:
        logger.exception("CAPTURE: could not clear active-session marker")


def read_active(root: Path) -> dict[str, Any]:
    return read_json(_state_path(root))


def active_rows(state: dict[str, Any]) -> list[dict[str, Any]]:
    """The sessions a marker names; a v1 marker is one flat session."""
    if not state:
        return []
    rows = state.get("sessions")
    if isinstance(rows, list):
        return [row for row in rows if isinstance(row, dict)]
    if state.get("symbol") or state.get("dir"):
        return [state]
    return []


def last_interrupted() -> dict[str, Any] | None:
    """The first session the previous process died during, if startup found any."""
    return _interrupted[0] if _interrupted else None


def interrupted_sessions() -> list[dict[str, Any]]:
    return [dict(row) for row in _interrupted]


def finalize_orphaned_session(root: Path) -> dict[str, Any] | None:
    """Single-session view of ``finalize_orphaned_sessions`` (kept for callers that expect one)."""
    summaries = finalize_orphaned_sessions(root)
    return summaries[0] if summaries else None


def finalize_orphaned_sessions(root: Path) -> list[dict[str, Any]]:
    """Stamp terminal counts and a ``restart`` segment on every session left open by a crash.

    Returns one recovery summary per session, or ``[]`` when the previous
    shutdown was clean.  Safe to call on every startup; the marker is consumed
    either way.
    """
    state = read_active(root)
    rows = active_rows(state)
    clear_active(root)
    summaries: list[dict[str, Any]] = []
    for row in rows:
        summary = _finalize_row(row, pid=state.get("pid"))
        if summary is not None:
            summaries.append(summary)
            _interrupted.append(summary)
    return summaries


def _finalize_row(row: dict[str, Any], *, pid: Any) -> dict[str, Any] | None:
    raw_dir = str(row.get("dir") or "").strip()
    symbol = str(row.get("symbol") or "").strip().upper()
    session_dir = Path(raw_dir) if raw_dir else None
    if session_dir is None or not session_dir.is_dir():
        logger.warning(
            "CAPTURE: orphaned session marker for %s points at a missing "
            "directory (%s) -- marker cleared",
            symbol or "?",
            raw_dir or "?",
        )
        return None

    counts, torn = recount_from_disk(session_dir)
    man_path = session_dir / CAPTURE_MANIFEST_NAME
    prior = read_json(man_path)
    # The dead segment's own rows: what is on disk now minus what the manifest
    # held when start_recorder seeded it (cumulative counts at segment start).
    base_counts = prior.get("counts") if isinstance(prior.get("counts"), dict) else {}
    segment_counts = {
        name: max(0, int(counts.get(name, 0)) - int(base_counts.get(name) or 0))
        for name in CAPTURE_STREAM_NAMES
    }
    stopped_et = datetime.now(ET).isoformat()
    segment_started = str(prior.get("segment_started_et") or row.get("started_et") or stopped_et)
    man = merge(
        prior,
        base={"symbol": prior.get("symbol") or symbol},
        started_et=segment_started,
        stopped_et=stopped_et,
        status=CAPTURE_STATUS_INTERRUPTED,
        counts=dict(counts),
        segment_counts=segment_counts,
        error=str(prior.get("error") or "") or None,
        reason=CAPTURE_STOP_RESTART,
    )
    man["started_et"] = prior.get("started_et") or row.get("started_et") or segment_started
    man["recovered_et"] = stopped_et
    man["recovered_from_pid"] = pid
    if torn:
        man["torn_tail"] = True
    try:
        write_json_atomic(man_path, man)
    except OSError:
        logger.exception("CAPTURE: could not finalize orphaned manifest %s", man_path)
        return None

    summary = {
        "symbol": man["symbol"],
        "dir": str(session_dir),
        "session_date": session_dir.parent.name,
        "started_et": man.get("started_et"),
        "counts": dict(counts),
        "torn_tail": torn,
        # When the dead process last wrote: the newest stream file. This is what
        # a restart resume is bounded on -- not when the recording began.
        "last_write_ts": _last_write_ts(session_dir),
    }
    logger.warning(
        "CAPTURE: recording of %s was interrupted by a restart -- finalized "
        "from disk as %s, counts=%s",
        summary["symbol"],
        CAPTURE_STATUS_INTERRUPTED,
        counts,
    )
    return summary


def _last_write_ts(session_dir: Path) -> float | None:
    newest: float | None = None
    for name in CAPTURE_STREAM_NAMES:
        try:
            mtime = (session_dir / f"{name}.jsonl").stat().st_mtime
        except OSError:
            continue
        newest = mtime if newest is None else max(newest, mtime)
    return newest
