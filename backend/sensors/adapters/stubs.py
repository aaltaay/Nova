"""Stable stub / computed-stub sensors 16-18."""
from __future__ import annotations

from typing import Any

from constants_sensors import SENSOR_MACRO_EVENTS, SENSOR_MEMORY_MAX, SENSOR_REGIME_BARS
from sensors.envelope import build_envelope
from sensors.feeds import get_bars, get_book, get_prints
from sensors import memory_store
from sensors.math_indicators import median


def read_memory(symbol: str) -> dict[str, Any]:
    rows = memory_store.list_decisions(symbol, SENSOR_MEMORY_MAX)
    return build_envelope(
        sensor="memory",
        symbol=symbol,
        status="stub",
        data={
            "decisions": rows,
            "count": len(rows),
            "write_path": "POST /sensors/memory",
            "note": "Local brain log. Not Advice, not IBKR.",
        },
    )


def write_memory(
    *,
    symbol: str,
    decision: str,
    confidence: float | None = None,
    outcome: str | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    row = memory_store.append_decision(
        symbol=symbol,
        decision=decision,
        confidence=confidence,
        outcome=outcome,
        note=note,
    )
    return build_envelope(
        sensor="memory",
        symbol=symbol,
        status="stub",
        data={"appended": row, "decisions": memory_store.list_decisions(symbol)},
    )


def _regime_from_bars(bars: list[dict[str, Any]]) -> dict[str, Any]:
    closes = [float(b["c"]) for b in bars]
    if len(closes) < 8:
        return {"regime": "unknown", "confidence": 0.15, "reason": "not_enough_bars"}
    rets = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    net = abs(sum(rets))
    travel = sum(abs(r) for r in rets) or 1.0
    efficiency = net / travel
    auto = 0.0
    if len(rets) >= 3:
        pairs = list(zip(rets[1:], rets[:-1], strict=False))
        auto = sum(a * b for a, b in pairs) / max(1, len(pairs))
    vol = median([abs(r) for r in rets]) or 0.0
    if efficiency >= 0.45:
        return {
            "regime": "trending",
            "confidence": round(min(0.85, 0.4 + efficiency), 3),
            "efficiency": round(efficiency, 4),
            "return_autocorr": round(auto, 6),
            "median_abs_return": vol,
        }
    if auto < 0:
        return {
            "regime": "mean-reverting",
            "confidence": round(min(0.7, 0.35 + min(0.3, abs(auto) * 10)), 3),
            "efficiency": round(efficiency, 4),
            "return_autocorr": round(auto, 6),
            "median_abs_return": vol,
        }
    return {
        "regime": "chopping",
        "confidence": round(0.35 + (0.2 if efficiency < 0.2 else 0.1), 3),
        "efficiency": round(efficiency, 4),
        "return_autocorr": round(auto, 6),
        "median_abs_return": vol,
    }


def read_regime(symbol: str) -> dict[str, Any]:
    bars, source = get_bars(symbol, limit=SENSOR_REGIME_BARS)
    prints, _ = get_prints(symbol)
    book, _ = get_book(symbol)
    if len(bars) < 8:
        return build_envelope(
            sensor="regime",
            symbol=symbol,
            status="computed_stub",
            data={
                "regime": "unknown",
                "confidence": 0.1,
                "source": source,
                "has_tape": bool(prints),
                "has_book": book is not None,
                "note": "Stub until enough 1Min bars exist. No new market-data feed.",
            },
        )
    calc = _regime_from_bars(bars[-SENSOR_REGIME_BARS:])
    calc.update(
        {
            "source": source,
            "has_tape": bool(prints),
            "has_book": book is not None,
            "note": "Computed from existing 1Min closes. No new subscription.",
        }
    )
    return build_envelope(sensor="regime", symbol=symbol, status="computed_stub", data=calc)


def read_macro(symbol: str | None = None) -> dict[str, Any]:
    events = [dict(row) for row in SENSOR_MACRO_EVENTS]
    if symbol:
        events.append(
            {
                "id": f"earnings-{symbol.lower()}",
                "kind": "earnings",
                "title": f"{symbol} earnings (schedule stub)",
                "scheduled_ts": None,
                "expected_impact": "medium",
                "symbol": symbol,
            }
        )
    return build_envelope(
        sensor="macro",
        symbol=symbol,
        status="stub",
        data={
            "events": events,
            "count": len(events),
            "note": "Static stub schedule. Not Advice. Do not reuse GET /sensors/news.",
        },
    )
