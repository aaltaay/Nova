"""Scanner integrity evaluator (ADR 004 strangler split)."""
from __future__ import annotations

from typing import Any

from constants import (
    HOD_MOMO_INTEGRITY_TICK_STALE_SEC,
    HOD_MOMO_INTEGRITY_TICK_WARN_SEC,
    SCANNER_INTEGRITY_CACHE_STALE_SEC,
)
from hod_momo_integrity_common import check, worst


def evaluate_scanner_integrity(snap: dict[str, Any]) -> dict[str, Any]:
    """Evaluate gappers/gainers/losers cache freshness + discovery feed."""
    checks: list[dict[str, str]] = []
    provider = (snap.get("discovery_provider") or "").strip().lower()
    ibkr_ok = snap.get("ibkr_connected")

    if provider == "ibkr" and ibkr_ok is False:
        checks.append(check(
            "scanner_feed",
            "fail",
            "discovery=ibkr but Gateway disconnected -- scanners will look empty",
        ))
    else:
        checks.append(check(
            "scanner_feed",
            "pass",
            f"provider={provider or 'unknown'} connected={ibkr_ok}",
        ))

    for name, count_key, age_key in (
        ("gappers", "gapper_count", "gapper_age_sec"),
        ("gainers", "gainer_count", "gainer_age_sec"),
        ("losers", "loser_count", "loser_age_sec"),
    ):
        count = int(snap.get(count_key) or 0)
        age = snap.get(age_key)
        if age is None:
            if count <= 0:
                checks.append(check(
                    f"scanner_{name}",
                    "pass",
                    f"{name}: empty (no cache yet) -- OK if another scanner list is live",
                ))
            else:
                checks.append(check(
                    f"scanner_{name}",
                    "warn",
                    f"{name}: no cache timestamp",
                ))
            continue
        age_f = float(age)
        if count <= 0 and age_f > SCANNER_INTEGRITY_CACHE_STALE_SEC:
            checks.append(check(
                f"scanner_{name}",
                "fail" if provider == "ibkr" else "warn",
                f"{name}: 0 rows and cache {age_f:.0f}s old",
            ))
        elif age_f > SCANNER_INTEGRITY_CACHE_STALE_SEC:
            checks.append(check(
                f"scanner_{name}",
                "warn",
                f"{name}: {count} rows but cache {age_f:.0f}s old "
                f"(>{SCANNER_INTEGRITY_CACHE_STALE_SEC:.0f}s)",
            ))
        else:
            checks.append(check(
                f"scanner_{name}",
                "pass",
                f"{name}: {count} rows age={age_f:.0f}s",
            ))

    reprice_age = snap.get("table_reprice_age_sec")
    if provider == "ibkr":
        if reprice_age is None:
            checks.append(check(
                "scanner_table_reprice",
                "warn",
                "no table-reprice heartbeat yet",
            ))
        elif float(reprice_age) > HOD_MOMO_INTEGRITY_TICK_STALE_SEC:
            checks.append(check(
                "scanner_table_reprice",
                "fail",
                f"table reprice {float(reprice_age):.1f}s ago -- UI prices not second-by-second",
            ))
        elif float(reprice_age) > HOD_MOMO_INTEGRITY_TICK_WARN_SEC:
            checks.append(check(
                "scanner_table_reprice",
                "warn",
                f"table reprice {float(reprice_age):.1f}s ago "
                f"(want <={HOD_MOMO_INTEGRITY_TICK_WARN_SEC:.0f}s)",
            ))
        else:
            checks.append(check(
                "scanner_table_reprice",
                "pass",
                f"table reprice {float(reprice_age):.1f}s ago",
            ))

    status = worst([c["status"] for c in checks])
    return {
        "ok": status == "pass",
        "status": status,
        "scope": "scanner",
        "checks": checks,
    }
