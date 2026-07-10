"""
Thin persistence helpers for scanner caches that must survive process restarts.

Each cache type is written to a date-stamped file in backend/.cache/:
  gappers-YYYY-MM-DD.json
  movers-YYYY-MM-DD.json
  afterhours-YYYY-MM-DD.json

Today's file is updated continuously by the scan loop. Past files are kept for
HISTORY_RETENTION_DAYS days so the frontend can browse historical snapshots.

At startup, _migrate_legacy_files() renames any old fixed-name files
(gappers.json, movers.json, afterhours.json) to the dated format so existing
data is not lost.
"""

import json
import os
import re
import tempfile
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

_ET = ZoneInfo("America/New_York")
# Prefer NOVA_CACHE_DIR (Electron desktop), then Railway volume, then local .cache/.
from paths import cache_dir as _nova_cache_dir

_CACHE_DIR = str(_nova_cache_dir())

# Legacy fixed filenames — only referenced for the one-time migration.
_LEGACY_FILES = {
    "gappers": os.path.join(_CACHE_DIR, "gappers.json"),
    "movers": os.path.join(_CACHE_DIR, "movers.json"),
    "afterhours": os.path.join(_CACHE_DIR, "afterhours.json"),
}


def _today_et() -> str:
    return datetime.now(_ET).strftime("%Y-%m-%d")


def _dated_path(prefix: str, date: str) -> str:
    """Return the absolute path for a dated cache file."""
    return os.path.join(_CACHE_DIR, f"{prefix}-{date}.json")


def _atomic_write(path: str, payload: dict) -> None:
    """Write *payload* to *path* atomically via a temp file in the same dir."""
    os.makedirs(_CACHE_DIR, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=_CACHE_DIR, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f)
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


# ── Migration ─────────────────────────────────────────────────────────────────

from constants import (
    HOD_MOMO_ALERTS_PREFIX,
    HOD_MOMO_CONFIG_FILE,
    HOD_MOMO_BLOCKLIST_FILE,
)


def _migrate_legacy_files() -> None:
    """
    One-time rename of old fixed-name files to the dated format.
    Safe to call on every startup — skips any file that doesn't exist or
    whose destination already exists.
    """
    for prefix, old_path in _LEGACY_FILES.items():
        if not os.path.exists(old_path):
            continue
        try:
            with open(old_path, encoding="utf-8") as f:
                data = json.load(f)
            date = data.get("date")
            if not date or not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
                continue
            new_path = _dated_path(prefix, date)
            if os.path.exists(new_path):
                os.unlink(old_path)
            else:
                os.rename(old_path, new_path)
        except Exception:
            pass  # never crash startup over a migration failure


# ── Retention cleanup ─────────────────────────────────────────────────────────

def cleanup_old_snapshots(retention_days: int) -> None:
    """Delete dated cache files older than *retention_days* days."""
    if not os.path.isdir(_CACHE_DIR):
        return
    cutoff = (datetime.now(_ET) - timedelta(days=retention_days)).strftime("%Y-%m-%d")
    pattern = re.compile(r"^(gappers|movers|afterhours|hod-momo)-(\d{4}-\d{2}-\d{2})\.json$")
    for fname in os.listdir(_CACHE_DIR):
        m = pattern.match(fname)
        if m and m.group(2) < cutoff:
            try:
                os.unlink(os.path.join(_CACHE_DIR, fname))
            except OSError:
                pass


# ── History helpers ───────────────────────────────────────────────────────────

def list_history_dates(cache_type: str, extra_allowed: set[str] | None = None) -> list[str]:
    """
    Return all dates for which a snapshot of *cache_type* exists on disk,
    sorted descending (newest first). Does not include today — today is live.
    """
    if not os.path.isdir(_CACHE_DIR):
        return []
    pattern = re.compile(rf"^{re.escape(cache_type)}-(\d{{4}}-\d{{2}}-\d{{2}})\.json$")
    _ = extra_allowed  # reserved for future use
    today = _today_et()
    dates = []
    for fname in os.listdir(_CACHE_DIR):
        m = pattern.match(fname)
        if m:
            d = m.group(1)
            if d != today:
                dates.append(d)
    dates.sort(reverse=True)
    return dates


def load_snapshot_for_date(cache_type: str, date: str) -> dict:
    """
    Load any dated snapshot. Returns the raw JSON dict from the file, or an
    empty dict if the file does not exist or cannot be parsed.
    """
    path = _dated_path(cache_type, date)
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


# ── Normalisation (backward compat for old on-disk shapes) ───────────────────

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


# ── Gappers ───────────────────────────────────────────────────────────────────

def save_gapper_snapshot(gappers: list[dict], ts: float) -> None:
    """Atomically persist the gapper cache to today's dated file."""
    try:
        payload = {"date": _today_et(), "ts": ts, "gappers": gappers}
        _atomic_write(_dated_path("gappers", _today_et()), payload)
    except Exception:
        pass


