"""HOD Momo + scanner integrity evaluators — fail loud on invisible data bugs.

Pure functions over a metrics snapshot. Used by:
  - GET /api/hod-momo/debug/integrity
  - GET /api/scan/integrity
  - GET /api/integrity
  - tools/hod_momo_integrity_check.py
  - background integrity_loop (loud WARN logs)

Statuses: pass | warn | fail. Overall = worst check.
"""
from __future__ import annotations

from typing import Any

from constants import (
    HOD_MOMO_ACTIVE_SET_CAPACITY,
    HOD_MOMO_INTEGRITY_ACTIVE_EVAL_MAX_SEC,
    HOD_MOMO_INTEGRITY_ACTIVE_EVAL_P95_SEC,
    HOD_MOMO_INTEGRITY_ACTIVE_QUOTE_MAX_SEC,
    HOD_MOMO_INTEGRITY_ACTIVE_QUOTE_P95_SEC,
    HOD_MOMO_INTEGRITY_ENRICHED_MIN_PCT,
    HOD_MOMO_INTEGRITY_SEED_WARN_AFTER_SEC,
    HOD_MOMO_INTEGRITY_SURGE_MIN_SPAN_SEC,
    HOD_MOMO_INTEGRITY_SURGE_PENDING_WARN,
    HOD_MOMO_INTEGRITY_SURGE_READY_MIN_PCT,
    HOD_MOMO_INTEGRITY_TICK_STALE_SEC,
    HOD_MOMO_INTEGRITY_TICK_WARN_SEC,
    HOD_MOMO_INTEGRITY_WARMUP_SEC,
    SCANNER_INTEGRITY_CACHE_STALE_SEC,
)

_STATUS_RANK = {"pass": 0, "warn": 1, "fail": 2}


def _worst(statuses: list[str]) -> str:
    worst = "pass"
    for s in statuses:
        if _STATUS_RANK.get(s, 0) > _STATUS_RANK[worst]:
            worst = s
    return worst


def _check(cid: str, status: str, detail: str) -> dict[str, str]:
    return {"id": cid, "status": status, "detail": detail}


def _age_gate(
    *,
    cid: str,
    p95: float | None,
    mx: float | None,
    p95_limit: float,
    max_limit: float,
    label: str,
) -> dict[str, str]:
    if p95 is None or mx is None:
        return _check(cid, "warn", f"{label}: no samples yet")
    if mx > max_limit or p95 > p95_limit:
        return _check(
            cid,
            "fail",
            f"{label}: p95={p95:.2f}s max={mx:.2f}s "
            f"(need p95<={p95_limit:.0f}s max<={max_limit:.0f}s)",
        )
    if p95 > p95_limit * 0.75:
        return _check(
            cid,
            "warn",
            f"{label}: p95={p95:.2f}s max={mx:.2f}s (approaching SLO)",
        )
    return _check(cid, "pass", f"{label}: p95={p95:.2f}s max={mx:.2f}s")


