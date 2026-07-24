"""Clock-domain-safe browser/backend timing evidence."""
from __future__ import annotations

import math
import time
from typing import Any


BROWSER_CLOCK_SOURCE = "browser.performance_now"
BACKEND_CLOCK_SOURCE = "backend.perf_counter_ns"
WALL_CLOCK_SOURCE = "utc_unix_wall"


def _finite(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) and parsed >= 0 else None


def normalize_browser_timing(raw: dict[str, Any] | None) -> dict[str, Any] | None:
    """Validate the paired browser action/dispatch stamps without inventing data."""
    if not raw:
        return None
    action_wall = _finite(raw.get("action_wall_ms"))
    action_perf = _finite(raw.get("action_performance_ms"))
    dispatch_wall = _finite(raw.get("request_wall_ms"))
    dispatch_perf = _finite(raw.get("request_performance_ms"))
    if None in (action_wall, action_perf, dispatch_wall, dispatch_perf):
        return {
            "valid": False,
            "excluded_reason": "missing_or_invalid_paired_browser_stamps",
            "clock_domain": BROWSER_CLOCK_SOURCE,
        }
    action_to_dispatch = dispatch_perf - action_perf
    if action_to_dispatch < 0:
        return {
            "valid": False,
            "excluded_reason": "negative_browser_same_clock_delta",
            "clock_domain": BROWSER_CLOCK_SOURCE,
        }
    return {
        "valid": True,
        "clock_domain": BROWSER_CLOCK_SOURCE,
        "wall_clock": WALL_CLOCK_SOURCE,
        "action_wall_ms": action_wall,
        "action_performance_ms": action_perf,
        "request_wall_ms": dispatch_wall,
        "request_performance_ms": dispatch_perf,
        "action_to_request_ms": action_to_dispatch,
    }


def ingress_stamps(request: Any) -> tuple[int, int]:
    """Read stamps captured by the outer ASGI middleware, with a safe fallback."""
    state = getattr(request, "state", None)
    perf_ns = getattr(state, "backend_ingress_perf_ns", None)
    wall_ns = getattr(state, "backend_ingress_wall_ns", None)
    return (
        int(perf_ns) if perf_ns is not None else time.perf_counter_ns(),
        int(wall_ns) if wall_ns is not None else time.time_ns(),
    )


def initial_measurement(
    *,
    browser_timing: dict[str, Any] | None,
    backend_ingress_perf_ns: int,
    backend_ingress_wall_ns: int,
) -> dict[str, Any]:
    browser = normalize_browser_timing(browser_timing)
    measurement: dict[str, Any] = {
        "schema_version": 1,
        "backend": {
            "clock_domain": BACKEND_CLOCK_SOURCE,
            "wall_clock": WALL_CLOCK_SOURCE,
            "ingress_perf_ns": int(backend_ingress_perf_ns),
            "ingress_wall_ms": backend_ingress_wall_ns / 1_000_000,
        },
        "browser": browser,
        "cross_clock_arithmetic": "forbidden",
        "frontend_render": {
            "status": "not_measured_by_backend",
            "owner": "widgets",
        },
    }
    if browser and browser.get("valid"):
        wall_delta = (
            backend_ingress_wall_ns / 1_000_000
            - float(browser["request_wall_ms"])
        )
        measurement["browser_to_backend_wall_observation"] = {
            "delta_ms": wall_delta,
            "latency_usable": False,
            "includes": [
                "browser_backend_wall_clock_offset",
                "transport",
                "backend_ingress",
            ],
            "uncertainty": "wall clocks require external synchronization",
        }
    return measurement


def response_ready_measurement(measurement: dict[str, Any]) -> dict[str, Any]:
    """Add the backend handler response-ready mark in the backend clock domain."""
    ready_perf_ns = time.perf_counter_ns()
    ready_wall_ns = time.time_ns()
    backend = dict(measurement.get("backend") or {})
    ingress_perf_ns = backend.get("ingress_perf_ns")
    delta_ms = None
    if isinstance(ingress_perf_ns, int) and ready_perf_ns >= ingress_perf_ns:
        delta_ms = (ready_perf_ns - ingress_perf_ns) / 1_000_000
    backend.update({
        "response_ready_perf_ns": ready_perf_ns,
        "response_ready_wall_ms": ready_wall_ns / 1_000_000,
        "ingress_to_response_ready_ms": delta_ms,
        "response_mark": "handler_response_ready_not_socket_or_frontend_render",
    })
    return {**measurement, "backend": backend}
