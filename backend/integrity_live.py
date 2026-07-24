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
from runtime_state import get_runtime_state

logger = logging.getLogger(__name__)

# Cached for alert suppress / session gate (updated by integrity_loop).
_last_merged_status: str = "pass"
_last_report: dict[str, Any] | None = None
_last_report_ts: float = 0.0
# Serve cached /api/integrity when fresh — avoids stacking slow sync builds
# while the event loop is under IBKR L1 pressure (CLOSE_WAIT storm).
_INTEGRITY_HTTP_CACHE_SEC = 2.0


def get_last_integrity_status() -> str:
    return _last_merged_status


def get_cached_integrity_report(*, max_age_sec: float = _INTEGRITY_HTTP_CACHE_SEC) -> dict[str, Any] | None:
    if _last_report is None:
        return None
    if (time.time() - float(_last_report_ts)) > float(max_age_sec):
        return None
    return _last_report


def integrity_is_failing() -> bool:
    return _last_merged_status == "fail"


def hod_integrity_is_failing() -> bool:
    """HOD-scope-only failure (REQ-HOD-004).

    Unlike ``integrity_is_failing()`` (flat merge of ``hod`` worst-of'd with
    ``scanner``), this reads only the cached ``hod`` partition — an unrelated
    scanner-tab bridge failure (e.g. sticky ``scanner_ibkr_bridge`` timeout)
    must not suppress HOD alerts. Genuine HOD degradation (dead/stale ticks,
    empty active set) is still caught natively by ``evaluate_hod_integrity()``'s
    own ``hod_ticks_flowing`` / ``hod_active_set`` checks.
    """
    if _last_report is None:
        return False
    hod = _last_report.get("hod") or {}
    return (hod.get("status") or "pass").strip().lower() == "fail"


def _cache_age(ts: float | None) -> float | None:
    if not ts:
        return None
    return max(0.0, time.time() - float(ts))


def build_hod_integrity_report() -> dict[str, Any]:
    import hod_momo as hm
    import hod_momo_active as active
    from alpaca import _get_discovery_provider
    from ibkr import client as ibkr_client

    flow = hm.get_flow_stats()
    provider = (_get_discovery_provider() or "").strip().lower()
    active_metrics = active.metrics_snapshot()
    state = get_runtime_state()
    snap = {
        **flow,
        **active_metrics,
        "universe_size": len(state.hod_momo_universe),
        "discovery_provider": provider,
        "ibkr_connected": ibkr_client.is_connected() if provider == "ibkr" else None,
    }
    report = evaluate_hod_integrity(snap)
    report["checked_at"] = time.time()
    report["metrics"] = snap
    return report


def build_scanner_integrity_report() -> dict[str, Any]:
    from alpaca import _get_discovery_provider
    from ibkr import client as ibkr_client
    from ibkr import scanner_l1 as ibkr_scanner_l1

    provider = (_get_discovery_provider() or "").strip().lower()
    l1_age = None
    last_ok = ibkr_scanner_l1.get_last_ok_ts()
    if last_ok:
        l1_age = _cache_age(last_ok)

    from ibkr import scanner_session as _scanner_session

    state = get_runtime_state()
    sub = ibkr_scanner_l1.get_subscription_state()

    def _frozen(table: str) -> bool:
        # Defensive: some tests/doubles pass a minimal state object without
        # TableState fields — treat that as "not frozen" rather than crash.
        try:
            return _scanner_session.is_table_frozen(state, table)
        except AttributeError:
            return False

    snap = {
        "discovery_provider": provider,
        "ibkr_connected": ibkr_client.is_connected() if provider == "ibkr" else None,
        "current_mode": (state.current_mode or "").strip().lower(),
        "gapper_count": len(state.gapper_cache),
        "gainer_count": len(state.gainer_cache),
        "loser_count": len(state.loser_cache),
        "afterhours_count": len(state.afterhours_cache or []),
        "gapper_age_sec": _cache_age(state.gapper_cache_ts or None),
        "gainer_age_sec": _cache_age(state.gainer_cache_ts or None),
        "loser_age_sec": _cache_age(state.loser_cache_ts or None),
        "afterhours_age_sec": _cache_age(
            getattr(state, "afterhours_cache_ts", None) or None
        ),
        # ADR 008 — frozen tables are immutable by design; a frozen table
        # never fails/warns on cache age. See evaluate_scanner_integrity.
        "gapper_frozen": _frozen(_scanner_session.TABLE_GAPPERS),
        "gainer_frozen": _frozen(_scanner_session.TABLE_GAINERS),
        "loser_frozen": _frozen(_scanner_session.TABLE_LOSERS),
        "afterhours_frozen": _frozen(_scanner_session.TABLE_AFTERHOURS),
        "scanner_l1_age_sec": l1_age,
        "l1_active_total": sub.get("active_total"),
        "l1_active_tab": sub.get("active_tab"),
        "l1_active_hod": sub.get("active_hod"),
        "l1_error": sub.get("error"),
        "ibkr_bridge_last_error": getattr(state, "ibkr_bridge_last_error", "") or "",
        "ibkr_bridge_last_error_age_sec": _cache_age(
            getattr(state, "ibkr_bridge_last_error_ts", None) or None
        ),
    }
    report = evaluate_scanner_integrity(snap)
    report["checked_at"] = time.time()
    report["metrics"] = snap
    return report


def build_all_integrity_report() -> dict[str, Any]:
    global _last_merged_status, _last_report, _last_report_ts
    hod = build_hod_integrity_report()
    scan = build_scanner_integrity_report()
    merged = merge_integrity(hod, scan)
    merged["checked_at"] = time.time()
    merged["hod"] = hod
    merged["scanner"] = scan
    _last_merged_status = (merged.get("status") or "fail").strip().lower()
    _last_report = merged
    _last_report_ts = float(merged["checked_at"])
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
            from ibkr.errors import describe_exc

            logger.warning(
                "Integrity loop error: %s",
                describe_exc(exc),
                exc_info=True,
            )
