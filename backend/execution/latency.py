"""Clock-safe, population-segregated execution latency rollups."""
from __future__ import annotations

from collections import Counter
from typing import Any, Callable

from constants import (
    EXECUTION_ACK_SLA_P95_MS,
    EXECUTION_METRICS_MIN_PERCENTILE_SAMPLES,
    EXECUTION_METRICS_QUERY_LIMIT,
)
from execution import evidence_store, store


def _pct(values: list[float], percentile: int) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, int((percentile / 100) * len(ordered) + 0.999999))
    return ordered[min(rank, len(ordered)) - 1]


def _stats(
    values: list[float],
    *,
    error_count: int = 0,
    excluded: Counter | None = None,
) -> dict[str, Any]:
    return {
        "count": len(values),
        "error_count": error_count,
        "p50": _pct(values, 50),
        "p95": _pct(values, 95),
        "p99": _pct(values, 99),
        "max": max(values) if values else None,
        "sufficient": len(values) >= EXECUTION_METRICS_MIN_PERCENTILE_SAMPLES,
        "minimum_samples": EXECUTION_METRICS_MIN_PERCENTILE_SAMPLES,
        "excluded_count": sum((excluded or {}).values()),
        "excluded_reasons": dict(sorted((excluded or {}).items())),
    }


def _collect_delta(
    rows: list[dict],
    end: str,
    start: str,
) -> tuple[list[float], Counter]:
    values: list[float] = []
    excluded: Counter = Counter()
    for row in rows:
        end_ns = row.get(end)
        start_ns = row.get(start)
        if end_ns is None or start_ns is None:
            excluded[f"missing_{end if end_ns is None else start}"] += 1
        elif end_ns < start_ns:
            excluded[f"negative_{end}_minus_{start}"] += 1
        else:
            values.append((end_ns - start_ns) / 1_000_000)
    return values, excluded


def _measurement_delta(row: dict) -> tuple[float | None, str | None]:
    measurement = (row.get("payload") or {}).get("measurement") or {}
    backend = measurement.get("backend") or {}
    value = backend.get("ingress_to_response_ready_ms")
    if value is None:
        return None, "missing_handler_response_ready"
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None, "invalid_handler_response_ready"
    return (
        (parsed, None)
        if parsed >= 0
        else (None, "negative_handler_response_ready")
    )


def _fill_delta(
    rows: list[dict],
    evidence: list[dict],
    *,
    complete: bool,
    start_field: str,
) -> tuple[list[float], Counter]:
    grouped: dict[str, list[int]] = {}
    for item in evidence:
        if not bool(item.get("aggregate_eligible", 1)):
            continue
        if complete and item["fill_state"] != "complete":
            continue
        grouped.setdefault(str(item["execution_id"]), []).append(
            int(item["callback_perf_ns"])
        )
    values: list[float] = []
    excluded: Counter = Counter()
    for row in rows:
        execution_id = str(row["id"])
        marks = grouped.get(execution_id)
        start_ns = row.get(start_field)
        if not marks and row.get("filled_ns") is not None:
            marks = [int(row["filled_ns"])]
        if not marks:
            excluded["missing_complete_fill" if complete else "missing_first_fill"] += 1
        elif start_ns is None:
            excluded[f"missing_{start_field}"] += 1
        else:
            mark = min(marks)
            if mark < start_ns:
                excluded["negative_fill_delta"] += 1
            else:
                values.append((mark - start_ns) / 1_000_000)
    return values, excluded


def _summary(rows: list[dict], evidence: list[dict]) -> dict[str, Any]:
    errors = sum(row.get("status") in ("failed", "rejected") for row in rows)
    distributions: dict[str, dict] = {}
    for name, end, start in (
        ("validation", "validation_completed_ns", "received_ns"),
        ("persistence", "persisted_ns", "received_ns"),
        ("broker_send", "broker_sent_ns", "received_ns"),
        ("broker_ack", "broker_ack_ns", "received_ns"),
    ):
        values, excluded = _collect_delta(rows, end, start)
        distributions[f"{name}_ms"] = _stats(
            values, error_count=errors, excluded=excluded,
        )
    for name, complete, start in (
        ("receive_to_first_fill", False, "received_ns"),
        ("send_to_first_fill", False, "broker_sent_ns"),
        ("ack_to_first_fill", False, "broker_ack_ns"),
        ("receive_to_complete_fill", True, "received_ns"),
        ("send_to_complete_fill", True, "broker_sent_ns"),
        ("ack_to_complete_fill", True, "broker_ack_ns"),
    ):
        values, excluded = _fill_delta(
            rows, evidence, complete=complete, start_field=start,
        )
        distributions[f"{name}_ms"] = _stats(
            values, error_count=errors, excluded=excluded,
        )
    response_values: list[float] = []
    response_excluded: Counter = Counter()
    for row in rows:
        value, reason = _measurement_delta(row)
        if reason:
            response_excluded[reason] += 1
        elif value is not None:
            response_values.append(value)
    distributions["backend_response_ready_ms"] = _stats(
        response_values, error_count=errors, excluded=response_excluded,
    )
    return {
        "sample_count": len(rows),
        "error_count": errors,
        "distributions": distributions,
    }


