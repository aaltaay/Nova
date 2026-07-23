"""HOD Momo integrity evaluator (ADR 004 strangler split)."""
from __future__ import annotations

from typing import Any

from constants import (
    HOD_MOMO_ACTIVE_SET_CAPACITY,
    HOD_MOMO_INTEGRITY_ACTIVE_COVERAGE_FAIL_PCT,
    HOD_MOMO_INTEGRITY_ACTIVE_EVAL_MAX_SEC,
    HOD_MOMO_INTEGRITY_ACTIVE_EVAL_P95_SEC,
    HOD_MOMO_INTEGRITY_ACTIVE_QUOTE_MAX_SEC,
    HOD_MOMO_INTEGRITY_ACTIVE_QUOTE_P95_SEC,
    HOD_MOMO_INTEGRITY_ENRICHED_MIN_PCT,
    HOD_MOMO_INTEGRITY_SURGE_MIN_SPAN_SEC,
    HOD_MOMO_INTEGRITY_SURGE_PENDING_WARN,
    HOD_MOMO_INTEGRITY_SURGE_READY_MIN_PCT,
    HOD_MOMO_INTEGRITY_TICK_STALE_SEC,
    HOD_MOMO_INTEGRITY_TICK_WARN_SEC,
    HOD_MOMO_INTEGRITY_WARMUP_SEC,
)
from hod_momo_integrity_common import age_gate, check, worst


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
    rvol_n = int(snap.get("snaps_with_rvol") or 0)
    tracked = int(snap.get("snaps_tracked") or 0)
    surge_none_after_seed = int(snap.get("surge_none_after_seed_count") or 0)
    active_coverage = snap.get("active_coverage_pct")

    if universe <= 0:
        checks.append(check(
            "hod_ticks_flowing",
            "warn",
            "watch universe empty -- no symbols to price (Gappers/Gainers/Afterhours may be down)",
        ))
    elif uptime < HOD_MOMO_INTEGRITY_WARMUP_SEC:
        checks.append(check(
            "hod_ticks_flowing",
            "pass",
            f"warmup ({uptime:.0f}s < {HOD_MOMO_INTEGRITY_WARMUP_SEC:.0f}s) -- tick check deferred",
        ))
    elif last_age is None or trades <= 0:
        checks.append(check(
            "hod_ticks_flowing",
            "fail",
            f"universe={universe} but total_trades_seen={trades} -- table reprice not feeding HOD",
        ))
    elif float(last_age) > HOD_MOMO_INTEGRITY_TICK_STALE_SEC:
        checks.append(check(
            "hod_ticks_flowing",
            "fail",
            f"last HOD tick {float(last_age):.1f}s ago "
            f"(>{HOD_MOMO_INTEGRITY_TICK_STALE_SEC:.0f}s) -- not second-by-second",
        ))
    elif float(last_age) > HOD_MOMO_INTEGRITY_TICK_WARN_SEC:
        checks.append(check(
            "hod_ticks_flowing",
            "warn",
            f"last HOD tick {float(last_age):.1f}s ago "
            f"(want <={HOD_MOMO_INTEGRITY_TICK_WARN_SEC:.0f}s)",
        ))
    else:
        checks.append(check(
            "hod_ticks_flowing",
            "pass",
            f"trades={trades} last_tick={float(last_age):.1f}s ago universe={universe}",
        ))

    capacity = int(snap.get("active_set_capacity") or HOD_MOMO_ACTIVE_SET_CAPACITY)
    if active_n <= 0 and universe > 0 and uptime >= HOD_MOMO_INTEGRITY_WARMUP_SEC:
        checks.append(check(
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
            cov = float(active_coverage)
            # 98% is usually one unquoted explore admit; age gates catch real death.
            status = (
                "fail"
                if cov < float(HOD_MOMO_INTEGRITY_ACTIVE_COVERAGE_FAIL_PCT)
                else "warn"
            )
            checks.append(check(
                "hod_active_set",
                status,
                f"{detail}; coverage={cov:.0f}% "
                f"(fail below {float(HOD_MOMO_INTEGRITY_ACTIVE_COVERAGE_FAIL_PCT):.0f}%; "
                f"quote/eval age gates enforce SLO)",
            ))
        else:
            checks.append(check("hod_active_set", "pass", detail))

    checks.append(age_gate(
        cid="hod_active_quote_age",
        p95=snap.get("active_quote_age_p95"),
        mx=snap.get("active_quote_age_max"),
        p95_limit=HOD_MOMO_INTEGRITY_ACTIVE_QUOTE_P95_SEC,
        max_limit=HOD_MOMO_INTEGRITY_ACTIVE_QUOTE_MAX_SEC,
        label="active quote age",
    ))
    checks.append(age_gate(
        cid="hod_active_eval_age",
        p95=snap.get("active_eval_age_p95"),
        mx=snap.get("active_eval_age_max"),
        p95_limit=HOD_MOMO_INTEGRITY_ACTIVE_EVAL_P95_SEC,
        max_limit=HOD_MOMO_INTEGRITY_ACTIVE_EVAL_MAX_SEC,
        label="active eval age",
    ))

    if buf_n <= 0:
        status = "warn" if universe > 0 else "pass"
        checks.append(check(
            "hod_surge_buffer",
            status,
            "no price buffers yet -- Squeeze cannot compute 5m surge",
        ))
    else:
        ready_pct = 100.0 * ready_n / buf_n
        if ready_pct < HOD_MOMO_INTEGRITY_SURGE_READY_MIN_PCT and seeded_n < max(1, buf_n // 4):
            # While the seed queue is actively draining, warn — don't block
            # parity/observe on a transient post-reload cold start.
            status = "warn" if pending > 0 else "fail"
            checks.append(check(
                "hod_surge_buffer",
                status,
                f"only {ready_n}/{buf_n} ({ready_pct:.0f}%) buffers span "
                f">={HOD_MOMO_INTEGRITY_SURGE_MIN_SPAN_SEC:.0f}s; seeded={seeded_n} "
                f"pending={pending} -- Squeeze cold-start risk (HKIT-class miss)",
            ))
        elif ready_pct < HOD_MOMO_INTEGRITY_SURGE_READY_MIN_PCT:
            checks.append(check(
                "hod_surge_buffer",
                "warn",
                f"surge ready {ready_n}/{buf_n} ({ready_pct:.0f}%); "
                f"seeded={seeded_n} pending={pending}",
            ))
        else:
            checks.append(check(
                "hod_surge_buffer",
                "pass",
                f"surge ready {ready_n}/{buf_n} ({ready_pct:.0f}%); seeded={seeded_n}",
            ))

    if surge_none_after_seed > 0:
        # Hard-fail only when the live tape is also dead — otherwise Squeeze
        # simply skips those symbols while quote/eval SLOs can still pass.
        tape_dead = (
            last_age is None
            or trades <= 0
            or float(last_age) > HOD_MOMO_INTEGRITY_TICK_STALE_SEC
        )
        checks.append(check(
            "hod_surge_after_seed",
            "fail" if tape_dead else "warn",
            f"{surge_none_after_seed} seeded symbol(s) still have surge=None "
            f"-- historical seed incomplete or window mismatch",
        ))
    else:
        checks.append(check(
            "hod_surge_after_seed",
            "pass",
            "no surge=None after completed historical seed",
        ))

    if pending >= HOD_MOMO_INTEGRITY_SURGE_PENDING_WARN:
        checks.append(check(
            "hod_surge_seed_backlog",
            "warn",
            f"pending_surge_seeds={pending} -- Squeeze cold-start queue backing up",
        ))
    else:
        checks.append(check(
            "hod_surge_seed_backlog",
            "pass",
            f"pending_surge_seeds={pending}",
        ))

    if tracked <= 0:
        checks.append(check("hod_enrichment", "warn", "no ticker snaps tracked yet"))
    else:
        pct = 100.0 * rvol_n / tracked
        if pct < HOD_MOMO_INTEGRITY_ENRICHED_MIN_PCT and uptime >= HOD_MOMO_INTEGRITY_WARMUP_SEC:
            checks.append(check(
                "hod_enrichment",
                "warn",
                f"rvol known on {rvol_n}/{tracked} ({pct:.0f}%) snaps -- RelVol strategies starved",
            ))
        else:
            checks.append(check(
                "hod_enrichment",
                "pass",
                f"rvol known on {rvol_n}/{tracked} ({pct:.0f}%) snaps",
            ))

    status = worst([c["status"] for c in checks])
    return {
        "ok": status == "pass",
        "status": status,
        "scope": "hod_momo",
        "checks": checks,
    }
