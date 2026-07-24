"""Low-cardinality FastAPI/ASGI request timing."""
from __future__ import annotations

import time
from typing import Any

from metrics.op_metrics import record_since


def operation_name(scope: dict[str, Any]) -> str:
    """Use the matched route template; never emit raw symbol/id paths."""
    method = str(scope.get("method") or "UNKNOWN").upper()
    route = scope.get("route")
    template = getattr(route, "path", None) or "unmatched"
    return f"http.{method}.{template}"


class HttpOperationMetricsMiddleware:
    """Measure the complete HTTP response lifecycle, including failures."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        started_ns = time.perf_counter_ns()
        state = scope.setdefault("state", {})
        state["backend_ingress_perf_ns"] = started_ns
        state["backend_ingress_wall_ns"] = time.time_ns()
        status_code = 500
        response_started = False

        async def send_with_status(message) -> None:
            nonlocal response_started, status_code
            if message.get("type") == "http.response.start":
                response_started = True
                status_code = int(message.get("status") or 500)
            await send(message)

        try:
            await self.app(scope, receive, send_with_status)
        except BaseException:
            record_since(operation_name(scope), started_ns, ok=False)
            raise
        else:
            ok = response_started and status_code < 400
            record_since(operation_name(scope), started_ns, ok=ok)
