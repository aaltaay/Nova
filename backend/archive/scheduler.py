"""
Optional archive maintenance loop (Nova OS P7/P8).

Started from lifespan only when ``ARCHIVE_MAINTENANCE_ENABLED`` is true
(constant default false, overridable via env ``ARCHIVE_MAINTENANCE_ENABLED``).
Does not trim hot data (``ARCHIVE_REQUIRE_VERIFIED_BEFORE_TRIM`` stays
authoritative).

It runs every hour, and does nothing while Nova trades (04:00-20:00 ET on an
exchange day, ``market.in_trading_session``). Its reads, writes and garbage
share the trading process's GIL: until #720 every run re-exported every
finished day, copied 5 GB of databases and re-checked every day with R2, and
the backend stalled for half an hour every 70-80 minutes, open included.
Outside the session a run:

* backs the local SQLite files up once a day (``archive.backup``);
* compacts a finished day's tables only where ``archive.day_state`` finds new
  rows or no manifest, rolling its daily bars up first;
* compacts a finished day's L2 tables once;
* uploads a day to R2 when enabled, after compacting it or while R2 has not
  verified it.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from archive import day_state
from archive.capture import session_date_for_ts
from archive.compact import cold_root, compact_day
from archive.l2_bridge import compact_l2_day, is_l2_day_verified_remote, upload_l2_day
from archive.r2 import is_day_verified_remote, r2_enabled, upload_day
from constants import (
    ARCHIVE_MAINTENANCE_ENABLED,
    ARCHIVE_MAINTENANCE_INTERVAL_SEC,
    ARCHIVE_TABLES_COLD,
    ARCHIVE_TABLES_COLD_L2,
)
from market import in_trading_session

logger = logging.getLogger(__name__)

_ET = ZoneInfo("America/New_York")
_COLD_TABLES = tuple(ARCHIVE_TABLES_COLD)
_BAR_TABLES = frozenset(("bars_1m", "bars_1d"))


def maintenance_enabled() -> bool:
    raw = os.environ.get("ARCHIVE_MAINTENANCE_ENABLED")
    if raw is None:
        return bool(ARCHIVE_MAINTENANCE_ENABLED)
    return raw.strip().lower() in ("1", "true", "yes", "on")


def run_maintenance_once(*, today: str | None = None, now_ts: float | None = None) -> list[str]:
    """One maintenance pass. Returns the finished days whose tables it exported.

    Inside the trading session it does nothing and returns ``[]``.
    """
    now = time.time() if now_ts is None else float(now_ts)
    if in_trading_session(now):
        logger.debug("archive.maintenance: inside the trading session; waiting for 20:00 ET")
        return []
    _backup_once_a_day(now)
    day = today or session_date_for_ts(now)
    root = cold_root()
    hot = day_state.hot_counts(day)  # a failure ends the pass; the loop logs it
    done: list[str] = []
    for d in sorted(hot):
        if _maintain_primary_day(root, d, hot[d]):
            done.append(d)
        # L2 depth/tape backup is best-effort and independent of the primary
        # bars/tape_ibkr day above: a failure here must not block (or be
        # masked by) that day's compact+upload, since the two pipelines have
        # separate manifests and verified indexes.
        _maintain_l2_day(root, d)
    return done


def _backup_once_a_day(now: float) -> None:
    try:
        from archive.backup import backup_complete, backup_sqlite_once

        when = datetime.fromtimestamp(now, tz=_ET)
        if not backup_complete(now=when):
            backup_sqlite_once(now=when)
    except Exception:
        logger.exception("archive.maintenance: sqlite backup failed")


def _maintain_primary_day(root: Path, d: str, hot_day: dict[str, int]) -> bool:
    """Compact what changed in one finished day and upload it. True when it exported."""
    exported = False
    try:
        export, kept = day_state.tables_to_export(hot_day, day_state.cold_counts(root, d, _COLD_TABLES))
        if kept:
            logger.warning(
                "archive.maintenance: %s hot %s hold fewer rows than the cold copy; keeping the cold copy",
                d, ", ".join(kept),
            )
        if export:
            if _BAR_TABLES & set(export) and "bars_1m" not in kept:
                _rollup_daily(d)
                if "bars_1d" not in kept and "bars_1d" not in export:
                    export.append("bars_1d")
            compact_day(d, tables=tuple(t for t in _COLD_TABLES if t in export))
            exported = True
        if r2_enabled() and (exported or not is_day_verified_remote(d)):
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
    return exported


def _rollup_daily(d: str) -> None:
    try:
        from archive.bar_builder import rollup_daily

        rollup_daily(d)
    except Exception:
        logger.exception("archive.maintenance: daily bar rollup failed for %s", d)


def _maintain_l2_day(root: Path, d: str) -> None:
    try:
        compacted = False
        if not day_state.l2_day_compacted(root, d, tuple(ARCHIVE_TABLES_COLD_L2)):
            compact_l2_day(d)
            compacted = True
        if r2_enabled() and (compacted or not is_l2_day_verified_remote(d)):
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


async def archive_maintenance_loop() -> None:
    """Hourly: maintenance outside the trading session, when enabled."""
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
