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
    gainer_count = int(snap.get("gainer_count") or 0)
    gainer_age = snap.get("gainer_age_sec")
    gainer_cache_fresh = (
        gainer_count > 0
        and gainer_age is not None
        and float(gainer_age) <= SCANNER_INTEGRITY_CACHE_STALE_SEC
    )
    if provider == "ibkr" and bridge_err:
        age_bit = (
            f" ({float(bridge_age):.0f}s ago)"
            if bridge_age is not None
            else ""
        )
        # Sticky leftover after a recovered movers refresh must not hard-fail
        # the whole banner when Top Gainers is still live.
        status = "warn" if gainer_cache_fresh else "fail"
        detail = f"IBKR discovery bridge error{age_bit}: {bridge_err}"
        if status == "warn":
            detail += " — gainer cache still fresh (recovered)"
        checks.append(check("scanner_ibkr_bridge", status, detail))

    for name, count_key, age_key, frozen_key in (
        ("gappers", "gapper_count", "gapper_age_sec", "gapper_frozen"),
        ("gainers", "gainer_count", "gainer_age_sec", "gainer_frozen"),
        ("losers", "loser_count", "loser_age_sec", "loser_frozen"),
    ):
        count = int(snap.get(count_key) or 0)
        age = snap.get(age_key)

        # ADR 008: a session-frozen table is immutable by design — its age
        # only grows because it must never be rewritten, not because the
        # feed is broken. Matching-session freeze metadata always passes.
        if snap.get(frozen_key):
            age_bit = f" age={float(age):.0f}s" if age is not None else ""
            checks.append(check(
                f"scanner_{name}",
                "pass",
                f"{name}: {count} rows{age_bit} — frozen for the session (ADR 008)",
            ))
            continue

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

        # Losers are a secondary UI table — empty/stale losers must not paint
        # Integrity fail when Top Gainers (the HOD eligibility source) is live.
        if name == "losers" and gainer_cache_fresh:
            age_bit = f" age={float(age):.0f}s" if age is not None else ""
            checks.append(check(
                "scanner_losers",
                "pass",
                f"losers: {count} rows{age_bit} — secondary list "
                f"(gainers live; not required for HOD)",
            ))
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
            sticky = (snap.get("ibkr_bridge_last_error") or "").strip()
            detail = f"gappers: 0 rows age={age_f:.0f}s while discovery=ibkr connected"
            if sticky:
                detail += f" — last bridge error: {sticky}"
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

    l1_age = snap.get("scanner_l1_age_sec")
    if provider == "ibkr":
        if l1_age is None:
            checks.append(check(
                "scanner_l1_stream",
                "warn",
                "no active-table L1 tick yet",
            ))
        elif float(l1_age) > HOD_MOMO_INTEGRITY_TICK_STALE_SEC:
            checks.append(check(
                "scanner_l1_stream",
                "fail",
                f"active-table L1 tick {float(l1_age):.1f}s ago -- UI prices stale",
            ))
        elif float(l1_age) > HOD_MOMO_INTEGRITY_TICK_WARN_SEC:
            checks.append(check(
                "scanner_l1_stream",
                "warn",
                f"active-table L1 tick {float(l1_age):.1f}s ago "
                f"(want <={HOD_MOMO_INTEGRITY_TICK_WARN_SEC:.0f}s)",
            ))
        else:
            checks.append(check(
                "scanner_l1_stream",
                "pass",
                f"active-table L1 tick {float(l1_age):.1f}s ago",
            ))

    status = worst([c["status"] for c in checks])
    return {
        "ok": status == "pass",
        "status": status,
        "scope": "scanner",
        "checks": checks,
    }