def _segments(
    rows: list[dict],
    evidence: list[dict],
    field: str,
    normalize: Callable[[Any], str] = lambda value: str(value or "unknown"),
) -> dict[str, dict]:
    result: dict[str, dict] = {}
    for value in sorted({normalize(row.get(field)) for row in rows}):
        selected = [row for row in rows if normalize(row.get(field)) == value]
        selected_ids = {row["id"] for row in selected}
        result[value[:64]] = _summary(
            selected,
            [item for item in evidence if item["execution_id"] in selected_ids],
        )
    return result


def _fill_leg_segments(evidence: list[dict]) -> dict[str, dict]:
    result: dict[str, dict] = {}
    for role in sorted({str(item.get("leg_role") or "legacy_unknown") for item in evidence}):
        selected = [
            item for item in evidence
            if str(item.get("leg_role") or "legacy_unknown") == role
        ]
        callback_values = [
            (item["callback_perf_ns"] - item["broker_sent_ns"]) / 1_000_000
            for item in selected
            if item.get("broker_sent_ns") is not None
            and item["callback_perf_ns"] >= item["broker_sent_ns"]
        ]
        slippage_values = [
            float(item["slippage_bps"])
            for item in selected if item.get("slippage_bps") is not None
        ]
        result[role[:32]] = {
            "evidence_count": len(selected),
            "aggregate_eligible_count": sum(
                bool(item.get("aggregate_eligible", 1)) for item in selected
            ),
            "callback_from_send_ms": _stats(callback_values),
            "slippage_bps": _stats(slippage_values),
        }
    return result


