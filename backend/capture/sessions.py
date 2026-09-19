"""List recorded sessions under the capture root (F:\\Nova\\sim_capture)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from capture.recorder import capture_root


def _line_count(path: Path, limit: int = 50_000) -> int:
    if not path.is_file():
        return 0
    n = 0
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as fh:
            for n, _ in enumerate(fh, 1):
                if n >= limit:
                    return n
    except OSError:
        return 0
    return n


def list_sessions() -> dict[str, Any]:
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
            prints = _line_count(sym_dir / "prints.jsonl")
            l2 = _line_count(sym_dir / "l2.jsonl")
            tickers.append(
                {
                    "symbol": sym_dir.name.upper(),
                    "dir": str(sym_dir),
                    "prints": prints,
                    "l2": l2,
                    "source": man.get("source"),
                    "status": man.get("status"),
                    "partial_ok": man.get("partial_ok", True),
                }
            )
        if tickers:
            days.append({"date": day, "ticker_count": len(tickers)})
            tickers_by_day[day] = tickers

    return {"root": str(root), "days": days, "tickers_by_day": tickers_by_day}
