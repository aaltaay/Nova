"""
Thin persistence helpers for scanner caches that must survive process restarts.

Only the gapper snapshot needs persistence: it is frozen at 9:30 AM ET and
never re-populated during market hours, so a restart would wipe it permanently
until the next pre-market session.

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
        gappers = data.get("gappers", [])
        ts = float(data.get("ts", 0.0))
        if not isinstance(gappers, list):
            return [], 0.0
        return gappers, ts
    except Exception:
        return [], 0.0
