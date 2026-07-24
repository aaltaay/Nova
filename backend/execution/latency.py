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


def _delta_ms(end_ns: int | None, start_ns: int | None) -> float | None:
    if end_ns is None or start_ns is None or end_ns < start_ns:
        return None
    return (end_ns - start_ns) / 1_000_000


def _stats(values: list[float]) -> dict[str, float | int | None]:
    return {
        "count": len(values),
        "p50": _pct(values, 50),
        "p95": _pct(values, 95),
        "max": max(values) if values else None,
    }


def latency_summary(
    limit: int = 500,
    *,
    idempotency_prefix: str | None = None,
) -> dict[str, Any]:
    rows = store.latency_rows(
        limit=limit,
        idempotency_prefix=idempotency_prefix,
    )
    ack_ms: list[float] = []
    sent_ms: list[float] = []
    val_ms: list[float] = []
    send_to_fill_ms: list[float] = []
    ack_to_fill_ms: list[float] = []
    for r in rows:
        recv = r.get("received_ns")
        if not recv:
            continue
        validation = _delta_ms(r.get("validation_completed_ns"), recv)
        sent = _delta_ms(r.get("broker_sent_ns"), recv)
        ack = _delta_ms(r.get("broker_ack_ns"), recv)
        send_fill = _delta_ms(r.get("filled_ns"), r.get("broker_sent_ns"))
        ack_fill = _delta_ms(r.get("filled_ns"), r.get("broker_ack_ns"))
        if validation is not None:
            val_ms.append(validation)
        if sent is not None:
            sent_ms.append(sent)
        if ack is not None:
            ack_ms.append(ack)
        if send_fill is not None:
            send_to_fill_ms.append(send_fill)
        if ack_fill is not None:
            ack_to_fill_ms.append(ack_fill)

    ack_p95 = _pct(ack_ms, 95)
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
        "fill_ms": {
            "send_to_fill": _stats(send_to_fill_ms),
            "ack_to_fill": _stats(ack_to_fill_ms),
        },
        "sla_p95_ms": EXECUTION_ACK_SLA_P95_MS,
        "sla_pass": (
            ack_p95 is not None
            and ack_p95 <= EXECUTION_ACK_SLA_P95_MS
        ),
    }
