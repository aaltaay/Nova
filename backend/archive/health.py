"""
Archive health snapshot (Nova OS P8).

Reports last verified remote day, lag vs local cold days, capture gaps,
bytes/object estimates, and fail-loud status when R2 is enabled/configured
but uploads are failing.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from archive.compact import cold_root
from archive import db as archive_db
from archive.l2_bridge import load_l2_verified_index
from archive.r2 import is_day_verified_remote, load_verified_index, r2_enabled, r2_status
from constants import (
    ARCHIVE_REQUIRE_VERIFIED_BEFORE_TRIM,
    ARCHIVE_SCHEMA_VERSION,
    ARCHIVE_TABLES_COLD,
    ARCHIVE_TABLES_COLD_L2,
)

logger = logging.getLogger(__name__)

_ET = ZoneInfo("America/New_York")


def list_local_cold_days(
    *,
    cold_dir: Path | None = None,
    schema_version: str = ARCHIVE_SCHEMA_VERSION,
) -> list[str]:
    """YYYY-MM-DD dirs under cold root that contain the active schema folder."""
    root = cold_dir or cold_root()
    if not root.is_dir():
        return []
    days: list[str] = []
    for child in sorted(root.iterdir()):
        if not child.is_dir() or child.name.startswith("_"):
            continue
        if (child / schema_version).is_dir():
            days.append(child.name)
    return days


def _estimate_day_bytes(day_dir: Path) -> tuple[int, int]:
    """Return (bytes, file_count) for payloads + manifests under a day schema dir."""
    total = 0
    count = 0
    if not day_dir.is_dir():
        return 0, 0
    for path in day_dir.rglob("*"):
        if path.is_file():
            total += path.stat().st_size
            count += 1
    return total, count


def _gap_count_for_dates(dates: list[str]) -> int:
    if not dates:
        return 0
    conn = archive_db.get_connection()
    try:
        placeholders = ",".join("?" for _ in dates)
        cur = conn.execute(
            f"SELECT COUNT(*) FROM capture_gaps WHERE session_date IN ({placeholders})",
            tuple(dates),
        )
        return int(cur.fetchone()[0])
    except Exception:
        logger.exception("archive.health: gap count failed")
        return 0
    finally:
        conn.close()


def _calendar_gaps(local_days: list[str]) -> list[str]:
    """Missing weekdays between min and max local cold days (simple lag gaps)."""
    if len(local_days) < 2:
        return []
    start = datetime.fromisoformat(local_days[0]).date()
    end = datetime.fromisoformat(local_days[-1]).date()
    have = set(local_days)
    missing: list[str] = []
    d = start
    while d <= end:
        iso = d.isoformat()
        if d.weekday() < 5 and iso not in have:
            missing.append(iso)
        d += timedelta(days=1)
    return missing


def archive_health(*, cold_dir: Path | None = None) -> dict[str, Any]:
    """
    Full health payload for GET /api/archive/health.

    ``ok`` is False when R2 is enabled and configured but the latest upload
    attempt failed, or when enabled but not configured (keys missing).
    """
    root = cold_dir or cold_root()
    local_days = list_local_cold_days(cold_dir=root)
    index = load_verified_index(root)
    verified_days = sorted(
        d for d, meta in (index.get("days") or {}).items()
        if isinstance(meta, dict) and meta.get("ok")
    )
    last_verified = verified_days[-1] if verified_days else None
    today = datetime.now(tz=_ET).date().isoformat()

    lag_days: int | None = None
    if last_verified:
        try:
            lag_days = (datetime.fromisoformat(today).date() - datetime.fromisoformat(last_verified).date()).days
        except ValueError:
            lag_days = None
    elif local_days:
        try:
            lag_days = (datetime.fromisoformat(today).date() - datetime.fromisoformat(local_days[-1]).date()).days
        except ValueError:
            lag_days = None

    bytes_est = 0
    object_count = 0
    for day in local_days:
        b, n = _estimate_day_bytes(root / day / ARCHIVE_SCHEMA_VERSION)
        bytes_est += b
        object_count += n

    unverified_local = [d for d in local_days if not is_day_verified_remote(d, root)]
    calendar_gaps = _calendar_gaps(local_days)
    capture_gaps = _gap_count_for_dates(local_days)

    r2 = r2_status()
    enabled = r2_enabled()
    failed_days = [
        d for d, meta in (index.get("days") or {}).items()
        if isinstance(meta, dict) and meta.get("ok") is False
    ]

    l2_index = load_l2_verified_index(root)
    l2_verified_days = sorted(
        d for d, meta in (l2_index.get("days") or {}).items()
        if isinstance(meta, dict) and meta.get("ok")
    )
    l2_failed_days = [
        d for d, meta in (l2_index.get("days") or {}).items()
        if isinstance(meta, dict) and meta.get("ok") is False
    ]

    problems: list[str] = []
    if enabled and not r2["configured"]:
        problems.append(r2["message"])
    if enabled and r2["configured"] and failed_days:
        problems.append(f"R2 upload failed for days: {', '.join(sorted(failed_days))}")
    if enabled and r2["configured"] and l2_failed_days:
        problems.append(
            f"L2 bridge R2 upload failed for days: {', '.join(sorted(l2_failed_days))}"
        )
    if enabled and r2["configured"] and local_days and not verified_days:
        problems.append("R2 configured but no day has been verified remote yet")

    ok = len(problems) == 0
    # When R2 is off, local-only health is still ok (P8 code-complete without keys).
    if not enabled:
        ok = True

    return {
        "ok": ok,
        "problems": problems,
        "schema_version": ARCHIVE_SCHEMA_VERSION,
        "today_et": today,
        "local_cold_days": local_days,
        "last_verified_day": last_verified,
        "verified_days": verified_days,
        "unverified_local_days": unverified_local,
        "lag_days": lag_days,
        "calendar_gaps": calendar_gaps,
        "capture_gap_rows": capture_gaps,
        "bytes_estimate": bytes_est,
        "object_count": object_count,
        "require_verified_before_trim": ARCHIVE_REQUIRE_VERIFIED_BEFORE_TRIM,
        "trim_blocked": bool(ARCHIVE_REQUIRE_VERIFIED_BEFORE_TRIM),
        "tables": list(ARCHIVE_TABLES_COLD),
        "l2_bridge_tables": list(ARCHIVE_TABLES_COLD_L2),
        "l2_bridge_verified_days": l2_verified_days,
        "l2_bridge_failed_days": l2_failed_days,
        "r2": r2,
        "note": (
            "Put R2_ACCOUNT_ID / R2_ACCESS_KEY_ID / R2_SECRET_ACCESS_KEY in .env only. "
            "Hot trim stays blocked while ARCHIVE_REQUIRE_VERIFIED_BEFORE_TRIM is True."
        ),
    }
