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
import logging
import os
import re
import tempfile
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

_ET = ZoneInfo("America/New_York")
# Prefer NOVA_CACHE_DIR (Electron desktop), then local backend/.cache/.
from paths import cache_dir as _nova_cache_dir

_CACHE_DIR = str(_nova_cache_dir())

# Legacy fixed filenames — only referenced for the one-time migration.
_LEGACY_FILES = {
    "gappers": os.path.join(_CACHE_DIR, "gappers.json"),
    "movers": os.path.join(_CACHE_DIR, "movers.json"),
    "afterhours": os.path.join(_CACHE_DIR, "afterhours.json"),
}


def _today_et() -> str:
    """04:00 ET-anchored session date for snapshot filenames (ADR 008)."""
    from market import session_key_et
    return session_key_et()


def _is_exchange_date(day: str) -> bool:
    """True when ``day`` (YYYY-MM-DD) is an exchange session, not a weekend or holiday."""
    from datetime import date

    from sim.trading_day import last_open_day
    try:
        parsed = date.fromisoformat(day)
    except ValueError:
        return False
    return last_open_day(parsed) == parsed


def _session_date_et() -> str:
    """The exchange session a scanner snapshot belongs to (#483).

    ``_today_et`` is a calendar date, so a board restored or re-persisted on a
    Saturday was saved as Saturday's and the past-day menu offered "Sat" for
    Friday's board. A weekend or holiday belongs to the last open day before it.
    """
    from datetime import date

    from sim.trading_day import last_open_day
    today = _today_et()
    try:
        return last_open_day(date.fromisoformat(today)).isoformat()
    except ValueError:
        return today


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
        except OSError as unlink_exc:
            logger.debug(
                "cache: temp file cleanup failed for %s: %s",
                tmp_path,
                unlink_exc,
            )
        raise


# ── Migration ─────────────────────────────────────────────────────────────────