def load_gapper_snapshot() -> tuple[list[dict], float]:
    """
    Load today's gapper snapshot from disk.

    Returns (gappers, ts) if the file exists and was written today (ET),
    otherwise returns ([], 0.0) so the scan loop starts fresh.
    """
    try:
        path = _dated_path("gappers", _today_et())
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if data.get("date") != _today_et():
            return [], 0.0
        raw = data.get("gappers", [])
        ts = float(data.get("ts", 0.0))
        if not isinstance(raw, list):
            return [], 0.0
        return [_normalize_gapper_row(g) for g in raw], ts
    except Exception:
        return [], 0.0


# ── After-hours ───────────────────────────────────────────────────────────────

def save_afterhours_snapshot(rows: list[dict], ts: float) -> None:
    """Atomically persist the after-hours cache to today's dated file."""
    try:
        payload = {"date": _today_et(), "ts": ts, "afterhours": rows}
        _atomic_write(_dated_path("afterhours", _today_et()), payload)
    except Exception:
        pass


def load_afterhours_snapshot() -> tuple[list[dict], float]:
    """
    Load today's after-hours snapshot from disk.

    Returns (rows, ts) if the file exists and was written today (ET),
    otherwise returns ([], 0.0) so the scan loop starts fresh.
    """
    try:
        path = _dated_path("afterhours", _today_et())
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if data.get("date") != _today_et():
            return [], 0.0
        raw = data.get("afterhours", [])
        ts = float(data.get("ts", 0.0))
        if not isinstance(raw, list):
            return [], 0.0
        return [_normalize_gapper_row(g) for g in raw], ts
    except Exception:
        return [], 0.0


# ── Movers (gainers + losers) ─────────────────────────────────────────────────

def save_movers_snapshot(gainers: list[dict], losers: list[dict], ts: float) -> None:
    """Atomically persist the movers (gainers + losers) cache to today's dated file."""
    try:
        payload = {"date": _today_et(), "ts": ts, "gainers": gainers, "losers": losers}
        _atomic_write(_dated_path("movers", _today_et()), payload)
    except Exception:
        pass


def load_movers_snapshot() -> tuple[list[dict], list[dict], float]:
    """
    Load today's movers snapshot from disk.

    Returns (gainers, losers, ts) if the file exists and was written today (ET),
    otherwise returns ([], [], 0.0) so the scan loop starts fresh.
    """
    try:
        path = _dated_path("movers", _today_et())
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if data.get("date") != _today_et():
            return [], [], 0.0
        gainers = data.get("gainers", [])
        losers = data.get("losers", [])
        ts = float(data.get("ts", 0.0))
        if not isinstance(gainers, list) or not isinstance(losers, list):
            return [], [], 0.0
        return gainers, losers, ts
    except Exception:
        return [], [], 0.0


# ── HOD Momo — alert snapshots ────────────────────────────────────────────────

def save_hod_momo_snapshot(alerts: list[dict], ts: float) -> None:
    """Atomically persist today's HOD Momo alert list."""
    try:
        payload = {"date": _today_et(), "ts": ts, "alerts": alerts}
        _atomic_write(_dated_path(HOD_MOMO_ALERTS_PREFIX, _today_et()), payload)
    except Exception:
        pass


def load_hod_momo_snapshot() -> tuple[list[dict], float]:
    """Load today's HOD Momo alerts from disk.

    Returns (alerts, ts) or ([], 0.0) if not found / stale.
    """
    try:
        path = _dated_path(HOD_MOMO_ALERTS_PREFIX, _today_et())
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if data.get("date") != _today_et():
            return [], 0.0
        raw = data.get("alerts", [])
        ts = float(data.get("ts", 0.0))
        if not isinstance(raw, list):
            return [], 0.0
        return raw, ts
    except Exception:
        return [], 0.0


def load_hod_momo_snapshot_for_date(date_str: str) -> dict:
    """Load HOD Momo alerts for an arbitrary past date (YYYY-MM-DD)."""
    try:
        path = _dated_path(HOD_MOMO_ALERTS_PREFIX, date_str)
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


# ── HOD Momo — configs ────────────────────────────────────────────────────────

def save_hod_momo_configs(payload: dict) -> None:
    """Persist strategy configs + master gate to the fixed config file."""
    try:
        os.makedirs(_CACHE_DIR, exist_ok=True)
        _atomic_write(HOD_MOMO_CONFIG_FILE, payload)
    except Exception:
        pass


def load_hod_momo_configs() -> dict:
    """Load strategy configs + master gate. Returns {} if file doesn't exist."""
    try:
        with open(HOD_MOMO_CONFIG_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


# ── HOD Momo — blocklist ─────────────────────────────────────────────────────

def save_hod_momo_blocklist(symbols: list[str]) -> None:
    """Persist the HOD Momo global blocklist."""
    try:
        os.makedirs(_CACHE_DIR, exist_ok=True)
        _atomic_write(HOD_MOMO_BLOCKLIST_FILE, {"symbols": symbols})
    except Exception:
        pass


def load_hod_momo_blocklist() -> list[str]:
    """Load the HOD Momo global blocklist. Returns [] if not found."""
    try:
        with open(HOD_MOMO_BLOCKLIST_FILE, encoding="utf-8") as f:
            data = json.load(f)
        raw = data.get("symbols", [])
        if not isinstance(raw, list):
            return []
        return [str(s) for s in raw]
    except Exception:
        return []
