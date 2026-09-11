"""Scanner integrity evaluator (ADR 004 strangler split)."""
from __future__ import annotations

from typing import Any

from constants import (
    HOD_MOMO_INTEGRITY_TICK_STALE_SEC,
    HOD_MOMO_INTEGRITY_TICK_WARN_SEC,
    SCANNER_INTEGRITY_CACHE_STALE_SEC,
    SCANNER_ROW_PRICE_FAIL_PCT,
    SCANNER_ROW_PRICE_GRACE_SEC,
    SCANNER_ROW_PRICE_WARN_PCT,
)
from hod_momo_integrity_common import check, worst

# Gappers freeze at the open by design — do not fail RTH/AH on a stale gapper cache.
_GAPPER_OPTIONAL_MODES = frozenset({"market", "regular", "rth", "afterhours", "closed"})

# Gainers owns discovery while its window is open (04:00-16:00 ET). An empty
# Gainers roster inside this window is a broken pipeline, not a quiet tape.
_GAINER_LIVE_MODES = frozenset({"premarket", "market", "regular", "rth"})

# Sibling-vouch (D-028): an empty table may pass only when another list is
# actually live with rows. Frozen-with-rows counts (ADR 008). Large Cap does
# not vouch -- it is a swing table, not a day-trade roster.
_SIBLING_TABLES = (
    ("gappers", "gapper_count", "gapper_age_sec", "gapper_frozen"),
    ("gainers", "gainer_count", "gainer_age_sec", "gainer_frozen"),
    ("losers", "loser_count", "loser_age_sec", "loser_frozen"),
    ("afterhours", "afterhours_count", "afterhours_age_sec", "afterhours_frozen"),
)


def _table_is_live(
    snap: dict[str, Any],
    count_key: str,
    age_key: str,
    frozen_key: str,
) -> bool:
    count = int(snap.get(count_key) or 0)
    if count <= 0:
        return False
    if snap.get(frozen_key):
        return True
    age = snap.get(age_key)
    return age is not None and float(age) <= SCANNER_INTEGRITY_CACHE_STALE_SEC


def _sibling_live_name(snap: dict[str, Any], exclude: str) -> str | None:
    for name, count_key, age_key, frozen_key in _SIBLING_TABLES:
        if name == exclude:
            continue
        if _table_is_live(snap, count_key, age_key, frozen_key):
            return name
    return None


def _row_price_checks(coverage: list[dict[str, Any]]) -> list[dict[str, str]]:
    """One check per displayed live table: are its rows actually priced?

    Name-only admission (ADR 008) means a fresh roster shows ``price=null``
    briefly, so coverage is only judged once the roster is older than
    ``SCANNER_ROW_PRICE_GRACE_SEC``. Below that window a table with rows the
    operator can see but no prices is L1 starvation, and every other scanner
    check here would still say pass.
    """
    out: list[dict[str, str]] = []
    for entry in coverage:
        table = str(entry.get("table") or "unknown")
        rows = int(entry.get("rows") or 0)
        priced = int(entry.get("priced") or 0)
        age = entry.get("roster_age_sec")
        if rows <= 0:
            continue
        pct = priced / rows * 100.0
        if age is None or float(age) < SCANNER_ROW_PRICE_GRACE_SEC:
            out.append(check(
                f"scanner_{table}_row_prices",
                "pass",
                f"{table}: {priced}/{rows} rows priced -- roster still inside "
                f"the {SCANNER_ROW_PRICE_GRACE_SEC:.0f}s admission grace",
            ))
            continue
        detail = (
            f"{table}: only {priced}/{rows} rows priced ({pct:.0f}%) "
            f"{float(age):.0f}s after roster commit while displayed and live "
            f"-- active-tab L1 is starved"
        )
        if pct < SCANNER_ROW_PRICE_FAIL_PCT:
            out.append(check(f"scanner_{table}_row_prices", "fail", detail))
        elif pct < SCANNER_ROW_PRICE_WARN_PCT:
            out.append(check(f"scanner_{table}_row_prices", "warn", detail))
        else:
            out.append(check(
                f"scanner_{table}_row_prices",
                "pass",
                f"{table}: {priced}/{rows} rows priced ({pct:.0f}%)",
            ))
    return out


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
            "discovery=ibkr but IBKR session not usable -- scanners will look empty",
        ))
    else:
        checks.append(check(
            "scanner_feed",
            "pass",
            f"provider={provider or 'unknown'} usable={ibkr_ok} mode={mode or 'unknown'}",
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
                # A missing timestamp means no roster ever committed. For the
                # feed that owns discovery (Gainers, live 04:00-16:00 ET) that
                # is a dead pipeline, not a quiet market: on 2026-08-24 this
                # branch reported "pass -- OK if another scanner list is live"
                # for eight minutes while IB was pushing names the roster
                # commit kept dropping. Never let one empty table vouch for
                # another empty table.
                if (
                    provider == "ibkr"
                    and ibkr_ok
                    and name == "gainers"
                    and mode in _GAINER_LIVE_MODES
                ):
                    checks.append(check(
                        "scanner_gainers",
                        "fail",
                        "gainers: no roster ever committed while discovery=ibkr "
                        "connected -- IB names are not reaching the table "
                        "(check roster commit / feed_error)",
                    ))
                    continue
                sibling = _sibling_live_name(snap, name)
                if sibling:
                    checks.append(check(
                        f"scanner_{name}",
                        "pass",
                        f"{name}: empty (no cache yet) -- {sibling} is live with rows",
                    ))
                    continue
                if name == "gappers" and mode == "premarket" and provider == "ibkr":
                    checks.append(check(
                        "scanner_gappers",
                        "warn",
                        "gappers: empty (no cache yet) -- no live sibling scanner list",
                    ))
                elif provider == "ibkr" and ibkr_ok:
                    checks.append(check(
                        f"scanner_{name}",
                        "fail",
                        f"{name}: empty (no cache yet) -- no live sibling scanner list",
                    ))
                else:
                    checks.append(check(
                        f"scanner_{name}",
                        "pass",
                        f"{name}: empty (no cache yet)",
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

    checks.extend(_row_price_checks(snap.get("row_price_coverage") or []))

    # Feed liveness (socket alive) is the honest signal; fall back to
    # price-change recency only when no event timestamp exists yet.
    l1_event_age = snap.get("scanner_l1_event_age_sec")
    l1_age = snap.get("scanner_l1_age_sec")
    stream_age = l1_event_age if l1_event_age is not None else l1_age
    if provider == "ibkr":
        if stream_age is None:
            checks.append(check(
                "scanner_l1_stream",
                "warn",
                "no active-table L1 event yet",
            ))
        elif float(stream_age) > HOD_MOMO_INTEGRITY_TICK_STALE_SEC:
            checks.append(check(
                "scanner_l1_stream",
                "fail",
                f"active-table L1 feed {float(stream_age):.1f}s ago -- socket stale",
            ))
        elif float(stream_age) > HOD_MOMO_INTEGRITY_TICK_WARN_SEC:
            checks.append(check(
                "scanner_l1_stream",
                "warn",
                f"active-table L1 feed {float(stream_age):.1f}s ago "
                f"(want <={HOD_MOMO_INTEGRITY_TICK_WARN_SEC:.0f}s)",
            ))
        else:
            checks.append(check(
                "scanner_l1_stream",
                "pass",
                f"active-table L1 feed {float(stream_age):.1f}s ago",
            ))

    status = worst([c["status"] for c in checks])
    return {
        "ok": status == "pass",
        "status": status,
        "scope": "scanner",
        "checks": checks,
    }
