"""Scanner integrity evaluator (ADR 004 strangler split)."""
from __future__ import annotations

from typing import Any

from constants import (
    HOD_MOMO_INTEGRITY_TICK_STALE_SEC,
    HOD_MOMO_INTEGRITY_TICK_WARN_SEC,
    SCANNER_INTEGRITY_CACHE_STALE_SEC,
)
from hod_momo_integrity_common import check, worst

# Gappers freeze at the open by design — do not fail RTH/AH on a stale gapper cache.
_GAPPER_OPTIONAL_MODES = frozenset({"market", "regular", "rth", "afterhours", "closed"})


def evaluate_scanner_integrity(snap: dict[str, Any]) -> dict[str, Any]:
    """Evaluate gappers/gainers/losers cache freshness + discovery feed."""
    checks: list[dict[str, str]] = []
    provider = (snap.get("discovery_provider") or "").strip().lower()
    ibkr_ok = snap.get("ibkr_connected")
    mode = (snap.get("current_mode") or "").strip().lower()

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
            f"provider={provider or 'unknown'} connected={ibkr_ok} mode={mode or 'unknown'}",
        ))

    bridge_err = (snap.get("ibkr_bridge_last_error") or "").strip()
    bridge_age = snap.get("ibkr_bridge_last_error_age_sec")
    if provider == "ibkr" and bridge_err:
        age_bit = (
            f" ({float(bridge_age):.0f}s ago)"
            if bridge_age is not None
            else ""
        )
        checks.append(check(
            "scanner_ibkr_bridge",
            "fail",
            f"IBKR discovery bridge error{age_bit}: {bridge_err}",
        ))

    for name, count_key, age_key in (
        ("gappers", "gapper_count", "gapper_age_sec"),
        ("gainers", "gainer_count", "gainer_age_sec"),
        ("losers", "loser_count", "loser_age_sec"),
    ):
        count = int(snap.get(count_key) or 0)
        age = snap.get(age_key)

        if name == "gappers" and mode in _GAPPER_OPTIONAL_MODES:
            if age is not None:
                detail = (
                    f"gappers: {count} rows age={float(age):.0f}s "
                    f"— offline by design after open (mode={mode})"
                )
            else:
                detail = f"gappers: offline by design after open (mode={mode})"
            checks.append(check("scanner_gappers", "pass", detail))
            continue

        if age is None:
            if count <= 0:
                # Premarket empty with no timestamp is suspicious when IBKR is up.
                status = (
                    "warn"
                    if name == "gappers" and mode == "premarket" and provider == "ibkr"
                    else "pass"
                )
                checks.append(check(
                    f"scanner_{name}",
                    status,
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
        # Premarket: 0 gappers while IBKR is connected is a fail-loud signal
        # (bridge timeouts used to wipe the cache and look like "no gaps").
        if (
            name == "gappers"
            and mode == "premarket"
            and provider == "ibkr"
            and count <= 0
        ):
            bridge_err = (snap.get("ibkr_bridge_last_error") or "").strip()
            detail = f"gappers: 0 rows age={age_f:.0f}s while discovery=ibkr connected"
            if bridge_err:
                detail += f" — last bridge error: {bridge_err}"
            else:
                detail += " — check IBKR scanner / bridge (not a silent 'no gaps' market)"
            checks.append(check("scanner_gappers", "fail", detail))
            continue
        if count <= 0 and age_f > SCANNER_INTEGRITY_CACHE_STALE_SEC:
            # AH: empty/stale RTH gainers are secondary when afterhours list is live.
            ah_live = (
                name == "gainers"
                and mode == "afterhours"
                and int(snap.get("afterhours_count") or 0) > 0
            )
            status = "warn" if ah_live or provider != "ibkr" else "fail"
            detail = f"{name}: 0 rows and cache {age_f:.0f}s old"
            if ah_live:
                detail += (
                    f" — AH movers live "
                    f"(afterhours={int(snap.get('afterhours_count') or 0)})"
                )
            checks.append(check(f"scanner_{name}", status, detail))
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
