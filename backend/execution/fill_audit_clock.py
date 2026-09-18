"""Refuse or correct timezone-shaped fill-latency measurements.

IBKR Execution.time is server/UTC wall digits. ib_async (empty TimezoneTWS)
and older Nova `_to_iso` treated those naive digits as America/New_York, then
converted to UTC -- a false +4h (EDT) / +5h (EST) on Ahmed's bench.

Owner: execution.fill_audit_clock. Pure clock math; no IBKR I/O.
schema_version: 1.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from constants_ibkr import (
    FILL_AUDIT_FAST_TYPES,
    FILL_AUDIT_IMPOSSIBLE_MKT_FILL_MS,
    FILL_AUDIT_REASON_CLOCK_SKEW,
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


def is_clock_skew_ms(ms: int | None) -> bool:
    """True when a face total cannot be a real fill duration.

    IBKR ``submitted_at`` / ``filled_at`` are often whole-second stamps.
    Nova ``nova_placed_at`` has millisecond precision. When both IBKR
    stamps land on the same second and Nova is later -- IMCC BUY 106411
    ``place_to_fill_ms=-296`` -- the delta is clock disagreement, not a
    fill before Place.

    Any negative is skew. ``FILL_AUDIT_CLOCK_SKEW_MS`` (1000) is the
    expected whole-second rounding ceiling; larger negatives stay
    ``clock_skew`` / ok, not danger.
    """
    if ms is None or ms >= 0:
        return False
    # Usual |skew| is 1..FILL_AUDIT_CLOCK_SKEW_MS (whole-second IBKR
    # stamps). Every negative still counts -- not a fill before Place.
    return True


def coherent_face_ms(
    place_to_fill_ms: int | None,
    place_to_terminal_ms: int | None,
    reason: str | None,
) -> int | None:
    """Face total only when both endpoints tell one coherent clock story.

    Missing stamps, negatives, zero, clock_skew, timezone-shaped, and
    impossible clocks return None -- never a guessed 0ms or a negative face.
    """
    if reason in {
        FILL_AUDIT_REASON_CLOCK_SKEW,
        FILL_AUDIT_REASON_TIMEZONE_SHAPED,
        FILL_AUDIT_REASON_IMPOSSIBLE,
    }:
        return None
    if place_to_fill_ms is not None:
        return place_to_fill_ms if place_to_fill_ms > 0 else None
    if place_to_terminal_ms is not None:
        return place_to_terminal_ms if place_to_terminal_ms > 0 else None
    return None


def clock_guard_level(reason: str | None) -> str | None:
    """Detective tone for a clock-guard reason. clock_skew stays calm."""
    if reason is None:
        return None
    if reason == FILL_AUDIT_REASON_CLOCK_SKEW:
        return "ok"
    if reason == FILL_AUDIT_REASON_IMPOSSIBLE:
        return "danger"
    return "warn"


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


def ny_shaped_offset_ms(
    place_to_fill_ms: int | None,
    placed_iso: str | None,
) -> int | None:
    """NY / 4h / 5h offset when place→fill matches it, else None."""
    if place_to_fill_ms is None:
        return None
    offsets: list[int] = []
    ny = ny_offset_ms(placed_iso)
    if ny is not None:
        offsets.append(ny)
    for extra in _FALLBACK_OFFSET_MS:
        if extra not in offsets:
            offsets.append(extra)
    for offset in offsets:
        if _residual_in_window(place_to_fill_ms - offset):
            return offset
    return None


def timezone_shaped_residual_ms(
    place_to_fill_ms: int | None,
    place_to_submit_ms: int | None,
    placed_iso: str | None,
) -> int | None:
    """Residual after removing a NY (or 4h/5h) offset, else None."""
    if place_to_fill_ms is None or not _same_second_submit(place_to_submit_ms):
        return None
    offset = ny_shaped_offset_ms(place_to_fill_ms, placed_iso)
    if offset is None:
        return None
    return place_to_fill_ms - offset


def _delta_ms_iso(start_iso: str | None, end_iso: str | None) -> int | None:
    start = _parse_iso(start_iso)
    end = _parse_iso(end_iso)
    if start is None or end is None:
        return None
    return int(round((end.timestamp() - start.timestamp()) * 1000.0))


def _iso_utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def same_clock_instant(left: str | None, right: str | None) -> bool:
    """True when two ISO stamps name the same UTC instant (.000Z vs Z)."""
    a = _parse_iso(left)
    b = _parse_iso(right)
    if a is None or b is None:
        return bool(left) and left == right
    return a == b


def honest_filled_at_iso(
    reference_iso: str | None,
    filled_iso: str | None,
) -> str | None:
    """Rewrite a NY-offset-shaped fill to the UTC wall digits.

    ib_async ``naive.astimezone(UTC)`` on an Eastern host turns UTC
    ``15:02:48`` digits into ``19:02:48Z``. Time Placed stays the real
    UTC instant, so Time Filled must not keep the +4h label.
    """
    if not filled_iso:
        return filled_iso
    filled_dt = _parse_iso(filled_iso)
    if filled_dt is None:
        return filled_iso
    raw = _delta_ms_iso(reference_iso, filled_iso)
    offset = ny_shaped_offset_ms(raw, reference_iso)
    if offset is None:
        return filled_iso
    return _iso_utc(filled_dt - timedelta(milliseconds=offset))


def apply_fill_clock_guard(
    *,
    place_to_fill_ms: int | None,
    place_to_submit_ms: int | None,
    placed_iso: str | None,
    order_type: str,
) -> tuple[int | None, str | None]:
    """Return (fill_ms, clock_reason).

    MKT-class + timezone-shaped: correct to the residual (same wire digits,
    UTC label -- not an invented stamp). Other types refuse. Multi-hour MKT
    with a same-second submit that is not TZ-shaped is impossible_fill_clock.
    A negative residual or raw fill is clock_skew (keep the raw ms).
    """
    typ = (order_type or "").upper()
    residual = timezone_shaped_residual_ms(
        place_to_fill_ms,
        place_to_submit_ms,
        placed_iso,
    )
    if residual is not None:
        if typ in FILL_AUDIT_FAST_TYPES:
            if residual == 0:
                # Exact offset collapse (109741 created_ts + ib_async +4h).
                # Not an honest instant fill -- never publish 0ms.
                return None, FILL_AUDIT_REASON_TIMEZONE_SHAPED
            if is_clock_skew_ms(residual):
                return residual, FILL_AUDIT_REASON_CLOCK_SKEW
            return residual, None
        return None, FILL_AUDIT_REASON_TIMEZONE_SHAPED
    if (
        typ in FILL_AUDIT_FAST_TYPES
        and place_to_fill_ms is not None
        and place_to_fill_ms >= FILL_AUDIT_IMPOSSIBLE_MKT_FILL_MS
        and _same_second_submit(place_to_submit_ms)
    ):
        return None, FILL_AUDIT_REASON_IMPOSSIBLE
    if is_clock_skew_ms(place_to_fill_ms):
        return place_to_fill_ms, FILL_AUDIT_REASON_CLOCK_SKEW
    if place_to_fill_ms == 0:
        return None, None
    return place_to_fill_ms, None
