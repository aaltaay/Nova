"""Join fill-audit latency onto order rows for Orders Today (#195).

Owner: execution.fill_audit_attach.
Invalidation: process-lifetime store + session ledger nova_placed_at / created_ts.
schema_version: 1 -- public payload is a subset of fill_audit SCHEMA_VERSION.

Never invent milliseconds. Collapsed ledger clocks (place == fill) stay blank.
"""
from __future__ import annotations

import logging
from typing import Any

from constants_ibkr import (
    IBKR_CLOSED_ORDER_STATUSES,
    FILL_AUDIT_FAST_TYPES,
    FILL_AUDIT_MKT_RTH_DANGER_MS,
    FILL_AUDIT_MKT_RTH_WARN_MS,
    FILL_AUDIT_REASON_CLOCK_SKEW,
    FILL_AUDIT_REASON_IMPOSSIBLE,
    FILL_AUDIT_REASON_TIMEZONE_SHAPED,
)
from execution.fill_audit import (
    classify_fill_audit,
    lookup_fill_audit,
)
from execution.fill_audit_clock import (
    apply_fill_clock_guard,
    clock_guard_level,
    coherent_face_ms,
    honest_filled_at_iso,
    is_clock_skew_ms,
    same_clock_instant,
)

_INVALID_CLOCK_REASONS = frozenset({
    FILL_AUDIT_REASON_IMPOSSIBLE,
    FILL_AUDIT_REASON_TIMEZONE_SHAPED,
    FILL_AUDIT_REASON_CLOCK_SKEW,
})

logger = logging.getLogger(__name__)


def _as_int(value: object) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