def latency_summary(
    limit: int = EXECUTION_METRICS_QUERY_LIMIT,
    *,
    idempotency_prefix: str | None = None,
) -> dict[str, Any]:
    cap = max(1, min(int(limit), EXECUTION_METRICS_QUERY_LIMIT))
    population = store.list_recent(limit=cap)
    if idempotency_prefix is not None:
        population = [
            row for row in population
            if str(row.get("idempotency_key") or "").startswith(idempotency_prefix)
        ]
    exclusions: Counter = Counter()
    rows: list[dict] = []
    for row in population:
        if not row.get("boot_id"):
            exclusions["legacy_missing_boot_id"] += 1
        elif row["boot_id"] != store.current_boot_id():
            exclusions["cross_boot"] += 1
        elif row.get("broker_sent_ns") is None:
            exclusions["did_not_reach_broker_send"] += 1
        else:
            key = str(row.get("idempotency_key") or "")
            if row.get("source") == "benchmark" and key.startswith("bench:synth:"):
                row["_population"] = "benchmark_synthetic"
            elif (
                row.get("source") == "benchmark"
                and key.startswith("bench:paper:")
                and row.get("mode") == "paper"
            ):
                row["_population"] = "benchmark_paper"
            elif row.get("source") == "benchmark":
                row["_population"] = "benchmark_unknown"
            else:
                row["_population"] = str(row.get("mode") or "unknown")
            rows.append(row)
    evidence = evidence_store.latency_rows([row["id"] for row in rows])
    aggregate = _summary(rows, evidence)
    distributions = aggregate["distributions"]
    populations = {str(row.get("_population") or "unknown") for row in rows}
    mixed = len(populations) > 1
    ack = distributions["broker_ack_ms"]
    provenance: dict[str, dict] = {}
    for name in sorted(evidence_store.PROVENANCES):
        selected_all = [item for item in evidence if item["provenance"] == name]
        selected = [
            item for item in selected_all
            if bool(item.get("aggregate_eligible", 1))
        ]
        child_excluded = len(selected_all) - len(selected)
        callback_values = [
            (item["callback_perf_ns"] - item["broker_sent_ns"]) / 1_000_000
            for item in selected
            if item.get("broker_sent_ns") is not None
            and item["callback_perf_ns"] >= item["broker_sent_ns"]
        ]
        exchange_values = [
            float(item["exchange_to_callback_ms"])
            for item in selected
            if item.get("exchange_to_callback_ms") is not None
        ]
        exchange_excluded = Counter(
            str(item["exchange_delay_excluded_reason"])
            for item in selected
            if item.get("exchange_delay_excluded_reason")
        )
        provenance[name] = {
            "callback_from_send_ms": _stats(
                callback_values,
                excluded=(
                    Counter({"child_leg_not_parent_aggregate": child_excluded})
                    if child_excluded else Counter()
                ),
            ),
            "exchange_to_callback_ms": _stats(
                exchange_values, excluded=exchange_excluded,
            ),
            "exchange_clock_note": (
                "wall-clock observation; meaningful only with synchronized "
                "IBKR/API host clocks"
            ),
        }
    evidence_ids = {
        str(item["execution_id"]) for item in evidence
        if bool(item.get("aggregate_eligible", 1))
    }
    stage_only = [
        row for row in rows
        if row.get("filled_ns") is not None and str(row["id"]) not in evidence_ids
    ]
    stage_values, stage_excluded = _collect_delta(
        stage_only, "filled_ns", "broker_sent_ns",
    )
    provenance["legacy_stage"] = {
        "callback_from_send_ms": _stats(
            stage_values, excluded=stage_excluded,
        ),
        "exchange_to_callback_ms": _stats(
            [], excluded=Counter({"exchange_timestamp_missing": len(stage_only)}),
        ),
        "exchange_clock_note": (
            "same-boot complete-fill stage only; callback source unavailable"
        ),
    }
    population_segments = _segments(rows, evidence, "_population")
    for segment in population_segments.values():
        segment_ack = segment["distributions"]["broker_ack_ms"]
        sufficient = bool(segment_ack["sufficient"])
        segment["sla"] = {
            "target_p95_ms": EXECUTION_ACK_SLA_P95_MS,
            "p95_ms": segment_ack["p95"],
            "pass": (
                sufficient
                and segment_ack["p95"] is not None
                and segment_ack["p95"] <= EXECUTION_ACK_SLA_P95_MS
            ) if sufficient else None,
            "status": (
                "pass"
                if sufficient and segment_ack["p95"] <= EXECUTION_ACK_SLA_P95_MS
                else "fail" if sufficient else "insufficient_samples"
            ),
            "evidence_sufficient": sufficient,
        }
    aggregate_sla_pass = (
        None
        if mixed or not ack["sufficient"]
        else ack["p95"] is not None and ack["p95"] <= EXECUTION_ACK_SLA_P95_MS
    )
    return {
        "clock_contract": {
            "backend": "perf_counter_ns_same_boot_only",
            "browser": "performance.now_same_document_only",
            "wall": "UTC observation; clock offset plus transport, not latency",
            "cross_clock_arithmetic": "forbidden",
        },
        "bounded_limit": cap,
        "population_count": len(population),
        "sample_count": aggregate["sample_count"],
        "ack_count": ack["count"],
        "error_count": aggregate["error_count"],
        "excluded_count": sum(exclusions.values()),
        "excluded_reasons": dict(sorted(exclusions.items())),
        "normalized_populations": sorted(populations),
        "mixed_population": mixed,
        "aggregate_scope": (
            "mixed_diagnostic_only" if mixed
            else next(iter(populations), "empty")
        ),
        "aggregate_warning": (
            "aggregate percentiles mix normalized populations; use segments.population"
            if mixed else None
        ),
        "distributions": distributions,
        "segments": {
            "population": population_segments,
            "mode": _segments(rows, evidence, "mode"),
            "operation": _segments(rows, evidence, "operation"),
            "source": _segments(rows, evidence, "source"),
            "fill_provenance": provenance,
            "fill_leg": _fill_leg_segments(evidence),
        },
        # Compatibility fields remain explicitly backed by the labeled aggregate.
        "validation_ms": distributions["validation_ms"],
        "broker_sent_ms": distributions["broker_send_ms"],
        "broker_ack_ms": distributions["broker_ack_ms"],
        "fill_ms": {
            "send_to_fill": distributions["send_to_complete_fill_ms"],
            "ack_to_fill": distributions["ack_to_complete_fill_ms"],
        },
        "sla_p95_ms": EXECUTION_ACK_SLA_P95_MS,
        "sla_pass": aggregate_sla_pass,
        "sla_status": (
            "suppressed_mixed_population"
            if mixed
            else "single_population"
            if ack["sufficient"]
            else "insufficient_samples"
        ),
        "sla_evidence_sufficient": ack["sufficient"] and not mixed,
    }
