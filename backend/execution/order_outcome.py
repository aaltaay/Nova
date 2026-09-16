"""Pure IBKR order-outcome reducer -- one stream, one honest outcome.

Filled qty / avg / filled_at come only from execDetails events. Soft warnings
(2109 and peers) never open a reject modal. The modal uses the latest hard
error (Error 201). Limit / aux / ValidationError prices are never fills.

Owner: execution.order_outcome. No IB socket, no ledger IO.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Literal, Mapping

from constants import IBKR_SOFT_ORDER_WARNING_CODES

Verdict = Literal["working", "filled", "rejected", "cancelled"]

_WORKING = frozenset({
    "PendingSubmit",
    "PreSubmitted",
    "Submitted",
    "ApiPending",
})
_CANCELLED = frozenset({"Cancelled", "Canceled", "ApiCancelled"})
_FILLED = frozenset({"Filled"})
_REJECT_STATUS = frozenset({"Inactive", "OrderRejected"})


def is_soft_warning(code: int | None) -> bool:
    try:
        return int(code or 0) in IBKR_SOFT_ORDER_WARNING_CODES
    except (TypeError, ValueError):
        return False


def latest_hard_error(
    errors: Iterable[tuple[int, str]],
) -> tuple[int | None, str | None]:
    """Latest hard error wins. Soft warnings never latch."""
    hard_code: int | None = None
    hard_msg: str | None = None
    for raw_code, raw_msg in errors:
        try:
            code = int(raw_code)
        except (TypeError, ValueError):
            continue
        if is_soft_warning(code):
            continue
        hard_code = code
        hard_msg = str(raw_msg or "").strip() or None
    return hard_code, hard_msg


@dataclass(frozen=True)
class OrderOutcome:
    verdict: Verdict
    ib_status: str | None
    filled_qty: float
    avg_fill_price: float | None
    filled_at: str | None
    hard_error_code: int | None
    hard_error_message: str | None
    open_reject_modal: bool
    commission: float | None
    status_history: tuple[str, ...]

    @property
    def display_failed(self) -> bool:
        return self.verdict == "rejected"


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _fills_from_events(events: Iterable[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return [ev for ev in events if str(ev.get("kind") or "") == "exec"]


def fills_only_qty_avg_at(
    events: Iterable[Mapping[str, Any]],
) -> tuple[float, float | None, str | None]:
    """Qty / VWAP / last fill clock from execDetails only."""
    fills = _fills_from_events(events)
    qty = 0.0
    notional = 0.0
    last_time: str | None = None
    for fill in fills:
        shares = _as_float(fill.get("shares")) or 0.0
        price = _as_float(fill.get("price"))
        if shares <= 0 or price is None or price <= 0:
            continue
        qty += shares
        notional += shares * price
        stamp = fill.get("time")
        if stamp:
            last_time = str(stamp)
    if qty <= 0:
        return 0.0, None, None
    return qty, notional / qty, last_time


def _commission_from_events(events: Iterable[Mapping[str, Any]]) -> float | None:
    total = 0.0
    found = False
    for ev in events:
        if str(ev.get("kind") or "") != "commission":
            continue
        value = _as_float(ev.get("commission"))
        if value is None:
            continue
        total += value
        found = True
    return total if found else None


def reduce_order_events(
    events: Iterable[Mapping[str, Any]],
    *,
    limit_price: float | None = None,
    stop_price: float | None = None,
) -> OrderOutcome:
    """Fold an IBKR event list into one outcome. Order of events is the tape."""
    evs = list(events)
    statuses: list[str] = []
    errors: list[tuple[int, str]] = []
    for ev in evs:
        kind = str(ev.get("kind") or "")
        if kind == "status":
            status = str(ev.get("status") or "").strip()
            if status:
                statuses.append(status)
        elif kind == "error":
            try:
                code = int(ev.get("code"))
            except (TypeError, ValueError):
                continue
            errors.append((code, str(ev.get("message") or "")))

    filled_qty, avg_fill, filled_at = fills_only_qty_avg_at(evs)
    # Limit / aux are never a fill price -- belt if a fixture leaked them.
    if avg_fill is not None:
        for decoy in (limit_price, stop_price):
            if decoy is None:
                continue
            try:
                if abs(float(decoy) - avg_fill) < 1e-12 and filled_qty <= 0:
                    avg_fill = None
            except (TypeError, ValueError):
                continue

    hard_code, hard_msg = latest_hard_error(errors)
    last = statuses[-1] if statuses else None
    returned_to_working = (
        any(s in _FILLED or s in _REJECT_STATUS for s in statuses[:-1])
        and last in _WORKING
    )

    if filled_qty > 0 and last in _FILLED:
        verdict: Verdict = "filled"
    elif last in _CANCELLED and filled_qty <= 0:
        verdict = "rejected" if hard_code is not None else "cancelled"
    elif last in _REJECT_STATUS:
        verdict = "rejected"
    elif returned_to_working:
        verdict = "working"
    elif last in _WORKING or last is None:
        verdict = "working"
    elif last in _FILLED and filled_qty <= 0:
        # Status Filled without execDetails is not a fill.
        verdict = "working"
    else:
        verdict = "working"

    open_modal = verdict == "rejected" and hard_code is not None
    return OrderOutcome(
        verdict=verdict,
        ib_status=last,
        filled_qty=filled_qty,
        avg_fill_price=avg_fill,
        filled_at=filled_at,
        hard_error_code=hard_code,
        hard_error_message=hard_msg,
        open_reject_modal=open_modal,
        commission=_commission_from_events(evs),
        status_history=tuple(statuses),
    )


def assert_outcome_honest(outcome: OrderOutcome) -> None:
    """CI tripwire: Failed+Filled and 2109-as-reject must never appear."""
    if outcome.display_failed and outcome.filled_qty > 0:
        raise AssertionError(
            f"Failed+Filled lie: verdict={outcome.verdict} "
            f"filled_qty={outcome.filled_qty} status={outcome.ib_status}"
        )
    if outcome.open_reject_modal and is_soft_warning(outcome.hard_error_code):
        raise AssertionError(
            f"reject modal on soft warning {outcome.hard_error_code}"
        )
    if outcome.open_reject_modal and outcome.hard_error_code is None:
        raise AssertionError("reject modal without a hard error")
    if outcome.filled_qty <= 0:
        if outcome.avg_fill_price is not None:
            raise AssertionError("avg fill without execDetails")
        if outcome.filled_at is not None:
            raise AssertionError("filled_at without execDetails")
    soft_only = (
        outcome.hard_error_code is None
        and not outcome.open_reject_modal
    )
    if not soft_only and outcome.hard_error_code is None and outcome.verdict == "rejected":
        # Inactive with no hard error is a failed row, but must not say "2109 rejected".
        pass
