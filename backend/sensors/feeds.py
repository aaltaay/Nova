"""Thin readers over existing IBKR / replay pipes. No new subscriptions.

In the Sim venue a loaded capture replay feeds the same depth and tape pipes, so
the readers are shared; only the source label says the data is a replay.
"""
from __future__ import annotations

from typing import Any

from constants_sensors import SENSOR_BAR_LIMIT, SENSOR_TAPE_PRINTS
from sensors import rings


def _sim_on() -> bool:
    try:
        from sim.mode import is_sim_mode

        return is_sim_mode()
    except Exception:
        return False


def _label(live: str) -> str:
    return "replay" if _sim_on() else live


def get_book(symbol: str) -> tuple[dict[str, Any] | None, str | None]:
    try:
        from ibkr.depth.state import current_book

        book = current_book(symbol)
    except Exception:
        book = None
    if book:
        return book, _label("ibkr_depth")
    return None, None


def get_prints(symbol: str, limit: int = SENSOR_TAPE_PRINTS) -> tuple[list[dict[str, Any]], str | None]:
    rows = rings.recent_prints(symbol, limit)
    if rows:
        return rows, _label("ibkr_tape")
    return [], None


def get_quote(symbol: str) -> tuple[dict[str, Any] | None, str | None]:
    try:
        from ibkr.ticks import last_quotes

        row = last_quotes([symbol]).get(symbol)
    except Exception:
        row = None
    if row:
        return row, _label("ibkr_l1")
    return None, None


def _normalize_bars(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        from ibkr.historical_derive import bar_unix

        ts = bar_unix(raw)
        if ts is None:
            continue
        try:
            out.append(
                {
                    "t": ts,
                    "o": float(raw.get("o")),
                    "h": float(raw.get("h")),
                    "l": float(raw.get("l")),
                    "c": float(raw.get("c")),
                    "v": float(raw.get("v") or 0),
                }
            )
        except (TypeError, ValueError):
            continue
    return out


def get_bars(
    symbol: str,
    timeframe: str = "1Min",
    limit: int = SENSOR_BAR_LIMIT,
) -> tuple[list[dict[str, Any]], str | None]:
    cap = max(1, min(int(limit), 2000))
    try:
        import bars_store

        stored = bars_store.read(symbol, timeframe, cap)
    except Exception:
        stored = None
    if not stored or not stored.get("bars"):
        return [], None
    return _normalize_bars(list(stored["bars"])), str(stored.get("source") or "bars_store")


def peek_avg_volume(symbol: str) -> float | None:
    try:
        from fundamentals import peek_cached

        fund = peek_cached(symbol) or {}
        avg = fund.get("average_volume")
        return float(avg) if avg else None
    except Exception:
        return None
