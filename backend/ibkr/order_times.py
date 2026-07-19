"""Extract submitted / last-activity timestamps from an ib_async Trade."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _eastern_tz():
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo("America/New_York")
    except Exception:
        return timezone.utc


def _to_iso(value: Any) -> str | None:
    """Normalize IBKR datetime / string times to ISO-8601 UTC."""
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value if value.tzinfo is not None else value.replace(tzinfo=_eastern_tz())
        return dt.astimezone(timezone.utc).isoformat()

    text = str(value).strip()
    if not text:
        return None

    # Already ISO-ish (with or without Z).
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=_eastern_tz())
        return parsed.astimezone(timezone.utc).isoformat()
    except ValueError:
        pass

    # Common IB execution string: "20260718  09:41:23"
    compact = " ".join(text.split())
    for fmt in ("%Y%m%d %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            dt = datetime.strptime(compact[:17] if fmt.startswith("%Y%m%d") else compact[:19], fmt)
            return dt.replace(tzinfo=_eastern_tz()).astimezone(timezone.utc).isoformat()
        except ValueError:
            continue
    return None


def extract_trade_times(trade: Any) -> tuple[str | None, str | None]:
    """Return (submitted_at, updated_at) ISO strings; either may be None."""
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

    last_raw: Any = None
    if fill_times:
        try:
            last_raw = max(fill_times)
        except TypeError:
            last_raw = fill_times[-1]
    elif log_times:
        last_raw = log_times[-1]

    return submitted, _to_iso(last_raw)
