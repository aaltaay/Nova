"""Persist fill evidence from existing cached reconciliation rows."""
from __future__ import annotations

from typing import Any, Protocol


class ReconciliationWatch(Protocol):
    execution_id: str | None
    leg_role: str
    side: str | None
    reference_price: float | None
    reference_source: str | None
    aggregate_eligible: bool
    _reconciled_fill_keys: set[tuple[str, str, str]]


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def record_reconciliation_fill(
    fill: Any,
    watch: ReconciliationWatch,
    *,
    complete: bool,
) -> bool:
    """Record one deduplicated cached fill without issuing a broker request."""
    execution = getattr(fill, "execution", None)
    order_id = int(getattr(execution, "orderId", 0) or 0)
    if order_id <= 0 or watch.execution_id is None:
        return False
    key = (
        str(getattr(execution, "time", None)),
        str(getattr(execution, "shares", None)),
        str(getattr(execution, "avgPrice", None)),
    )
    if key in watch._reconciled_fill_keys:
        return False
    watch._reconciled_fill_keys.add(key)

    from execution import evidence_store

    return evidence_store.record_fill(
        execution_id=watch.execution_id,
        order_id=order_id,
        provenance="reconciliation_poll",
        complete=complete,
        exchange_time=getattr(execution, "time", None),
        price=_float_or_none(getattr(execution, "price", None)),
        shares=_float_or_none(getattr(execution, "shares", None)),
        cumulative_shares=_float_or_none(getattr(execution, "cumQty", None)),
        average_fill_price=_float_or_none(getattr(execution, "avgPrice", None)),
        broker_status="reconciled",
        leg_role=watch.leg_role,
        side=watch.side,
        reference_price=watch.reference_price,
        reference_source=watch.reference_source,
        aggregate_eligible=watch.aggregate_eligible,
    )
