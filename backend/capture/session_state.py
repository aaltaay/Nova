"""Crash-recovery marker for session Record (D-067).

``recorder`` keeps its session in process globals, so a crash, ``--reload``,
Ctrl-C or a Desktop sidecar respawn used to leave the session directory in a
state nothing could ever finalize: ``manifest.json`` still held only the
``start_recorder`` shape, so ``sessions.list_sessions`` reported ``prints: -1``
("present but unknown") for that day forever, and the only recovery was the
operator deleting the directory by hand.

A tiny marker file under the capture root names the in-flight session.  It is
written on start and removed on a clean stop, so finding one at startup means
exactly one thing: the previous process died mid-recording.  Startup then
recounts that session from disk and stamps a terminal status.

Owner: ``capture.recorder``.  Invalidation: removed on clean stop, consumed and
removed by ``finalize_orphaned_session`` at startup.  ``schema_version`` is
carried so a future shape change can be detected rather than misread.
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

ACTIVE_STATE_SCHEMA_VERSION = 1

# Set by finalize_orphaned_session so /api/capture can tell the operator that a
# recording was interrupted rather than silently showing nothing.
_last_interrupted: dict[str, Any] | None = None


def reset_for_tests() -> None:
    global _last_interrupted
    _last_interrupted = None


def _state_path(root: Path) -> Path:
    return root / CAPTURE_ACTIVE_STATE_NAME


def mark_active(root: Path, *, symbol: str, session_dir: Path, started_et: str) -> None:
    """Record that a session is in flight. Best effort -- never blocks Record."""
    try:
        write_json_atomic(
            _state_path(root),
            {
                "schema_version": ACTIVE_STATE_SCHEMA_VERSION,
                "symbol": symbol,
                "dir": str(session_dir),
                "started_et": started_et,
                "pid": os.getpid(),
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


def last_interrupted() -> dict[str, Any] | None:
    """The session the previous process died during, if startup found one."""
    return _last_interrupted


def finalize_orphaned_session(root: Path) -> dict[str, Any] | None:
    """Stamp terminal counts and status on a session left open by a crash.

    Returns the recovery summary, or ``None`` when the previous shutdown was
    clean.  Safe to call on every startup; the marker is consumed either way.
    """
    global _last_interrupted
    state = read_active(root)
    if not state:
        return None

    raw_dir = str(state.get("dir") or "").strip()
    symbol = str(state.get("symbol") or "").strip().upper()
    session_dir = Path(raw_dir) if raw_dir else None
    clear_active(root)

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
    segment_started = str(prior.get("segment_started_et") or state.get("started_et") or stopped_et)
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
    man["started_et"] = prior.get("started_et") or state.get("started_et") or segment_started
    man["recovered_et"] = stopped_et
    man["recovered_from_pid"] = state.get("pid")
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
    _last_interrupted = summary
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
