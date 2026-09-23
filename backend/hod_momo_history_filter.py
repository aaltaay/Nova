"""HOD Momo alert history up to a moment (ADR 022) -- pure."""
from __future__ import annotations

from datetime import datetime
from typing import Any


def raised_at(alert: dict[str, Any]) -> float | None:
    """When Nova raised the alert: ``created_ts``, else its ISO ``timestamp``."""
    created = alert.get("created_ts")
    if isinstance(created, (int, float)) and not isinstance(created, bool) and created > 0:
        return float(created)
    stamp = alert.get("timestamp")
    if isinstance(stamp, str) and stamp:
        try:
            return datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return None
    return None


def raised_by(alerts: list[Any], until: float) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for alert in alerts:
        if not isinstance(alert, dict):
            continue
        when = raised_at(alert)
        if when is not None and when <= until:
            out.append(alert)
    return out
