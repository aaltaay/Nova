"""Session recorder — jsonl under archive/sim_capture/<date>/<symbol>/."""
from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, TextIO
from zoneinfo import ZoneInfo

from capture.constants_capture import CAPTURE_L2_MAX_HZ
from paths import cache_dir

logger = logging.getLogger(__name__)
ET = ZoneInfo("America/New_York")

_lock = threading.Lock()
_active = False
_symbol: str | None = None
_day: str | None = None
_dir: Path | None = None
_files: dict[str, TextIO] = {}
_last_l2_mono = 0.0
_counts = {"prints": 0, "quotes": 0, "l2": 0, "bars_1m": 0, "bars_10s": 0}


def reset_for_tests() -> None:
    stop_recorder()


def is_recording() -> bool:
    return _active


def capture_root() -> Path:
    return cache_dir() / "sim_capture"


def _session_dir(symbol: str) -> Path:
    day = datetime.now(ET).strftime("%Y-%m-%d")
    return capture_root() / day / symbol.upper()


def start_recorder(symbol: str | None) -> dict[str, Any]:
    global _active, _symbol, _day, _dir, _last_l2_mono, _counts
    with _lock:
        stop_recorder_unlocked()
        sym = (symbol or "PENDING").strip().upper()
        _symbol = sym
        _dir = _session_dir(sym)
        _dir.mkdir(parents=True, exist_ok=True)
        _day = _dir.parent.name
        _counts = {k: 0 for k in _counts}
        _last_l2_mono = 0.0
        for name in ("prints", "quotes", "l2", "bars_1m", "bars_10s"):
            path = _dir / f"{name}.jsonl"
            _files[name] = path.open("a", encoding="utf-8")
        manifest = {
            "symbol": sym,
            "session_date": _day,
            "started_et": datetime.now(ET).isoformat(),
            "source": "ibkr",
            "schema": "sim_capture_v1",
            "l2_max_hz": CAPTURE_L2_MAX_HZ,
            "note": "Capture mode — places blocked; compact to parquet after session",
        }
        (_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        _active = True
        logger.info("CAPTURE: recorder started %s", _dir)
        return {"ok": True, "dir": str(_dir), "manifest": manifest}


def stop_recorder() -> None:
    with _lock:
        stop_recorder_unlocked()


def stop_recorder_unlocked() -> None:
    global _active
    if not _active and not _files:
        return
    for fh in list(_files.values()):
        try:
            fh.flush()
            fh.close()
        except Exception:
            logger.exception("CAPTURE: close failed")
    _files.clear()
    if _dir is not None and _active:
        try:
            man_path = _dir / "manifest.json"
            man = json.loads(man_path.read_text(encoding="utf-8")) if man_path.exists() else {}
            man["stopped_et"] = datetime.now(ET).isoformat()
            man["counts"] = dict(_counts)
            man_path.write_text(json.dumps(man, indent=2), encoding="utf-8")
        except Exception:
            logger.exception("CAPTURE: manifest finalize failed")
    _active = False
    logger.info("CAPTURE: recorder stopped counts=%s", _counts)


def _write(kind: str, row: dict[str, Any]) -> None:
    fh = _files.get(kind)
    if fh is None:
        return
    fh.write(json.dumps(row, separators=(",", ":")) + "\n")
    fh.flush()
    _counts[kind] = _counts.get(kind, 0) + 1


def record_print(payload: dict[str, Any]) -> None:
    if not _active:
        return
    with _lock:
        if not _active:
            return
        _write("prints", payload)


def record_quote(payload: dict[str, Any]) -> None:
    if not _active:
        return
    with _lock:
        if not _active:
            return
        _write("quotes", payload)


def record_l2(payload: dict[str, Any]) -> None:
    """Sampled L2 — drop updates faster than CAPTURE_L2_MAX_HZ."""
    global _last_l2_mono
    if not _active:
        return
    now = time.monotonic()
    min_dt = 1.0 / max(1.0, CAPTURE_L2_MAX_HZ)
    with _lock:
        if not _active:
            return
        if now - _last_l2_mono < min_dt:
            return
        _last_l2_mono = now
        _write("l2", payload)


def record_bar(timeframe: str, payload: dict[str, Any]) -> None:
    if not _active:
        return
    kind = "bars_1m" if timeframe in ("1Min", "1min", "1m") else "bars_10s"
    with _lock:
        if not _active:
            return
        _write(kind, payload)


def status() -> dict[str, Any]:
    return {
        "recording": _active,
        "symbol": _symbol,
        "session_date": _day,
        "dir": str(_dir) if _dir else None,
        "counts": dict(_counts),
    }
