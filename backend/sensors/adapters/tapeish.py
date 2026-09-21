"""Tape and last-move adapters."""
from __future__ import annotations

import time
from typing import Any

from constants_sensors import SENSOR_LAST_MOVE_LOOKBACK, SENSOR_TAPE_PRINTS
from sensors.envelope import build_envelope
from sensors.feeds import get_bars, get_prints
from sensors.math_indicators import median


def _parse_ts(raw: Any) -> float | None:
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    text = str(raw).strip().replace("Z", "+00:00")
    try:
        from datetime import datetime

        return datetime.fromisoformat(text).timestamp()
    except ValueError:
        return None


def _cluster_sizes(prints: list[dict[str, Any]]) -> dict[str, Any]:
    sizes: list[float] = []
    for row in prints:
        try:
            sizes.append(float(row.get("size") or 0))
        except (TypeError, ValueError):
            continue
    if not sizes:
        return {"count": 0, "median": None, "max": None, "repeat_size": None}
    tallies: dict[float, int] = {}
    for size in sizes:
        tallies[size] = tallies.get(size, 0) + 1
    repeat = max(tallies.items(), key=lambda item: item[1])
    return {
        "count": len(sizes),
        "median": median(sizes),
        "max": max(sizes),
        "repeat_size": repeat[0],
        "repeat_count": repeat[1],
    }


def _inter_print(prints: list[dict[str, Any]]) -> dict[str, Any]:
    stamps = []
    for row in prints:
        ts = _parse_ts(row.get("time") or row.get("ts") or row.get("timestamp"))
        if ts is not None:
            stamps.append(ts)
    stamps.sort()
    gaps = [stamps[i] - stamps[i - 1] for i in range(1, len(stamps)) if stamps[i] >= stamps[i - 1]]
    return {
        "intervals_sec": [round(g, 4) for g in gaps[-12:]],
        "median_gap_sec": median(gaps) if gaps else None,
        "last_print_age_sec": round(time.time() - stamps[-1], 3) if stamps else None,
    }


def read_tape(symbol: str) -> dict[str, Any]:
    prints, source = get_prints(symbol, SENSOR_TAPE_PRINTS)
    rows = []
    for row in prints[-SENSOR_TAPE_PRINTS:]:
        rows.append(
            {
                "time": row.get("time") or row.get("ts"),
                "price": row.get("price"),
                "size": row.get("size"),
                "aggressor": row.get("side"),
                "bid": row.get("bid"),
                "ask": row.get("ask"),
                "exchange": row.get("exchange"),
            }
        )
    error = None if rows else "No prints yet. Open Trader tape, or load a replay in Sim."
    return build_envelope(
        sensor="tape",
        symbol=symbol,
        status="live",
        data={
            "source": source,
            "prints": rows,
            "print_count": len(rows),
            "size_clustering": _cluster_sizes(prints),
            "timing": _inter_print(prints),
        },
        error=error,
    )


def read_last_move(symbol: str) -> dict[str, Any]:
    bars, source = get_bars(symbol)
    if len(bars) < 2:
        return build_envelope(
            sensor="last-move",
            symbol=symbol,
            status="live",
            data={"source": source, "bars": len(bars)},
            error="Need 1Min bars to measure a significant move (no trip level invented).",
        )
    look = bars[-SENSOR_LAST_MOVE_LOOKBACK:]
    ranges = [float(b["h"]) - float(b["l"]) for b in look]
    med = median(ranges)
    significant = None
    if med is not None:
        for bar in reversed(look):
            rng = float(bar["h"]) - float(bar["l"])
            if rng >= med and rng > 0:
                significant = bar
                break
    age = None
    if significant is not None:
        age = round(time.time() - float(significant["t"]), 3)
    return build_envelope(
        sensor="last-move",
        symbol=symbol,
        status="live",
        data={
            "source": source,
            "seconds_ago": age,
            "median_range": med,
            "bar": significant,
            "method": "last 1Min bar whose range >= median of last 20 1Min ranges",
            "note": "Relative to realized range. No Ahmed trip/clear level.",
        },
        error=None if significant is not None else "No bar met the relative-range rule.",
    )
