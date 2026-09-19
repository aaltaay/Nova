"""Single sensor registry -- id, path, status, reader."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sensors.adapters import advice, bars, bookish, desk, stubs, tapeish, volume

Reader = Callable[..., dict[str, Any]]


@dataclass(frozen=True)
class SensorSpec:
    sensor_id: int
    key: str
    title: str
    path: str
    status: str
    needs_symbol: bool
    reader: Reader


SPECS: tuple[SensorSpec, ...] = (
    SensorSpec(1, "l2", "L2 book", "/sensors/l2", "live", True, bookish.read_l2),
    SensorSpec(2, "tape", "Time & sales tape", "/sensors/tape", "live", True, tapeish.read_tape),
    SensorSpec(3, "vwap", "VWAP", "/sensors/vwap", "live", True, bars.read_vwap),
    SensorSpec(4, "macd", "MACD", "/sensors/macd", "live", True, bars.read_macd),
    SensorSpec(5, "rvol", "Relative volume", "/sensors/rvol", "live", True, volume.read_rvol),
    SensorSpec(6, "day-volume", "Day volume", "/sensors/day-volume", "live", True, volume.read_day_volume),
    SensorSpec(7, "spread", "Spread", "/sensors/spread", "live", True, bookish.read_spread),
    SensorSpec(8, "session-phase", "Session phase", "/sensors/session-phase", "live", False, desk.read_session_phase),
    SensorSpec(9, "flow", "Order-flow events", "/sensors/flow", "live", True, bookish.read_flow),
    SensorSpec(10, "last-move", "Time since last significant move", "/sensors/last-move", "live", True, tapeish.read_last_move),
    SensorSpec(11, "liquidity", "Liquidity profile", "/sensors/liquidity", "live", True, bookish.read_liquidity),
    SensorSpec(12, "emas", "EMA 9/20/200", "/sensors/emas", "live", True, bars.read_emas),
    SensorSpec(13, "news", "News / catalyst (Advice)", "/sensors/news", "live", True, advice.read_news),
    SensorSpec(14, "risk", "Risk state", "/sensors/risk", "live", False, desk.read_risk),
    SensorSpec(15, "halt", "Halt / LULD", "/sensors/halt", "live", True, desk.read_halt),
    SensorSpec(16, "memory", "Brain memory", "/sensors/memory", "stub", True, stubs.read_memory),
    SensorSpec(17, "regime", "Regime detector", "/sensors/regime", "computed_stub", True, stubs.read_regime),
    SensorSpec(18, "macro", "Macro calendar", "/sensors/macro", "stub", False, stubs.read_macro),
)

SENSOR_IDS = tuple(spec.key for spec in SPECS)
BY_KEY = {spec.key: spec for spec in SPECS}


def list_catalog() -> list[dict[str, Any]]:
    return [
        {
            "id": spec.sensor_id,
            "sensor": spec.key,
            "title": spec.title,
            "path": spec.path,
            "status": spec.status,
            "needs_symbol": spec.needs_symbol,
        }
        for spec in SPECS
    ]


def read_one(key: str, symbol: str | None) -> dict[str, Any]:
    spec = BY_KEY[key]
    if spec.needs_symbol:
        return spec.reader(symbol)
    if key in ("risk", "macro") and symbol:
        return spec.reader(symbol)
    return spec.reader()


def read_all(symbol: str) -> list[dict[str, Any]]:
    rows = []
    for spec in SPECS:
        if spec.needs_symbol:
            rows.append(spec.reader(symbol))
        elif spec.key in ("risk", "macro"):
            rows.append(spec.reader(symbol))
        else:
            rows.append(spec.reader())
    return rows
