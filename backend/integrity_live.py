"""Live integrity report builders + background fail-loud logger."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from constants import HOD_MOMO_INTEGRITY_POLL_SEC
from hod_momo_integrity import (
    evaluate_hod_integrity,
    evaluate_scanner_integrity,
    merge_integrity,
)

logger = logging.getLogger(__name__)


def _cache_age(ts: float | None) -> float | None:
    if not ts:
        return None
    return max(0.0, time.time() - float(ts))


def build_hod_integrity_report() -> dict[str, Any]:
    import hod_momo as hm
    import hod_momo_active as active
    import hod_momo_universe as uni
    import main as m
    from alpaca import _get_discovery_provider
    from ibkr import client as ibkr_client

    flow = hm.get_flow_stats()
    provider = (_get_discovery_provider() or "").strip().lower()
    active_metrics = active.metrics_snapshot()
    snap = {
        **flow,
        **active_metrics,
        "universe_size": len(getattr(m, "_hod_momo_universe", set()) or set()),
        "watch_seed_size": len(uni.get_seed_symbols()),
        "discovery_provider": provider,
        "ibkr_connected": ibkr_client.is_connected() if provider == "ibkr" else None,
    }
    report = evaluate_hod_integrity(snap)
    report["checked_at"] = time.time()
    report["metrics"] = snap
    return report


def build_scanner_integrity_report() -> dict[str, Any]:
    import main as m
    from alpaca import _get_discovery_provider
    from ibkr import client as ibkr_client
    from ibkr import reprice as ibkr_reprice

    provider = (_get_discovery_provider() or "").strip().lower()
    table_age = None
    last_ok = getattr(ibkr_reprice, "_table_last_ok_ts", None)
    if last_ok:
        table_age = _cache_age(last_ok)

    snap = {
        "discovery_provider": provider,
        "ibkr_connected": ibkr_client.is_connected() if provider == "ibkr" else None,
        "gapper_count": len(getattr(m, "_gapper_cache", None) or []),
        "gainer_count": len(getattr(m, "_gainer_cache", None) or []),
        "loser_count": len(getattr(m, "_loser_cache", None) or []),
        "gapper_age_sec": _cache_age(getattr(m, "_gapper_cache_ts", 0.0) or None),
        "gainer_age_sec": _cache_age(getattr(m, "_gainer_cache_ts", 0.0) or None),
        "loser_age_sec": _cache_age(getattr(m, "_loser_cache_ts", 0.0) or None),
        "table_reprice_age_sec": table_age,
        "table_busy_skips": getattr(ibkr_reprice, "_table_busy_skips", 0),
        "table_timeouts": getattr(ibkr_reprice, "_table_timeouts", 0),
    }
    report = evaluate_scanner_integrity(snap)
    report["checked_at"] = time.time()
    report["metrics"] = snap
    return report


def build_all_integrity_report() -> dict[str, Any]:
    hod = build_hod_integrity_report()
    scan = build_scanner_integrity_report()
    merged = merge_integrity(hod, scan)
    merged["checked_at"] = time.time()
    merged["hod"] = hod
    merged["scanner"] = scan
    return merged


def _log_report(report: dict[str, Any]) -> None:
    status = report.get("status") or "pass"
    if status == "pass":
        logger.debug(
            "Integrity %s: pass (%d checks)",
            report.get("scope"),
            len(report.get("checks") or []),
        )
        return
    failed = [c for c in (report.get("checks") or []) if c.get("status") in ("fail", "warn")]
    summary = "; ".join(f"{c['id']}={c['status']}:{c['detail']}" for c in failed[:6])
    if status == "fail":
        logger.warning("INTEGRITY FAIL [%s]: %s", report.get("scope"), summary)
    else:
        logger.warning("INTEGRITY WARN [%s]: %s", report.get("scope"), summary)


async def integrity_loop() -> None:
    """Background task: periodically evaluate and log fail/warn loudly."""
    while True:
        try:
            await asyncio.sleep(HOD_MOMO_INTEGRITY_POLL_SEC)
            report = build_all_integrity_report()
            _log_report(report)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Integrity loop error: %s", exc)
