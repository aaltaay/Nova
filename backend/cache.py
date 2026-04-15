"""
Thin persistence helpers for scanner caches that must survive process restarts.

Gapper and after-hours snapshots need persistence because they are frozen once
their active window ends and never re-populated until the next matching session:
- Gappers: frozen at 9:30 AM ET until next pre-market.
- After-hours: frozen at 8:00 PM ET until the next after-hours session.

All other caches (gainers, losers, news catalysts) are continuously refreshed
during their active windows and do not need persistence.
"""

import json
import os
import tempfile
from datetime import datetime
from zoneinfo import ZoneInfo

_ET = ZoneInfo("America/New_York")
_CACHE_DIR = os.path.join(os.path.dirname(__file__), ".cache")
_GAPPER_FILE = os.path.join(_CACHE_DIR, "gappers.json")
_AFTERHOURS_FILE = os.path.join(_CACHE_DIR, "afterhours.json")


def _today_et() -> str:
    return datetime.now(_ET).strftime("%Y-%m-%d")


def save_gapper_snapshot(gappers: list[dict], ts: float) -> None:
    """Atomically persist the gapper cache to disk."""
    try:
        os.makedirs(_CACHE_DIR, exist_ok=True)
        payload = {"date": _today_et(), "ts": ts, "gappers": gappers}
        fd, tmp_path = tempfile.mkstemp(dir=_CACHE_DIR, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f)
            os.replace(tmp_path, _GAPPER_FILE)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
    except Exception:
        pass  # never crash the caller over a persistence failure


def _normalize_gapper_row(row: dict) -> dict:
    """Ensure every gapper dict carries both the legacy and current field names.

    The on-disk snapshot may have been written by older code that only stored
    ``previous_close`` / ``current_price``.  The current frontend ScannerRow
    type binds to ``price`` / ``prev_close`` / ``change_pct`` / ``change_abs``.
    This helper bridges the two shapes so restored rows always render correctly.
    """
    price = row.get("price") or row.get("current_price", 0)
    prev_close = row.get("prev_close") or row.get("previous_close", 0)
    gap_pct = row.get("gap_percent", 0)
    change_abs = (price - prev_close) if (price and prev_close) else 0
    change_pct = gap_pct  # for gappers change == gap
    return {
        **row,
        "price": price,
        "prev_close": prev_close,
        "change_pct": change_pct,
        "change_abs": change_abs,
        "current_price": price,
        "previous_close": prev_close,
    }


def load_gapper_snapshot() -> tuple[list[dict], float]:
    """
    Load today's gapper snapshot from disk.

    Returns (gappers, ts) if the file exists and was written today (ET),
    otherwise returns ([], 0.0) so the scan loop starts fresh.
    """
    try:
        with open(_GAPPER_FILE, encoding="utf-8") as f:
            data = json.load(f)
        if data.get("date") != _today_et():
            return [], 0.0
        raw = data.get("gappers", [])
        ts = float(data.get("ts", 0.0))
        if not isinstance(raw, list):
            return [], 0.0
        gappers = [_normalize_gapper_row(g) for g in raw]
        return gappers, ts
    except Exception:
        return [], 0.0


def save_afterhours_snapshot(rows: list[dict], ts: float) -> None:
    """Atomically persist the after-hours cache to disk."""
    try:
        os.makedirs(_CACHE_DIR, exist_ok=True)
        payload = {"date": _today_et(), "ts": ts, "afterhours": rows}
        fd, tmp_path = tempfile.mkstemp(dir=_CACHE_DIR, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f)
            os.replace(tmp_path, _AFTERHOURS_FILE)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
    except Exception:
        pass  # never crash the caller over a persistence failure


def load_afterhours_snapshot() -> tuple[list[dict], float]:
    """
    Load today's after-hours snapshot from disk.

    Returns (rows, ts) if the file exists and was written today (ET),
    otherwise returns ([], 0.0) so the scan loop starts fresh.
    """
    try:
        with open(_AFTERHOURS_FILE, encoding="utf-8") as f:
            data = json.load(f)
        if data.get("date") != _today_et():
            return [], 0.0
        raw = data.get("afterhours", [])
        ts = float(data.get("ts", 0.0))
        if not isinstance(raw, list):
            return [], 0.0
        rows = [_normalize_gapper_row(g) for g in raw]
        return rows, ts
    except Exception:
        return [], 0.0
