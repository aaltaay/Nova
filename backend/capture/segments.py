"""A recording's segments as the desk reads them (QA 2026-09-22, C22 / C41 / C64).

The manifest's ``segments`` list gains an entry only when a segment *ends*, so
the segment being written right now is not in it: a first segment read as no
segment at all ("0 segments", no recorded lane), and a resumed recording's
live stretch after its last stop read as a gap. ``with_open_segment`` appends
it while the manifest says ``recording``.

``missing_sec`` is the time no segment covers between the first start and the
last stop -- the gaps a restart or a failure left. A gap that follows a
segment the operator stopped on purpose is not missing: nothing went wrong,
the operator chose it. A quiet stretch inside a segment is not missing either:
the recorder was up and the tape said nothing.

Pure except ``last_write_ts`` (file mtimes); the listing and the capture
player share it so the Records table and the Sim scrubber cannot disagree.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from capture.constants_capture import (
    CAPTURE_STATUS_RECORDING,
    CAPTURE_STATUS_UNLISTED,
    CAPTURE_STOP_OPERATOR,
    CAPTURE_STREAM_NAMES,
    CAPTURE_UNLISTED_TOLERANCE_SEC,
)

ET = ZoneInfo("America/New_York")


def last_write_ts(session_dir: Path) -> float | None:
    """When anything last reached this recording's stream files (newest mtime)."""
    newest: float | None = None
    for name in CAPTURE_STREAM_NAMES:
        try:
            mtime = (session_dir / f"{name}.jsonl").stat().st_mtime
        except OSError:
            continue
        newest = mtime if newest is None else max(newest, mtime)
    return newest


def finished_segments(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    """The manifest's own segment rows (objects only)."""
    segments = manifest.get("segments") if isinstance(manifest, dict) else None
    return [dict(seg) for seg in segments if isinstance(seg, dict)] if isinstance(segments, list) else []


def with_open_segment(manifest: dict[str, Any], session_dir: Path, *, live: bool) -> list[dict[str, Any]]:
    """Finished segments plus the one still being written, when there is one.

    ``live``: this process is recording ``session_dir`` now -- the open segment
    runs to now (``stopped_et`` null). Otherwise a manifest still saying
    ``recording`` was left by a process that is not advancing it here, and its
    segment is bounded by the last write on disk rather than by now.
    """
    segments = finished_segments(manifest)
    started = manifest.get("segment_started_et") if isinstance(manifest, dict) else None
    if not isinstance(manifest, dict) or manifest.get("status") != CAPTURE_STATUS_RECORDING or not isinstance(started, str):
        return segments
    stop: str | None = None
    if not live:
        written = last_write_ts(session_dir)
        stop = datetime.fromtimestamp(written, ET).isoformat() if written is not None else started
    segments.append({"started_et": started, "stopped_et": stop, "status": CAPTURE_STATUS_RECORDING, "reason": None})
    return segments


def recorded_segments(
    manifest: dict[str, Any], session_dir: Path, *, live: bool, last_event_ts: float | None = None,
) -> list[dict[str, Any]]:
    """Every stretch the recording holds data for: finished, open, and unlisted.

    A recorder can keep appending after its segment was closed (QA 2026-09-22,
    R13: 57 % of a GRML session's prints landed after the manifest's last
    stop), so the manifest alone understates the session. When data reaches
    past the last segment's stop -- the newest event (``last_event_ts``, from a
    loaded replay) or else the newest stream write -- by more than
    ``CAPTURE_UNLISTED_TOLERANCE_SEC``, that stretch is listed too, with status
    ``unlisted``: the rows are on disk, so it was recorded, but no segment
    counted it.
    """
    segments = with_open_segment(manifest, session_dir, live=live)
    if not segments or segments[-1].get("stopped_et") is None:
        return segments  # nothing finished yet, or the last one is still open
    last_stop = max((stop for _start, stop, _reason in segment_rows(segments)), default=None)
    reached = last_event_ts if last_event_ts is not None else last_write_ts(session_dir)
    if last_stop is None or reached is None or reached - last_stop <= CAPTURE_UNLISTED_TOLERANCE_SEC:
        return segments
    segments.append({
        "started_et": datetime.fromtimestamp(last_stop, ET).isoformat(),
        "stopped_et": datetime.fromtimestamp(reached, ET).isoformat(),
        "status": CAPTURE_STATUS_UNLISTED,
        "reason": None,
    })
    return segments


def has_unlisted(segments: list[dict[str, Any]]) -> bool:
    """A stretch no manifest segment counted: the manifest's row counts understate it."""
    return any(isinstance(seg, dict) and seg.get("status") == CAPTURE_STATUS_UNLISTED for seg in segments)


def _epoch(value: Any) -> float | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value).timestamp()
    except ValueError:
        return None


def segment_rows(segments: Any) -> list[tuple[float, float, str | None]]:
    """``(start, stop, reason)`` per parsable segment, sorted; an open one runs to now."""
    out: list[tuple[float, float, str | None]] = []
    if not isinstance(segments, list):
        return out
    now = datetime.now().timestamp()
    for segment in segments:
        if not isinstance(segment, dict):
            continue
        start = _epoch(segment.get("started_et"))
        if start is None:
            continue
        stop = _epoch(segment.get("stopped_et"))
        reason = segment.get("reason")
        out.append((start, max(start, stop if stop is not None else now), reason if isinstance(reason, str) else None))
    out.sort(key=lambda row: (row[0], row[1]))
    return out


def segment_spans(segments: Any) -> list[tuple[float, float]]:
    """``[(start_epoch, stop_epoch)]`` per segment, sorted; unparsable rows skipped."""
    return [(start, stop) for start, stop, _reason in segment_rows(segments)]


def spans_payload(segments: Any) -> list[list[int]]:
    """``[[start, stop], ...]`` whole epoch seconds per segment for the listing.

    The Sim scrubber draws these under a downloaded replay so the operator sees
    where Nova itself recorded that symbol; an open segment runs to now.
    """
    return [[int(start), int(-(-stop // 1))] for start, stop in segment_spans(segments)]


def missing_seconds(segments: Any) -> int:
    """Seconds no segment covers between the first start and the last stop, except
    the gaps after a segment the operator stopped on purpose."""
    rows = segment_rows(segments)
    if not rows:
        return 0
    missing = 0.0
    cursor, cursor_reason = rows[0][1], rows[0][2]
    for start, stop, reason in rows[1:]:
        if start > cursor:
            if cursor_reason != CAPTURE_STOP_OPERATOR:
                missing += start - cursor
            cursor, cursor_reason = stop, reason
        elif stop > cursor:
            cursor, cursor_reason = stop, reason
    return int(max(0.0, missing))


def segment_summary(segments: Any, *, finished: Any = None) -> dict[str, Any]:
    """How whole a recording is: segment count, seconds missing, and why the last one ended.

    ``finished`` is the manifest's own list when ``segments`` carries the open
    segment too: the open one has not ended, so ``last_reason`` comes from the
    last *finished* segment.
    """
    rows = segment_rows(segments)
    if not rows:
        return {"segments": 0, "missing_sec": 0, "last_reason": None}
    ended = finished if finished is not None else segments
    last = ended[-1] if isinstance(ended, list) and ended else {}
    return {
        "segments": len(rows),
        "missing_sec": missing_seconds(segments),
        "last_reason": last.get("reason") if isinstance(last, dict) else None,
    }
