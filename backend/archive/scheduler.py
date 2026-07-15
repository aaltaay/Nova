"""
Optional archive maintenance loop (Nova OS P7/P8).

Started from lifespan only when ``ARCHIVE_MAINTENANCE_ENABLED`` is true
(constant default false, overridable via env ``ARCHIVE_MAINTENANCE_ENABLED``).
Compacts finished calendar days (ET) older than today; optionally uploads to
R2 when ``ARCHIVE_R2_ENABLED`` is true. Does not trim hot data
(``ARCHIVE_REQUIRE_VERIFIED_BEFORE_TRIM`` stays authoritative).
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime
from zoneinfo import ZoneInfo

from archive.capture import session_date_for_ts
from archive.compact import compact_day, list_finished_dates
from archive.l2_bridge import compact_l2_day, upload_l2_day
from archive.r2 import r2_enabled, upload_day
from constants import ARCHIVE_MAINTENANCE_ENABLED, ARCHIVE_MAINTENANCE_INTERVAL_SEC

logger = logging.getLogger(__name__)

_ET = ZoneInfo("America/New_York")


def maintenance_enabled() -> bool:
    raw = os.environ.get("ARCHIVE_MAINTENANCE_ENABLED")
    if raw is None:
        return bool(ARCHIVE_MAINTENANCE_ENABLED)
    return raw.strip().lower() in ("1", "true", "yes", "on")


def run_maintenance_once(*, today: str | None = None) -> list[str]:
    """Compact finished days; upload to R2 when enabled. Returns dates compacted."""
    day = today or session_date_for_ts()
    finished = list_finished_dates(day)
    done: list[str] = []
    for d in finished:
        try:
            compact_day(d)
            done.append(d)
            if r2_enabled():
                result = upload_day(d)
                if not result.get("ok"):
                    logger.error(
                        "archive.maintenance: R2 upload failed for %s: %s",
                        d,
                        result.get("error") or result.get("uploads"),
                    )
                else:
                    logger.info("archive.maintenance: R2 verified %s", d)
        except Exception:
            logger.exception("archive.maintenance: compact failed for %s", d)

        # L2 depth/tape backup is best-effort and independent of the primary
        # bars/tape_ibkr day above: a failure here must not block (or be
        # masked by) that day's compact+upload, since the two pipelines have
        # separate manifests and verified indexes.
        try:
            compact_l2_day(d)
            if r2_enabled():
                l2_result = upload_l2_day(d)
                if not l2_result.get("ok"):
                    logger.error(
                        "archive.maintenance: L2 R2 upload failed for %s: %s",
                        d,
                        l2_result.get("error") or l2_result.get("uploads"),
                    )
                else:
                    logger.info("archive.maintenance: L2 R2 verified %s", d)
        except Exception:
            logger.exception("archive.maintenance: L2 compact/upload failed for %s", d)
    return done


async def archive_maintenance_loop() -> None:
    """Hourly stub — compact (+ optional R2) when enabled."""
    interval = float(ARCHIVE_MAINTENANCE_INTERVAL_SEC)
    logger.info(
        "archive.maintenance: loop started (interval=%.0fs ET now=%s)",
        interval,
        datetime.now(tz=_ET).isoformat(),
    )
    while True:
        try:
            await asyncio.sleep(interval)
            if not maintenance_enabled():
                continue
            done = await asyncio.to_thread(run_maintenance_once)
            if done:
                logger.info("archive.maintenance: compacted %s", done)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("archive.maintenance: sweep failed")
