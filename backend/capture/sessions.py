"""List recorded sessions under the capture root (F:\\Nova\\sim_capture).

A row is a replayable Session Record only when it holds events, its manifest
reads, and it is IBKR-sourced: the removed synthetic SIM1 instrument's old
``source: "sim"`` directories are listed unusable with a reason, never offered
(ADR 019; QA 2026-09-22, C21). A directory this process is recording right now
reads its live counts and its open segment, so Records never shows "-1 prints,
0 segments" for a running recording (C22).
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from capture.constants_capture import CAPTURE_NOT_IBKR_REASON, CAPTURE_SOURCE_IBKR
from capture.recorder import capture_root
from capture.schema import read_manifest
from capture.segments import (  # noqa: F401 -- segment_spans / spans_payload / segment_summary are this module's API
    finished_segments, segment_spans, segment_summary, spans_payload, with_open_segment,
)

logger = logging.getLogger(__name__)


def _file_bytes(path: Path) -> int:
    try:
        return path.stat().st_size if path.is_file() else 0
    except OSError:
        return 0


def _live_sessions() -> dict[str, dict[str, Any]]:
    """This process's active recordings keyed by directory (the recorder's lock-free status)."""
    try:
        from capture.recorder import status as recorder_status

        sessions = recorder_status().get("sessions") or {}
    except Exception:
        logger.warning("CAPTURE: recorder status unavailable; listing without live counts", exc_info=True)
        return {}
    return {
        str(row["dir"]): row
        for row in sessions.values()
        if isinstance(row, dict) and row.get("recording") and row.get("dir")
    }


def is_ibkr_source(manifest: dict[str, Any]) -> bool:
    """IBKR-sourced, or stamped before manifests carried a source."""
    source = manifest.get("source") if isinstance(manifest, dict) else None
    return source is None or source == CAPTURE_SOURCE_IBKR


def list_sessions() -> dict[str, Any]:
    """Fast listing: prefer manifest.counts; never line-scan huge jsonl."""
    root = capture_root()
    days: list[dict[str, Any]] = []
    if not root.is_dir():
        return {"root": str(root), "days": [], "tickers_by_day": {}}

    live_by_dir = _live_sessions()
    tickers_by_day: dict[str, list[dict[str, Any]]] = {}
    for day_dir in sorted((p for p in root.iterdir() if p.is_dir()), key=lambda p: p.name, reverse=True):
        day = day_dir.name
        tickers: list[dict[str, Any]] = []
        for sym_dir in sorted((p for p in day_dir.iterdir() if p.is_dir()), key=lambda p: p.name):
            row = _row(sym_dir, live_by_dir.get(str(sym_dir)))
            if row is not None:
                tickers.append(row)
        if tickers:
            days.append({"date": day, "ticker_count": len(tickers)})
            tickers_by_day[day] = tickers

    return {"root": str(root), "days": days, "tickers_by_day": tickers_by_day}


def _row(sym_dir: Path, live: dict[str, Any] | None) -> dict[str, Any] | None:
    manifest_error = None
    try:
        man, _legacy = read_manifest(sym_dir)
    except ValueError as exc:
        man = {}
        manifest_error = str(exc)
        logger.warning("CAPTURE: %s (%s)", manifest_error, sym_dir)
    counts = man.get("counts") if isinstance(man.get("counts"), dict) else {}
    # The recorder's cumulative counts are the truth while it writes this directory;
    # the manifest only catches up when a segment ends.
    live_counts = live.get("counts") if live and isinstance(live.get("counts"), dict) else None
    prints_n = _count((live_counts or counts).get("prints"))
    l2_n = _count((live_counts or counts).get("l2"))
    # Presence check only (bytes), never read lines.
    has_prints = _file_bytes(sym_dir / "prints.jsonl") > 0
    has_l2 = _file_bytes(sym_dir / "l2.jsonl") > 0
    has_quotes = _file_bytes(sym_dir / "quotes.jsonl") > 0
    has_events = has_prints or has_quotes
    synthetic = manifest_error is None and not is_ibkr_source(man)
    usable = has_events and manifest_error is None and not synthetic
    if prints_n == 0 and has_prints:
        prints_n = -1  # rows on disk, not counted yet
    if l2_n == 0 and has_l2:
        l2_n = -1
    # Skip empty dirs with no capture files
    if not (has_events or has_l2 or man or manifest_error):
        return None
    segments = with_open_segment(man, sym_dir, live=live is not None)
    reason = manifest_error or (CAPTURE_NOT_IBKR_REASON if synthetic else None)
    return {
        "symbol": sym_dir.name.upper(),
        "empty": not has_events,
        "usable": usable,
        "unavailable_reason": reason or (None if usable else "No recorded prints or quotes"),
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
        **segment_summary(segments, finished=finished_segments(man)),
        "spans": spans_payload(segments),
    }


def _count(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (ValueError, TypeError, OverflowError):
        return 0
