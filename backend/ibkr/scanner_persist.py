"""Write ADR 008 live roster rows to dated JSON (same files as scan_loop)."""
from __future__ import annotations

import logging

from ibkr import scanner_session as _session

logger = logging.getLogger(__name__)


def persist_roster(table: str, rows: list[dict], ts: float) -> None:
    """Best-effort snapshot. Failures stay on disk logs, never raise."""
    try:
        import cache as _cache

        if table == _session.TABLE_GAPPERS:
            _cache.save_gapper_snapshot(rows, ts)
        elif table == _session.TABLE_GAINERS:
            _cache.save_gainer_snapshot(rows, ts)
        elif table == _session.TABLE_LOSERS:
            _cache.save_loser_snapshot(rows, ts)
        elif table == _session.TABLE_AFTERHOURS:
            _cache.save_afterhours_snapshot(rows, ts)
        elif table == _session.TABLE_LARGE_CAP:
            _cache.save_large_cap_snapshot(rows, ts)
    except Exception:
        logger.warning(
            "scanner_persist: failed to write %s snapshot", table, exc_info=True
        )
