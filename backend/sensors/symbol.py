"""Normalize ticker query params for sensors."""
from __future__ import annotations

import re

from constants_sensors import default_sensor_symbol

_SYMBOL_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,11}$")


class SensorSymbolError(ValueError):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def normalize_symbol(raw: str | None, *, required: bool = True) -> str | None:
    value = (raw or "").strip().upper()
    if not value:
        if required:
            raise SensorSymbolError("symbol is required")
        return None
    if not _SYMBOL_RE.match(value):
        raise SensorSymbolError("Enter a ticker like AAPL")
    return value


def resolve_symbol(raw: str | None) -> str:
    """Required symbol, or SIM1 / AAPL when the query is omitted."""
    if raw is None or not str(raw).strip():
        try:
            from sim.mode import is_sim_mode
        except Exception:
            return default_sensor_symbol(sim=False)
        return default_sensor_symbol(sim=is_sim_mode())
    return normalize_symbol(raw, required=True) or default_sensor_symbol(sim=False)
