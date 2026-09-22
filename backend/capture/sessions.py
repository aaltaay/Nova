"""List recorded sessions under the capture root (F:\\Nova\\sim_capture)."""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from capture.recorder import capture_root
from capture.schema import read_manifest

logger = logging.getLogger(__name__)


def _file_bytes(path: Path) -> int:
    try:
        return path.stat().st_size if path.is_file() else 0
    except OSError:
        return 0


def list_sessions() -> dict[str, Any]:
    """Fast listing: prefer manifest.counts; never line-scan huge jsonl."""
    root = capture_root()
    days: list[dict[str, Any]] = []
    if not root.is_dir():
        return {"root": str(root), "days": [], "tickers_by_day": {}}

    tickers_by_day: dict[str, list[dict[str, Any]]] = {}
    for day_dir in sorted((p for p in root.iterdir() if p.is_dir()), key=lambda p: p.name, reverse=True):
        day = day_dir.name
        tickers: list[dict[str, Any]] = []
        for sym_dir in sorted((p for p in day_dir.iterdir() if p.is_dir()), key=lambda p: p.name):
            manifest_error = None
            try:
                man, _legacy = read_manifest(sym_dir)
            except ValueError as exc:
                man = {}
                manifest_error = str(exc)
                logger.warning("CAPTURE: %s (%s)", manifest_error, sym_dir)
            counts = man.get("counts") if isinstance(man.get("counts"), dict) else {}
            prints_n = _count(counts.get("prints"))
            l2_n = _count(counts.get("l2"))
            # Presence check only (bytes), never read lines.
            has_prints = _file_bytes(sym_dir / "prints.jsonl") > 0
            has_l2 = _file_bytes(sym_dir / "l2.jsonl") > 0
            has_quotes = _file_bytes(sym_dir / "quotes.jsonl") > 0
            has_events = has_prints or has_quotes
            usable = has_events and manifest_error is None
            if prints_n == 0 and has_prints:
                prints_n = -1  # unknown but present
            if l2_n == 0 and has_l2:
                l2_n = -1
            # Skip empty dirs with no capture files
            if not (has_events or has_l2 or man or manifest_error):
                continue
            tickers.append(
                {
                    "symbol": sym_dir.name.upper(),
                    "empty": not has_events,
                    "usable": usable,
                    "unavailable_reason": manifest_error or (None if usable else "No recorded prints or quotes"),
                    "dir": str(sym_dir),
                    "prints": prints_n,
                    "l2": l2_n,
                    "bytes": {
                        "prints": _file_bytes(sym_dir / "prints.jsonl"),
                        "l2": _file_bytes(sym_dir / "l2.jsonl"),
                        "quotes": _file_bytes(sym_dir / "quotes.jsonl"),
                    },
                    "source": man.get("source"),
                    "status": man.get("status"),
                    "partial_ok": man.get("partial_ok", True),
                    **segment_summary(man.get("segments")),
                    "spans": spans_payload(man.get("segments")),
                }
            )
        if tickers:
            days.append({"date": day, "ticker_count": len(tickers)})
            tickers_by_day[day] = tickers

    return {"root": str(root), "days": days, "tickers_by_day": tickers_by_day}


def _count(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (ValueError, TypeError, OverflowError):
        return 0


def segment_summary(segments: Any) -> dict[str, Any]:
    """How whole a recording is: segment count, seconds no segment covers, last reason.

    ``missing_sec`` is the time between the first segment start and the last
    segment stop that no segment covers -- the gaps a restart or a failure left.
    A quiet stretch inside a segment is not missing: the recorder was up and the
    tape said nothing. An open segment (``stopped_et`` null) is counted as
    running to now.
    """
    spans = segment_spans(segments)
    if not spans:
        return {"segments": 0, "missing_sec": 0, "last_reason": None}
    covered = 0.0
    cursor = spans[0][0]
    for start, stop in spans:
        if stop > cursor:
            covered += stop - max(start, cursor)
            cursor = stop
    total = spans[-1][1] - spans[0][0]
    last = segments[-1] if isinstance(segments, list) and segments else {}
    return {
        "segments": len(spans),
        "missing_sec": int(max(0.0, total - covered)),
        "last_reason": last.get("reason") if isinstance(last, dict) else None,
    }


def spans_payload(segments: Any) -> list[list[int]]:
    """``[[start, stop], ...]`` whole epoch seconds per segment for the listing.

    The Sim scrubber draws these under a downloaded replay so the operator sees
    where Nova itself recorded that symbol; an open segment runs to now.
    """
    return [[int(start), int(-(-stop // 1))] for start, stop in segment_spans(segments)]


def segment_spans(segments: Any) -> list[tuple[float, float]]:
    """``[(start_epoch, stop_epoch)]`` per segment, sorted; unparsable rows skipped."""
    out: list[tuple[float, float]] = []
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
        out.append((start, max(start, stop if stop is not None else now)))
    out.sort()
    return out


def _epoch(value: Any) -> float | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value).timestamp()
    except ValueError:
        return None