def evaluate_hod_integrity(snap: dict[str, Any]) -> dict[str, Any]:
    """Evaluate HOD Momo data-flow health from a metrics snapshot."""
    checks: list[dict[str, str]] = []
    universe = int(snap.get("universe_size") or 0)
    active_n = int(snap.get("active_set_size") or 0)
    uncovered_n = int(snap.get("uncovered_count") or 0)
    trades = int(snap.get("total_trades_seen") or 0)
    last_age = snap.get("last_trade_age_sec")
    uptime = float(snap.get("process_uptime_sec") or 0.0)
    buf_n = int(snap.get("buffer_symbol_count") or 0)
    ready_n = int(snap.get("surge_ready_count") or 0)
    seeded_n = int(snap.get("surge_seeded_count") or 0)
    pending = int(snap.get("pending_surge_seeds") or 0)
    seed_size = int(snap.get("watch_seed_size") or 0)
    provider = (snap.get("discovery_provider") or "").strip().lower()
    rvol_n = int(snap.get("snaps_with_rvol") or 0)
    tracked = int(snap.get("snaps_tracked") or 0)
    ibkr_ok = snap.get("ibkr_connected")
    surge_none_after_seed = int(snap.get("surge_none_after_seed_count") or 0)
    active_coverage = snap.get("active_coverage_pct")

    if universe <= 0:
        checks.append(_check(
            "hod_ticks_flowing",
            "warn",
            "watch universe empty -- no symbols to price (scanner/seeds may be down)",
        ))
    elif uptime < HOD_MOMO_INTEGRITY_WARMUP_SEC:
        checks.append(_check(
            "hod_ticks_flowing",
            "pass",
            f"warmup ({uptime:.0f}s < {HOD_MOMO_INTEGRITY_WARMUP_SEC:.0f}s) -- tick check deferred",
        ))
    elif last_age is None or trades <= 0:
        checks.append(_check(
            "hod_ticks_flowing",
            "fail",
            f"universe={universe} but total_trades_seen={trades} -- table reprice not feeding HOD",
        ))
    elif float(last_age) > HOD_MOMO_INTEGRITY_TICK_STALE_SEC:
        checks.append(_check(
            "hod_ticks_flowing",
            "fail",
            f"last HOD tick {float(last_age):.1f}s ago "
            f"(>{HOD_MOMO_INTEGRITY_TICK_STALE_SEC:.0f}s) -- not second-by-second",
        ))
    elif float(last_age) > HOD_MOMO_INTEGRITY_TICK_WARN_SEC:
        checks.append(_check(
            "hod_ticks_flowing",
            "warn",
            f"last HOD tick {float(last_age):.1f}s ago "
            f"(want <={HOD_MOMO_INTEGRITY_TICK_WARN_SEC:.0f}s)",
        ))
    else:
        checks.append(_check(
            "hod_ticks_flowing",
            "pass",
            f"trades={trades} last_tick={float(last_age):.1f}s ago universe={universe}",
        ))

    capacity = int(snap.get("active_set_capacity") or HOD_MOMO_ACTIVE_SET_CAPACITY)
    if active_n <= 0 and universe > 0 and uptime >= HOD_MOMO_INTEGRITY_WARMUP_SEC:
        checks.append(_check(
            "hod_active_set",
            "fail",
            f"active_set empty while discovery universe={universe}",
        ))
    else:
        detail = (
            f"active={active_n}/{capacity} uncovered={uncovered_n} "
            f"discovery={universe}"
        )
        if active_coverage is not None and float(active_coverage) < 100.0 and active_n > 0:
            checks.append(_check(
                "hod_active_set",
                "fail",
                f"{detail}; coverage={float(active_coverage):.0f}% "
                f"(need 100% recent quote+eval on active set)",
            ))
        else:
            checks.append(_check("hod_active_set", "pass", detail))

    checks.append(_age_gate(
        cid="hod_active_quote_age",
        p95=snap.get("active_quote_age_p95"),
        mx=snap.get("active_quote_age_max"),
        p95_limit=HOD_MOMO_INTEGRITY_ACTIVE_QUOTE_P95_SEC,
        max_limit=HOD_MOMO_INTEGRITY_ACTIVE_QUOTE_MAX_SEC,
        label="active quote age",
    ))
    checks.append(_age_gate(
        cid="hod_active_eval_age",
        p95=snap.get("active_eval_age_p95"),
        mx=snap.get("active_eval_age_max"),
        p95_limit=HOD_MOMO_INTEGRITY_ACTIVE_EVAL_P95_SEC,
        max_limit=HOD_MOMO_INTEGRITY_ACTIVE_EVAL_MAX_SEC,
        label="active eval age",
    ))

    if buf_n <= 0:
        status = "warn" if universe > 0 else "pass"
        checks.append(_check(
            "hod_surge_buffer",
            status,
            "no price buffers yet -- Squeeze cannot compute 5m surge",
        ))
    else:
        ready_pct = 100.0 * ready_n / buf_n
        if ready_pct < HOD_MOMO_INTEGRITY_SURGE_READY_MIN_PCT and seeded_n < max(1, buf_n // 4):
            checks.append(_check(
                "hod_surge_buffer",
                "fail",
                f"only {ready_n}/{buf_n} ({ready_pct:.0f}%) buffers span "
                f">={HOD_MOMO_INTEGRITY_SURGE_MIN_SPAN_SEC:.0f}s; seeded={seeded_n} "
                f"pending={pending} -- Squeeze cold-start risk (HKIT-class miss)",
            ))
        elif ready_pct < HOD_MOMO_INTEGRITY_SURGE_READY_MIN_PCT:
            checks.append(_check(
                "hod_surge_buffer",
                "warn",
                f"surge ready {ready_n}/{buf_n} ({ready_pct:.0f}%); "
                f"seeded={seeded_n} pending={pending}",
            ))
        else:
            checks.append(_check(
                "hod_surge_buffer",
                "pass",
                f"surge ready {ready_n}/{buf_n} ({ready_pct:.0f}%); seeded={seeded_n}",
            ))

    if surge_none_after_seed > 0:
        checks.append(_check(
            "hod_surge_after_seed",
            "fail",
            f"{surge_none_after_seed} seeded symbol(s) still have surge=None "
            f"-- historical seed incomplete or window mismatch",
        ))
    else:
        checks.append(_check(
            "hod_surge_after_seed",
            "pass",
            "no surge=None after completed historical seed",
        ))

    if pending >= HOD_MOMO_INTEGRITY_SURGE_PENDING_WARN:
        checks.append(_check(
            "hod_surge_seed_backlog",
            "warn",
            f"pending_surge_seeds={pending} -- Squeeze cold-start queue backing up",
        ))
    else:
        checks.append(_check(
            "hod_surge_seed_backlog",
            "pass",
            f"pending_surge_seeds={pending}",
        ))

    if provider == "ibkr":
        if ibkr_ok is False:
            checks.append(_check(
                "hod_volume_seeds",
                "fail",
                "discovery=ibkr but Gateway not connected -- seeds and ticks will starve",
            ))
        elif seed_size <= 0 and uptime >= HOD_MOMO_INTEGRITY_SEED_WARN_AFTER_SEC:
            checks.append(_check(
                "hod_volume_seeds",
                "warn",
                f"watch_seed_size=0 after {uptime:.0f}s -- HOT_BY_VOLUME seeds empty; "
                f"late runners may arrive only via Top Gainers",
            ))
        elif seed_size <= 0:
            checks.append(_check(
                "hod_volume_seeds",
                "pass",
                f"volume seeds still warming "
                f"({uptime:.0f}s < {HOD_MOMO_INTEGRITY_SEED_WARN_AFTER_SEC:.0f}s)",
            ))
        else:
            checks.append(_check(
                "hod_volume_seeds",
                "pass",
                f"watch_seed_size={seed_size}",
            ))
    else:
        checks.append(_check(
            "hod_volume_seeds",
            "pass",
            f"provider={provider or 'unknown'} -- IBKR seed check skipped",
        ))

    if tracked <= 0:
        checks.append(_check("hod_enrichment", "warn", "no ticker snaps tracked yet"))
    else:
        pct = 100.0 * rvol_n / tracked
        if pct < HOD_MOMO_INTEGRITY_ENRICHED_MIN_PCT and uptime >= HOD_MOMO_INTEGRITY_WARMUP_SEC:
            checks.append(_check(
                "hod_enrichment",
                "warn",
                f"rvol known on {rvol_n}/{tracked} ({pct:.0f}%) snaps -- RelVol strategies starved",
            ))
        else:
            checks.append(_check(
                "hod_enrichment",
                "pass",
                f"rvol known on {rvol_n}/{tracked} ({pct:.0f}%) snaps",
            ))

    status = _worst([c["status"] for c in checks])
    return {
        "ok": status == "pass",
        "status": status,
        "scope": "hod_momo",
        "checks": checks,
    }


def evaluate_scanner_integrity(snap: dict[str, Any]) -> dict[str, Any]:
    """Evaluate gappers/gainers/losers cache freshness + discovery feed."""
    checks: list[dict[str, str]] = []
    provider = (snap.get("discovery_provider") or "").strip().lower()
    ibkr_ok = snap.get("ibkr_connected")

    if provider == "ibkr" and ibkr_ok is False:
        checks.append(_check(
            "scanner_feed",
            "fail",
            "discovery=ibkr but Gateway disconnected -- scanners will look empty",
        ))
    else:
        checks.append(_check(
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
                checks.append(_check(
                    f"scanner_{name}",
                    "pass",
                    f"{name}: empty (no cache yet) -- OK if another scanner list is live",
                ))
            else:
                checks.append(_check(
                    f"scanner_{name}",
                    "warn",
                    f"{name}: no cache timestamp",
                ))
            continue
        age_f = float(age)
        if count <= 0 and age_f > SCANNER_INTEGRITY_CACHE_STALE_SEC:
            checks.append(_check(
                f"scanner_{name}",
                "fail" if provider == "ibkr" else "warn",
                f"{name}: 0 rows and cache {age_f:.0f}s old",
            ))
        elif age_f > SCANNER_INTEGRITY_CACHE_STALE_SEC:
            checks.append(_check(
                f"scanner_{name}",
                "warn",
                f"{name}: {count} rows but cache {age_f:.0f}s old "
                f"(>{SCANNER_INTEGRITY_CACHE_STALE_SEC:.0f}s)",
            ))
        else:
            checks.append(_check(
                f"scanner_{name}",
                "pass",
                f"{name}: {count} rows age={age_f:.0f}s",
            ))

    reprice_age = snap.get("table_reprice_age_sec")
    if provider == "ibkr":
        if reprice_age is None:
            checks.append(_check(
                "scanner_table_reprice",
                "warn",
                "no table-reprice heartbeat yet",
            ))
        elif float(reprice_age) > HOD_MOMO_INTEGRITY_TICK_STALE_SEC:
            checks.append(_check(
                "scanner_table_reprice",
                "fail",
                f"table reprice {float(reprice_age):.1f}s ago -- UI prices not second-by-second",
            ))
        elif float(reprice_age) > HOD_MOMO_INTEGRITY_TICK_WARN_SEC:
            checks.append(_check(
                "scanner_table_reprice",
                "warn",
                f"table reprice {float(reprice_age):.1f}s ago "
                f"(want <={HOD_MOMO_INTEGRITY_TICK_WARN_SEC:.0f}s)",
            ))
        else:
            checks.append(_check(
                "scanner_table_reprice",
                "pass",
                f"table reprice {float(reprice_age):.1f}s ago",
            ))

    status = _worst([c["status"] for c in checks])
    return {
        "ok": status == "pass",
        "status": status,
        "scope": "scanner",
        "checks": checks,
    }


def merge_integrity(*reports: dict[str, Any]) -> dict[str, Any]:
    """Combine HOD + scanner reports into one overall verdict."""
    checks: list[dict[str, str]] = []
    for r in reports:
        checks.extend(list(r.get("checks") or []))
    status = _worst([c["status"] for c in checks]) if checks else "pass"
    return {
        "ok": status == "pass",
        "status": status,
        "scope": "all",
        "checks": checks,
        "parts": {r.get("scope", "?"): r.get("status") for r in reports},
    }
