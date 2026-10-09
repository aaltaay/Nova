"""Pure IBKR order-outcome reducer -- one stream, one honest outcome.

Filled qty / avg / filled_at come only from execDetails events. Soft warnings
(2109 and peers) never open a reject modal. The modal uses the latest hard
error (Error 201). Limit / aux / ValidationError prices are never fills.
``ledger_close`` maps a venue's closed status to the execution row's terminal
fields, so a cancelled order reads ``cancelled``, never ``failed``.

Owner: execution.order_outcome. No IB socket, no ledger IO.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Literal, Mapping

from constants import (
    IBKR_ERROR_CANCEL_ALREADY_CLOSED,
    IBKR_ERROR_NO_OPENING_TRADES,
    IBKR_OCA_CLOSED_MARKERS,
    IBKR_SOFT_ORDER_WARNING_CODES,
)
from constants_practice import (
    PRACTICE_OCO_CANCELLED_CODE,
    PRACTICE_ORDER_STATUS_EXPIRED,
    PRACTICE_PARENT_CANCELLED_CODE,
    PRACTICE_TIF_EXPIRED_CODE,
)

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


def is_closure_notice(code: int | None, message: str | None) -> bool:
    """IBKR saying the order is already closed, not refusing it (a cancel, never a reject).

    10148 answers a cancel of an order that had already filled or been cancelled; 201 that names
    the OCA group is a one-cancels-all sibling closed because another member filled.
    """
    try:
        number = int(code or 0)
    except (TypeError, ValueError):
        return False
    if number == IBKR_ERROR_CANCEL_ALREADY_CLOSED:
        return True
    text = str(message or "").lower()
    return number == IBKR_ERROR_NO_OPENING_TRADES and any(m in text for m in IBKR_OCA_CLOSED_MARKERS)


def closed_state(errors: Iterable[tuple[int, str]]) -> str | None:
    """The state a 10148 names ("Filled", "Cancelled"...), the latest one; None when none was heard."""
    state: str | None = None
    for raw_code, raw_msg in errors:
        try:
            code = int(raw_code)
        except (TypeError, ValueError):
            continue
        text = str(raw_msg or "")
        if code == IBKR_ERROR_CANCEL_ALREADY_CLOSED and "state:" in text.lower():
            state = text[text.lower().rindex("state:") + len("state:"):].strip().rstrip(".").strip() or None
    return state


def latest_hard_error(
    errors: Iterable[tuple[int, str]],
) -> tuple[int | None, str | None]:
    """Latest hard error wins. Soft warnings and closure notices never latch."""
    hard_code: int | None = None
    hard_msg: str | None = None
    for raw_code, raw_msg in errors:
        try:
            code = int(raw_code)
        except (TypeError, ValueError):
            continue
        if is_soft_warning(code) or is_closure_notice(code, raw_msg):
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


_NO_STATUS_FILL = frozenset({"Inactive", "OrderRejected"})


def honest_broker_fill_qty(
    *,
    ib_status: str | None,
    exec_filled_qty: float,
    status_filled_qty: float | None,
    requested_qty: float | None,
) -> tuple[float, bool]:
    """Row-mapping fill size. Live streams still use execDetails only.

    1. execDetails shares win.
    2. ``orderStatus.filled`` is real on Filled / working / cancelled.
    3. Warm ``reqCompletedOrders`` Filled with filled=0 uses requested size.
    4. Inactive / OrderRejected never borrow status.filled or requested size
       (ZTG #116071: limit copied into filled / avgFillPrice).
    """
    if exec_filled_qty > 0:
        return float(exec_filled_qty), False
    status = str(ib_status or "")
    if status in _NO_STATUS_FILL:
        return 0.0, False
    tracked = _as_float(status_filled_qty) or 0.0
    if tracked > 0:
        return tracked, False
    if status == "Filled":
        qty = _as_float(requested_qty)
        if qty is not None and qty > 0:
            return qty, True
    return 0.0, False


def warm_completed_fill_qty(
    *,
    ib_status: str | None,
    exec_filled_qty: float,
    requested_qty: float | None,
) -> float:
    qty, _ = honest_broker_fill_qty(
        ib_status=ib_status,
        exec_filled_qty=exec_filled_qty,
        status_filled_qty=0.0,
        requested_qty=requested_qty,
    )
    return qty


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


#: Closed unfilled, and not a refusal: a cancel (Nova's, the operator's, KILL's), a DAY
#: order's expiry, or a bracket's own closures (one-cancels-other, an entry's exits).
_LEDGER_CANCELLED = _CANCELLED | {PRACTICE_ORDER_STATUS_EXPIRED}
_NOT_A_REFUSAL = frozenset({
    PRACTICE_TIF_EXPIRED_CODE, PRACTICE_OCO_CANCELLED_CODE, PRACTICE_PARENT_CANCELLED_CODE,
})


def ledger_close(
    broker_status: str | None, *, reason_code: str | None = None, error: str | None = None,
) -> dict[str, str | None] | None:
    """The execution ledger's terminal fields for an order its venue closed; None while it works.

    ``filled`` for a fill; ``cancelled`` for an order closed unfilled by a cancel,
    its TIF or its bracket; ``failed`` for any other close -- a venue's refusal
    (a practice order cancelled at the fill, ``PRACTICE_BUYING_POWER``) or
    ``Inactive`` -- in the venue's own words when it gave them.
    """
    status = str(broker_status or "")
    code = str(reason_code or "") or None
    if status in _FILLED:
        return {"status": "filled", "broker_status": status, "reason_code": None, "error": None}
    if status in _LEDGER_CANCELLED and (code is None or code in _NOT_A_REFUSAL):
        return {"status": "cancelled", "broker_status": status, "reason_code": code, "error": None}
    if status in _LEDGER_CANCELLED or status in _REJECT_STATUS:
        return {
            "status": "failed", "broker_status": status, "reason_code": code,
            "error": error or f"The venue closed the order ({status})",
        }
    return None


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
