"""Latency rollups over the execution ledger (ADR 007)."""
from __future__ import annotations

from typing import Any

from constants import EXECUTION_ACK_SLA_P95_MS
from execution import store


def _pct(vals: list[float], p: float) -> float | None:
    if not vals:
        return None
    s = sorted(vals)
    idx = min(len(s) - 1, max(0, int(round((p / 100.0) * (len(s) - 1)))))
    return s[idx]


def latency_summary(limit: int = 500) -> dict[str, Any]:
    rows = store.latency_rows(limit=limit)
    ack_ms: list[float] = []
    sent_ms: list[float] = []
    val_ms: list[float] = []
    for r in rows:
        recv = r.get("received_ns")
        if not recv:
            continue
        if r.get("validation_completed_ns"):
            val_ms.append((r["validation_completed_ns"] - recv) / 1e6)
        if r.get("broker_sent_ns"):
            sent_ms.append((r["broker_sent_ns"] - recv) / 1e6)
        if r.get("broker_ack_ns"):
            ack_ms.append((r["broker_ack_ns"] - recv) / 1e6)

    return {
        "sample_count": len(rows),
        "ack_count": len(ack_ms),
        "validation_ms": {
            "p50": _pct(val_ms, 50),
            "p95": _pct(val_ms, 95),
            "max": max(val_ms) if val_ms else None,
        },
        "broker_sent_ms": {
            "p50": _pct(sent_ms, 50),
            "p95": _pct(sent_ms, 95),
            "max": max(sent_ms) if sent_ms else None,
        },
        "broker_ack_ms": {
            "p50": _pct(ack_ms, 50),
            "p95": _pct(ack_ms, 95),
            "max": max(ack_ms) if ack_ms else None,
        },
        "sla_p95_ms": EXECUTION_ACK_SLA_P95_MS,
        "sla_pass": (
            _pct(ack_ms, 95) is not None
            and _pct(ack_ms, 95) <= EXECUTION_ACK_SLA_P95_MS
        ),
    }
