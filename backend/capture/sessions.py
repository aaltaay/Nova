"""List recorded sessions under the capture root (F:\\Nova\\sim_capture)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from capture.recorder import capture_root


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
            man: dict[str, Any] = {}
            man_path = sym_dir / "manifest.json"
            if man_path.is_file():
                try:
                    man = json.loads(man_path.read_text(encoding="utf-8"))
                except Exception:
                    man = {}
            counts = man.get("counts") if isinstance(man.get("counts"), dict) else {}
            prints_n = int(counts.get("prints") or 0)
            l2_n = int(counts.get("l2") or 0)
            # Presence check only (bytes), never read lines.
            has_prints = _file_bytes(sym_dir / "prints.jsonl") > 0
            has_l2 = _file_bytes(sym_dir / "l2.jsonl") > 0
            if prints_n == 0 and has_prints:
                prints_n = -1  # unknown but present
            if l2_n == 0 and has_l2:
                l2_n = -1
            # Skip empty dirs with no capture files
            if not (has_prints or has_l2 or man):
                continue
            tickers.append(
                {
                    "symbol": sym_dir.name.upper(),
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
