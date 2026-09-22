"""Shared helpers for HOD Momo + scanner integrity evaluators (ADR 004)."""
from __future__ import annotations

_STATUS_RANK = {"pass": 0, "warn": 1, "fail": 2}


def worst(statuses: list[str]) -> str:
    worst_status = "pass"
    for s in statuses:
        if _STATUS_RANK.get(s, 0) > _STATUS_RANK[worst_status]:
            worst_status = s
    return worst_status


def check(cid: str, status: str, detail: str) -> dict[str, str]:
    return {"id": cid, "status": status, "detail": detail}


def session_is_idle(mode: str | None) -> bool:
    """Closed (and any other idle) session -- no live tape or roster expected.

    Reuses ``HOD_MOMO_INTEGRITY_TICK_IDLE_MODES`` so HOD buffer checks and
    scanner empty-cache checks share one session gate.
    """
    from constants import HOD_MOMO_INTEGRITY_TICK_IDLE_MODES

    return (mode or "").strip().lower() in HOD_MOMO_INTEGRITY_TICK_IDLE_MODES


def idle_pass(cid: str, mode: str, why: str) -> dict[str, str]:
    return check(cid, "pass", f"market closed (mode={mode}) -- {why}")


def age_gate(
    *,
    cid: str,
    p95: float | None,
    mx: float | None,
    p95_limit: float,
    max_limit: float,
    label: str,
) -> dict[str, str]:
    if p95 is None or mx is None:
        return check(cid, "warn", f"{label}: no samples yet")
    # Judge the figures the detail prints: a max of 3.004 s printed "3.00s"
    # beside "need max<=3s" and a red "fail" (QA W27, 2026-09-22).
    p95 = round(float(p95), 2)
    mx = round(float(mx), 2)
    if mx > max_limit or p95 > p95_limit:
        return check(
            cid,
            "fail",
            f"{label}: p95={p95:.2f}s max={mx:.2f}s "
            f"(need p95<={p95_limit:g}s max<={max_limit:g}s)",
        )
    if p95 > p95_limit * 0.75:
        return check(
            cid,
            "warn",
            f"{label}: p95={p95:.2f}s max={mx:.2f}s (approaching SLO)",
        )
    return check(cid, "pass", f"{label}: p95={p95:.2f}s max={mx:.2f}s")
