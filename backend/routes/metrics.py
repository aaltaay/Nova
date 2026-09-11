"""Read-only operation metrics routes."""
from __future__ import annotations

from fastapi import APIRouter

from metrics.op_metrics import snapshot

router = APIRouter(prefix="/api/metrics", tags=["metrics"])


@router.get("/ops")
async def operation_metrics() -> dict:
    from execution.latency import latency_summary
    from ibkr.historical_service import pacing_snapshot

    from process_maps import snapshot as map_sizes

    return {
        **snapshot(),
        "execution": latency_summary(),
        "historical_pacing": pacing_snapshot(),
        "maps": map_sizes(),
    }
