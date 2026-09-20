"""List recorded sessions under the capture root (F:\\Nova\\sim_capture)."""
from __future__ import annotations

import logging
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
