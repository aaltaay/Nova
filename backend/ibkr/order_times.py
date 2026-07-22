"""Extract submitted / last-activity timestamps from an ib_async Trade.

Audit rules for Time Placed (`submitted_at`):
1. Prefer IBKR trade.log[0].time (broker-authoritative place/ack trail).
2. If the broker log is empty (race right after placeOrder), use the
   Nova wall-clock stamp recorded at send time (`remember_nova_placed`).
3. Never invent a browser/client clock — UI only formats the ISO string.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# order_id → Nova wall-clock ISO UTC recorded at placeOrder send.
_nova_placed_at: dict[int, str] = {}


def _eastern_tz():
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo("America/New_York")
    except Exception:
        return timezone.utc


def wall_utc_now_iso() -> str:
    """Wall-clock UTC ISO-8601 with microsecond precision (audit stamp)."""
    ns = time.time_ns()
    sec, nsec = divmod(ns, 1_000_000_000)
    dt = datetime.fromtimestamp(sec, tz=timezone.utc).replace(
        microsecond=nsec // 1000,
    )
    return dt.isoformat().replace("+00:00", "Z")


def remember_nova_placed(order_id: int, iso: str | None = None) -> str:
    """Record Nova send-time for an order id (first stamp wins)."""
    oid = int(order_id)
    existing = _nova_placed_at.get(oid)
    if existing:
        return existing
    stamp = iso or wall_utc_now_iso()
    _nova_placed_at[oid] = stamp
    return stamp


def nova_placed_iso(order_id: int) -> str | None:
    return _nova_placed_at.get(int(order_id))


def clear_nova_placed_for_tests() -> None:
    """Test helper — do not call from product paths."""
    _nova_placed_at.clear()


def resolve_submitted_at(broker_submitted: str | None, order_id: int) -> str | None:
    """Broker log wins; Nova wall stamp fills gaps only."""
    if broker_submitted:
        return broker_submitted
    return nova_placed_iso(order_id)


def _to_iso(value: Any) -> str | None:
    """Normalize IBKR datetime / string times to ISO-8601 UTC (keep sub-seconds)."""
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value if value.tzinfo is not None else value.replace(tzinfo=_eastern_tz())
        return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

    text = str(value).strip()
    if not text:
        return None

    # Already ISO-ish (with or without Z).
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=_eastern_tz())
        return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    except ValueError:
        pass

    # Common IB execution string: "20260718  09:41:23" or with fractional seconds.
    compact = " ".join(text.split())
    for fmt in (
        "%Y%m%d %H:%M:%S.%f",
        "%Y%m%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
    ):
        try:
            dt = datetime.strptime(compact, fmt)
            return dt.replace(tzinfo=_eastern_tz()).astimezone(timezone.utc).isoformat().replace(
                "+00:00", "Z",
            )
        except ValueError:
            continue
    return None


def extract_trade_times(trade: Any) -> tuple[str | None, str | None, str | None]:
    """Return (submitted_at, updated_at, filled_at) ISO strings; any may be None.

    `filled_at` is the real broker fill clock (max of `Trade.fills[].execution.time`)
    and is `None` whenever the order never filled (straight cancel/reject) — callers
    must not fall back to log/cancel time here; `updated_at` already covers that.
    """
    log_times: list[Any] = []
    for entry in getattr(trade, "log", None) or []:
        t = getattr(entry, "time", None)
        if t is not None:
            log_times.append(t)

    fill_times: list[Any] = []
    for fill in getattr(trade, "fills", None) or []:
        t = getattr(getattr(fill, "execution", None), "time", None)
        if t is not None:
            fill_times.append(t)

    submitted = _to_iso(log_times[0]) if log_times else None

    last_fill_raw: Any = None
    if fill_times:
        try:
            last_fill_raw = max(fill_times)
        except TypeError:
            last_fill_raw = fill_times[-1]

    last_raw = last_fill_raw if last_fill_raw is not None else (log_times[-1] if log_times else None)

    return submitted, _to_iso(last_raw), _to_iso(last_fill_raw)


def audit_log_placed(
    *,
    order_id: int,
    symbol: str,
    side: str,
    qty: float,
    order_type: str,
    mode: str,
    nova_placed_at: str,
    broker_submitted_at: str | None,
) -> None:
    """Single structured line for place-time audits (no secrets)."""
    logger.info(
        "IBKR_ORDER_AUDIT placed order_id=%s symbol=%s side=%s qty=%s type=%s "
        "mode=%s nova_placed_at_utc=%s broker_submitted_at_utc=%s",
        order_id,
        symbol,
        side,
        qty,
        order_type,
        mode,
        nova_placed_at,
        broker_submitted_at or "",
    )