def _as_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_or_none(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def public_fill_audit(row: dict[str, Any] | None) -> dict[str, Any] | None:
    """UI payload, or None when there is no click-to-fill / click-to-terminal.

    Timezone-shaped leftovers (same-second submit + ~4h/5h fill) stay
    publishable so the cell can show an invalid clock, not a confident 4h ok.
    Negative whole-second skew stays publishable as clock_skew / ok so the
    hover can explain the disagreement without a -Nms face.
    """
    if not row:
        return None
    fill = _int_or_none(row.get("place_to_fill_ms"))
    terminal = _int_or_none(row.get("place_to_terminal_ms"))
    submit = _int_or_none(row.get("place_to_submit_ms"))
    reason = row.get("reason")
    level = row.get("level")
    guarded_fill, clock_reason = apply_fill_clock_guard(
        place_to_fill_ms=fill,
        place_to_submit_ms=submit,
        placed_iso=None,
        order_type=str(row.get("type") or "MKT"),
    )
    if clock_reason == FILL_AUDIT_REASON_CLOCK_SKEW:
        if guarded_fill is not None:
            fill = guarded_fill
        reason = clock_reason
        level = "ok"
    elif clock_reason:
        fill = None
        reason = clock_reason
        level = clock_guard_level(clock_reason)
    elif guarded_fill is not None:
        fill = guarded_fill
        typ = str(row.get("type") or "MKT").upper()
        if typ in FILL_AUDIT_FAST_TYPES and fill is not None and reason == "filled":
            if fill > FILL_AUDIT_MKT_RTH_DANGER_MS:
                level = "danger"
                reason = "mkt_rth_slow"
            elif fill > FILL_AUDIT_MKT_RTH_WARN_MS:
                level = "warn"
                reason = "mkt_rth_slow"
    if is_clock_skew_ms(fill) or is_clock_skew_ms(terminal):
        reason = FILL_AUDIT_REASON_CLOCK_SKEW
        level = "ok"
    if fill is None and terminal is None and reason not in _INVALID_CLOCK_REASONS:
        return None
    return {
        "place_to_submit_ms": submit,
        "place_to_fill_ms": fill,
        "place_to_terminal_ms": terminal,
        "face_ms": coherent_face_ms(fill, terminal, str(reason) if reason else None),
        "level": level,
        "reason": reason,
    }


def placed_index_from_ledger(ledger_rows: list[dict] | None) -> dict[tuple[str, int], str]:
    """Map (order|perm, id) -> nova_placed_at ISO (payload, else created_ts)."""
    from execution.nova_placed import ledger_placed_iso

    index: dict[tuple[str, int], str] = {}
    for led in ledger_rows or []:
        iso = ledger_placed_iso(led)
        if not iso:
            continue
        oid = _as_int(led.get("order_id"))
        perm = _as_int(led.get("perm_id"))
        if oid > 0:
            index[("order", oid)] = iso
        if perm > 0:
            index[("perm", perm)] = iso
    return index


def _has_real_fill(row: dict[str, Any]) -> bool:
    filled = _as_float(row.get("filled_qty")) or 0.0
    return filled > 0 and bool(row.get("filled_at"))


def _clocks_usable(
    placed: str,
    end: str | None,
) -> bool:
    """Refuse collapsed identical stamps -- those are not measured latency."""
    if not placed or not end:
        return False
    if placed == end:
        return False
    return not same_clock_instant(placed, end)


def resolve_fill_audit(
    row: dict[str, Any],
    placed_index: dict[tuple[str, int], str] | None = None,
) -> dict[str, Any] | None:
    """Build the public fill_audit object, or None when clocks are incomplete."""
    oid = _as_int(row.get("order_id"))
    perm = _as_int(row.get("perm_id"))
    stored, stored_placed = lookup_fill_audit(oid or None, perm or None)
    idx = placed_index or {}
    placed = (
        stored_placed
        or idx.get(("order", oid) if oid > 0 else ("order", 0))
        or idx.get(("perm", perm) if perm > 0 else ("perm", 0))
    )
    has_fill = _has_real_fill(row)
    status = str(row.get("status") or "")
    terminal = status in IBKR_CLOSED_ORDER_STATUSES
    submitted = str(row.get("submitted_at") or "") or None
    filled_at = str(row.get("filled_at") or "") if has_fill else None
    if filled_at:
        honest = honest_filled_at_iso(submitted or placed, filled_at)
        if honest and honest != filled_at:
            row["filled_at"] = honest
            filled_at = honest
    terminal_at = None
    if terminal and not has_fill:
        terminal_at = str(row.get("updated_at") or "") or None
    end = filled_at if has_fill else terminal_at
    if placed and _clocks_usable(placed, end):
        classified = classify_fill_audit(
            order_id=oid,
            symbol=str(row.get("symbol") or ""),
            side=str(row.get("side") or ""),
            order_type=str(row.get("order_type") or "MKT"),
            mode=str(row.get("mode") or ""),
            status=status,
            nova_placed_at=placed,
            submitted_at=submitted,
            filled_at=filled_at,
            terminal_at=terminal_at,
            has_fill=has_fill,
            rth=not bool(row.get("outside_rth")),
        )
        pub = public_fill_audit(classified)
        if pub is not None:
            return pub
    if stored is None:
        return None
    pub = public_fill_audit(stored)
    if pub is None:
        return None
    # Still-working rows do not show click-to-ack as "terminal".
    if has_fill or terminal:
        return pub
    if pub.get("place_to_fill_ms") is not None:
        return pub
    return None


def attach_fill_audit(
    rows: list[dict],
    *,
    ledger_rows: list[dict] | None = None,
) -> list[dict]:
    """Copy rows and set ``fill_audit`` (object or null). Never scrapes JSONL."""
    ledgers = ledger_rows
    if ledgers is None:
        try:
            from execution.closed_blotter import load_session_ledger

            ledgers = load_session_ledger()
        except Exception:
            logger.exception("fill_audit_attach: session ledger read failed")
            ledgers = []
    index = placed_index_from_ledger(ledgers)
    out: list[dict] = []
    for row in rows:
        copy = dict(row)
        copy["fill_audit"] = resolve_fill_audit(copy, index)
        out.append(copy)
    return out
