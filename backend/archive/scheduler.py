"""
Optional archive maintenance loop (Nova OS P7).

Started from lifespan only when ``ARCHIVE_MAINTENANCE_ENABLED`` is true
(constant default false, overridable via env ``ARCHIVE_MAINTENANCE_ENABLED``).
Compacts finished calendar days (ET) older than today; does not trim hot data.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime
from zoneinfo import ZoneInfo

from archive.capture import session_date_for_ts
from archive.compact import compact_day, list_finished_dates
from constants import ARCHIVE_MAINTENANCE_ENABLED, ARCHIVE_MAINTENANCE_INTERVAL_SEC

logger = logging.getLogger(__name__)

_ET = ZoneInfo("America/New_York")


def maintenance_enabled() -> bool:
    raw = os.environ.get("ARCHIVE_MAINTENANCE_ENABLED")
    if raw is None:
        return bool(ARCHIVE_MAINTENANCE_ENABLED)
    return raw.strip().lower() in ("1", "true", "yes", "on")


def run_maintenance_once(*, today: str | None = None) -> list[str]:
    """Compact all hot session dates strictly before today. Returns dates done."""
    day = today or session_date_for_ts()
    finished = list_finished_dates(day)
    done: list[str] = []
    for d in finished:
        try:
            compact_day(d)
            done.append(d)
        except Exception:
            logger.exception("archive.maintenance: compact failed for %s", d)
    return done


async def archive_maintenance_loop() -> None:
    """Hourly stub — compact finished days when enabled."""
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