from cache_schema import accept_schema, stamp_schema, version_for_prefix
from constants import (  # noqa: F401 -- aliases for cache_snapshots + test patches
    CHART_DRAWINGS_FILE,
    DESK_VENUE_FILE,
    HOD_MOMO_ALERTS_PREFIX,
    HOD_MOMO_BLOCKLIST_FILE,
    HOD_MOMO_CONFIG_FILE,
    HOD_MOMO_HIGHS_PREFIX,
    LARGE_CAP_CONFIG_FILE,
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
            logger.warning(
                "cache: legacy file migration failed for %s (startup continues)",
                old_path, exc_info=True,
            )


# ── Retention cleanup ─────────────────────────────────────────────────────────

def cleanup_old_snapshots(retention_days: int) -> None:
    """Delete dated cache files older than *retention_days* days."""
    if not os.path.isdir(_CACHE_DIR):
        return
    cutoff = (datetime.now(_ET) - timedelta(days=retention_days)).strftime("%Y-%m-%d")
    pattern = re.compile(
        r"^(gappers|gainers|losers|movers|afterhours|large_cap|hod-momo)-(\d{4}-\d{2}-\d{2})\.json$"
    )
    for fname in os.listdir(_CACHE_DIR):
        m = pattern.match(fname)
        if m and m.group(2) < cutoff:
            try:
                os.unlink(os.path.join(_CACHE_DIR, fname))
            except OSError as exc:
                logger.warning(
                    "cache: failed to delete expired snapshot %s: %s",
                    fname,
                    exc,
                )


# ── History helpers ───────────────────────────────────────────────────────────

_HISTORY_ALL_PREFIXES = ("gappers", "gainers", "losers", "movers", "afterhours", "large_cap")


def _dates_with_rows(prefix: str, row_key: str) -> set[str]:
    """Past dates (not today -- today is live) whose ``prefix`` snapshot holds rows.

    Weekend and holiday files written before #483 stay on disk but are not
    offered: the board they hold belongs to the session before them.
    """
    if not os.path.isdir(_CACHE_DIR):
        return set()
    pattern = re.compile(rf"^{re.escape(prefix)}-(\d{{4}}-\d{{2}}-\d{{2}})\.json$")
    today = _today_et()
    dates: set[str] = set()
    for fname in os.listdir(_CACHE_DIR):
        m = pattern.match(fname)
        if not m or m.group(1) == today or not _is_exchange_date(m.group(1)):
            continue
        rows = _read_dated_json(prefix, m.group(1)).get(row_key)
        if isinstance(rows, list) and not rows:
            continue
        dates.add(m.group(1))
    return dates


def list_history_dates(cache_type: str, extra_allowed: set[str] | None = None) -> list[str]:
    """
    Return all dates for which a snapshot of *cache_type* exists on disk,
    sorted descending (newest first). Does not include today — today is live.
    Empty snapshots are omitted so the date picker does not offer a blank day.

    ``movers`` reads the split ``gainers-`` / ``losers-`` files (ADR 008) and the
    legacy combined file; ``all`` is every scanner list, so the board's date
    menu offers a day that saved Gainers but no Gappers.
    """
    _ = extra_allowed  # reserved for future use
    if cache_type == "all":
        found: set[str] = set()
        for prefix in _HISTORY_ALL_PREFIXES:
            found |= set(list_history_dates(prefix))
        return sorted(found, reverse=True)
    if cache_type == "movers":
        found = _dates_with_rows("gainers", "gainers") | _dates_with_rows("losers", "losers")
        found |= _dates_with_rows("movers", "movers")
        return sorted(found, reverse=True)
    row_key = cache_type if cache_type != "hod-momo" else "alerts"
    return sorted(_dates_with_rows(cache_type, row_key), reverse=True)


def _write_dated(prefix: str, date: str, payload: dict) -> None:
    """Stamp ``schema_version`` for *prefix* and atomically write the dated file."""
    _atomic_write(
        _dated_path(prefix, date),
        stamp_schema(payload, version_for_prefix(prefix)),
    )


def _read_dated_json(prefix: str, date: str) -> dict:
    """Load a dated snapshot. Missing version migrates; unknown version is {}."""
    path = _dated_path(prefix, date)
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {}
        accepted = accept_schema(
            data, version_for_prefix(prefix), name=f"{prefix}-{date}",
        )
        return accepted or {}
    except Exception:
        return {}


def load_snapshot_for_date(cache_type: str, date: str) -> dict:
    """
    Load any dated snapshot. Returns the raw JSON dict from the file, or an
    empty dict if the file does not exist or cannot be parsed.

    ``movers`` is composed from independent ``gainers-`` / ``losers-`` files
    (ADR 008 split). The legacy combined ``movers-*.json`` is fallback only.
    """
    if cache_type == "movers":
        gainers = _read_dated_json("gainers", date)
        losers = _read_dated_json("losers", date)
        g_rows = gainers.get("gainers")
        l_rows = losers.get("losers")
        g_rows = g_rows if isinstance(g_rows, list) else []
        l_rows = l_rows if isinstance(l_rows, list) else []
        if g_rows or l_rows:
            ts = max(float(gainers.get("ts") or 0), float(losers.get("ts") or 0))
            return {"date": date, "gainers": g_rows, "losers": l_rows, "ts": ts}
    data = _read_dated_json(cache_type, date)
    return data


# ── Normalisation (backward compat for old on-disk shapes) ───────────────────

def _positive(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0


def _normalize_gapper_row(row: dict) -> dict:
    """Ensure every gapper dict carries both the legacy and current field names.

    The on-disk snapshot may have been written by older code that only stored
    ``previous_close`` / ``current_price``.  The current frontend ScannerRow
    type binds to ``price`` / ``prev_close`` / ``change_pct`` / ``change_abs``.
    This helper bridges the two shapes so restored rows always render correctly.
    """
    price = row.get("price") or row.get("current_price", 0)
    prev_close = row.get("prev_close") or row.get("previous_close", 0)
    if _positive(price) and _positive(prev_close):
        # The change is the price against the prior close. It is NOT the gap:
        # an after-hours row restored here read "-16.71%" over "+$0.44" when
        # its gap was copied into its change (QA C36, 2026-09-22).
        change_abs = price - prev_close
        change_pct = change_abs / prev_close
    else:
        # Nothing to measure from: keep what the row says, never invent a 0.
        change_abs = row.get("change_abs")
        change_pct = row.get("change_pct")
    return {
        **row,
        "price": price,
        "prev_close": prev_close,
        "change_pct": change_pct,
        "change_abs": change_abs,
        "current_price": price,
        "previous_close": prev_close,
    }


from cache_snapshots import (  # noqa: E402, F401
    load_afterhours_snapshot,
    load_chart_drawings,
    load_desk_venue,
    load_gapper_snapshot,
    load_gainer_snapshot,
    load_hod_momo_blocklist,
    load_hod_momo_configs,
    load_hod_momo_highs,
    load_hod_momo_snapshot,
    load_hod_momo_snapshot_for_date,
    load_large_cap_config,
    load_large_cap_fired,
    load_loser_snapshot,
    load_movers_snapshot,
    save_afterhours_snapshot,
    save_chart_drawings,
    save_desk_venue,
    save_gapper_snapshot,
    save_gainer_snapshot,
    save_hod_momo_blocklist,
    save_hod_momo_configs,
    save_hod_momo_highs,
    save_hod_momo_snapshot,
    save_hod_momo_snapshot_for_date,
    save_large_cap_config,
    save_large_cap_fired,
    save_large_cap_snapshot,
    save_loser_snapshot,
    save_movers_snapshot,
)
