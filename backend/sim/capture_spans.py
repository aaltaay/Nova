"""Where a loaded capture holds data, for the capture player (QA 2026-09-22, R11 / R13 / R24).

A recording has gaps -- a restart, a recorder failure, the operator stopping it
-- and inside one nothing was recorded. The player used to answer "the newest
row at or before the playhead" with no regard to them, so a playhead inside an
84-minute gap showed the book and tape from before it as the current market and
a practice Market order filled at that old quote. A gap is a stated absence
(no inferred market data): a read at a moment no recorded stretch covers
answers nothing, and a read inside a stretch never reaches back across the gap
before it.

Stretches come from the manifest's segments (finished, the one still open, and
data written past the last segment, R13). A capture whose manifest names no
segment cannot say where the recorder was up, so its reads stay unbounded --
unknown is not a gap.
"""
from __future__ import annotations

import bisect
import logging
from pathlib import Path
from typing import Any

from capture.constants_capture import CAPTURE_ODD_LOT_CONDITION
from capture.segments import recorded_segments, segment_spans

logger = logging.getLogger(__name__)

Span = tuple[float, float]


def load_spans(
    manifest: dict[str, Any], root: Path, *, live: bool, first_ts: float, last_ts: float,
) -> tuple[list[dict[str, Any]], list[Span]]:
    """``(segments, spans)`` for a capture just loaded: what the band draws, what reads are bounded by."""
    segments = recorded_segments(manifest, root, live=live, last_event_ts=last_ts)
    spans = segment_spans(segments)
    if not spans:
        # A manifest that names no segment cannot say where the recorder was up:
        # unknown is not a gap, so reads stay unbounded, as they always were.
        return segments, []
    if live:
        # The open segment runs to now; the loaded events end at the load, and
        # the live-edge reload folds in what lands after it.
        spans = [(a, max(b, last_ts)) for a, b in spans]
    return segments, _merge(spans)


def _merge(spans: list[Span]) -> list[Span]:
    merged: list[Span] = []
    for start, stop in sorted(spans):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], stop))
        else:
            merged.append((start, stop))
    return merged


def span_start(spans: list[Span], t: float) -> float | None:
    """Start of the recorded stretch holding ``t``; ``None`` in a gap (or before / after the recording)."""
    for start, stop in spans:
        if start <= t <= stop:
            return start
        if start > t:
            break
    return None


def newest_in_span(keys: list[float], spans: list[Span], t: float) -> int:
    """Index of the newest row at or before ``t`` inside ``t``'s own stretch, else -1."""
    start = span_start(spans, t)
    if start is None or not keys:
        return -1
    i = bisect.bisect_right(keys, t) - 1
    return i if i >= 0 and keys[i] >= start else -1


def is_odd_lot(row: dict[str, Any]) -> bool:
    """An odd-lot print (sale condition ``I``): it never sets the last or fills a practice order."""
    return CAPTURE_ODD_LOT_CONDITION in str(row.get("conditions") or "").upper()


def previous_close_for(symbol: str, date: str) -> float | None:
    """The replayed session's previous close, read once per load (the quote head's change)."""
    try:
        from sim.history_cache import previous_close

        return previous_close(symbol.upper(), {"date": date})
    except Exception:
        logger.warning("CAPTURE PLAY: previous close unavailable for %s %s", symbol, date, exc_info=True)
        return None


def recording_here(root: Path) -> bool:
    """This process is recording ``root`` right now (the recorder's lock-free status)."""
    try:
        from capture.recorder import status as recorder_status

        sessions = recorder_status().get("sessions") or {}
    except Exception:
        logger.warning("CAPTURE PLAY: recorder status unavailable; an open segment ends at its last write",
                       exc_info=True)
        return False
    return any(isinstance(row, dict) and row.get("recording") and row.get("dir") == str(root)
               for row in sessions.values())
