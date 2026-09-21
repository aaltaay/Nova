"""Normalize ticker query params for sensors."""
from __future__ import annotations

import re

from constants_sensors import SENSOR_DEFAULT_LIQUID_SYMBOL

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


def _default_symbol() -> str:
    """The loaded replay's symbol in the Sim venue, else the liquid default."""
    try:
        from sim.mode import is_sim_mode
        from sim.practice import loaded
    except Exception:
        return SENSOR_DEFAULT_LIQUID_SYMBOL
    active = loaded() if is_sim_mode() else None
    return active.symbol if active else SENSOR_DEFAULT_LIQUID_SYMBOL


def resolve_symbol(raw: str | None) -> str:
    """Required symbol, or the Sim replay symbol / AAPL when the query is omitted."""
    if raw is None or not str(raw).strip():
        return _default_symbol()
    return normalize_symbol(raw, required=True) or SENSOR_DEFAULT_LIQUID_SYMBOL
