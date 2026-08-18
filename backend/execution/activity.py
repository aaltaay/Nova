"""Shape ADR 007 ledger rows for the read-only Activity trail."""
from __future__ import annotations

from constants import EXECUTION_ACTIVITY_DEFAULT_LIMIT, EXECUTION_METRICS_QUERY_LIMIT
from execution.models import StageTimings
from execution.store import list_recent


def _as_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _timings(row: dict) -> dict[str, float | None]:
    received = row.get("received_ns")
    try:
        received_ns = int(received) if received is not None else 0
    except (TypeError, ValueError):
        received_ns = 0
    stages = StageTimings(
        received_ns=received_ns,
        validation_completed_ns=row.get("validation_completed_ns"),
        persisted_ns=row.get("persisted_ns"),
        broker_sent_ns=row.get("broker_sent_ns"),
        broker_ack_ns=row.get("broker_ack_ns"),
        filled_ns=row.get("filled_ns"),
    )
    return stages.to_dict()


def shape_activity_row(row: dict) -> dict:
    payload = row.get("payload") or {}
    return {
        "id": row.get("id"),
        "created_ts": row.get("created_ts"),
        "updated_ts": row.get("updated_ts"),
        "operation": row.get("operation"),
        "source": row.get("source"),
        "symbol": str(row.get("symbol") or "").upper() or None,
        "side": str(payload.get("side") or "").upper() or None,
        "requested_qty": _as_float(payload.get("requested_qty")),
        "sent_qty": _as_float(payload.get("sent_qty") if payload.get("sent_qty") is not None else payload.get("qty")),
        "forced_one_share": bool(payload.get("forced_one_share")),
        "orders_enabled": payload.get("orders_enabled"),
        "live_trading_confirmed": payload.get("live_trading_confirmed"),
        "short_enabled": payload.get("short_enabled"),
        "short_entry": bool(payload.get("short_entry")),
        "gateway_mode": payload.get("gateway_mode"),
        "order_id": row.get("order_id"),
        "perm_id": row.get("perm_id"),
        "filled_qty": row.get("filled_qty"),
        "avg_fill_price": row.get("avg_fill_price"),
        "status": row.get("status"),
        "broker_status": row.get("broker_status"),
        "reason_code": row.get("reason_code"),
        "error": row.get("error"),
        "mode": row.get("mode"),
        "timings": _timings(row),
    }


def recent_activity(
    *,
    limit: int = EXECUTION_ACTIVITY_DEFAULT_LIMIT,
    symbol: str | None = None,
) -> list[dict]:
    cap = max(1, min(int(limit), EXECUTION_METRICS_QUERY_LIMIT))
    needle = (symbol or "").strip().upper()
    fetch = cap if not needle else min(EXECUTION_METRICS_QUERY_LIMIT, max(cap * 4, 50))
    rows = [shape_activity_row(row) for row in list_recent(fetch)]
    if needle:
        rows = [row for row in rows if row.get("symbol") == needle]
    return rows[:cap]
