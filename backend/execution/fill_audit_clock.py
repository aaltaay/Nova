"""Refuse or correct timezone-shaped fill-latency measurements.

IBKR Execution.time is server/UTC wall digits. ib_async (empty TimezoneTWS)
and older Nova `_to_iso` treated those naive digits as America/New_York, then
converted to UTC -- a false +4h (EDT) / +5h (EST) on Ahmed's bench.

Owner: execution.fill_audit_clock. Pure clock math; no IBKR I/O.
schema_version: 1.
"""
from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from constants_ibkr import (
    FILL_AUDIT_FAST_TYPES,
    FILL_AUDIT_IMPOSSIBLE_MKT_FILL_MS,
    FILL_AUDIT_REASON_IMPOSSIBLE,
    FILL_AUDIT_REASON_TIMEZONE_SHAPED,
    FILL_AUDIT_SAME_SECOND_SUBMIT_MS,
    FILL_AUDIT_TZ_OFFSET_SLACK_MS,
    FILL_AUDIT_TZ_RESIDUAL_MAX_MS,
)

_ET = ZoneInfo("America/New_York")
_HOUR_MS = 3_600_000
_FALLBACK_OFFSET_MS = (4 * _HOUR_MS, 5 * _HOUR_MS)


def _parse_iso(iso: str | None) -> datetime | None:
    if not iso:
        return None
    text = str(iso).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def ny_offset_ms(placed_iso: str | None) -> int | None:
    """UTC-minus-ET milliseconds at the place stamp (14400000 in EDT)."""
    dt = _parse_iso(placed_iso)
    if dt is None:
        return None
    off = dt.astimezone(_ET).utcoffset()
    if off is None:
        return None
    return int(round(-off.total_seconds() * 1000))


def _same_second_submit(place_to_submit_ms: int | None) -> bool:
    if place_to_submit_ms is None:
        return False
    return abs(place_to_submit_ms) <= FILL_AUDIT_SAME_SECOND_SUBMIT_MS


def _residual_in_window(residual: int) -> bool:
    return (
        -FILL_AUDIT_TZ_OFFSET_SLACK_MS
        <= residual
        <= FILL_AUDIT_TZ_RESIDUAL_MAX_MS
    )


def timezone_shaped_residual_ms(
    place_to_fill_ms: int | None,
    place_to_submit_ms: int | None,
    placed_iso: str | None,
) -> int | None:
    """Residual after removing a NY (or 4h/5h) offset, else None."""
    if place_to_fill_ms is None or not _same_second_submit(place_to_submit_ms):
        return None
    offsets: list[int] = []
    ny = ny_offset_ms(placed_iso)
    if ny is not None:
        offsets.append(ny)
    for extra in _FALLBACK_OFFSET_MS:
        if extra not in offsets:
            offsets.append(extra)
    for offset in offsets:
        residual = place_to_fill_ms - offset
        if _residual_in_window(residual):
            return residual
    return None


def apply_fill_clock_guard(
    *,
    place_to_fill_ms: int | None,
    place_to_submit_ms: int | None,
    placed_iso: str | None,
    order_type: str,
) -> tuple[int | None, str | None]:
    """Return (fill_ms, refuse_reason).

    MKT-class + timezone-shaped: correct to the residual (same wire digits,
    UTC label -- not an invented stamp). Other types refuse. Multi-hour MKT
    with a same-second submit that is not TZ-shaped is impossible_fill_clock.
    """
    typ = (order_type or "").upper()
    residual = timezone_shaped_residual_ms(
        place_to_fill_ms,
        place_to_submit_ms,
        placed_iso,
    )
    if residual is not None:
        if typ in FILL_AUDIT_FAST_TYPES:
            return max(0, residual), None
        return None, FILL_AUDIT_REASON_TIMEZONE_SHAPED
    if (
        typ in FILL_AUDIT_FAST_TYPES
        and place_to_fill_ms is not None
        and place_to_fill_ms >= FILL_AUDIT_IMPOSSIBLE_MKT_FILL_MS
        and _same_second_submit(place_to_submit_ms)
    ):
        return None, FILL_AUDIT_REASON_IMPOSSIBLE
    return place_to_fill_ms, None
