"""Common sensor response envelope."""
from __future__ import annotations

import time
from typing import Any

from constants_sensors import SENSOR_STATUSES

SENSOR_STATUSES = SENSOR_STATUSES


def build_envelope(
    *,
    sensor: str,
    status: str,
    data: dict[str, Any] | None = None,
    symbol: str | None = None,
    error: str | None = None,
    as_of: float | None = None,
) -> dict[str, Any]:
    if status not in SENSOR_STATUSES:
        raise ValueError(f"unknown sensor status {status!r}")
    payload: dict[str, Any] = {
        "sensor": sensor,
        "status": status,
        "as_of": float(as_of if as_of is not None else time.time()),
        "data": data if data is not None else {},
    }
    if symbol is not None:
        payload["symbol"] = symbol
    if error:
        payload["error"] = error
    return payload
