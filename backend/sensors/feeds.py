"""Thin readers over existing IBKR / Sim pipes. No new subscriptions."""
from __future__ import annotations

from typing import Any

from constants_sensors import SENSOR_BAR_LIMIT, SENSOR_TAPE_PRINTS
from constants_sim import SIM_SYMBOL
from sensors import rings


def _sim_on() -> bool:
    try:
        from sim.mode import is_sim_mode

        return is_sim_mode()
    except Exception:
        return False


def get_book(symbol: str) -> tuple[dict[str, Any] | None, str | None]:
    if _sim_on() and symbol == SIM_SYMBOL:
        from sim import market as _market

        book = _market.book()
        rings.observe_book(symbol, book)
        return book, "sim"
    try:
        from ibkr.depth.state import current_book

        book = current_book(symbol)
    except Exception:
        book = None
    if book:
        return book, "ibkr_depth"
    return None, None


def get_prints(symbol: str, limit: int = SENSOR_TAPE_PRINTS) -> tuple[list[dict[str, Any]], str | None]:
    rows = rings.recent_prints(symbol, limit)
    if rows:
        source = "sim" if _sim_on() and symbol == SIM_SYMBOL else "ibkr_tape"
        return rows, source
    if _sim_on() and symbol == SIM_SYMBOL:
        from sim import market as _market

        return _market.recent_prints(limit), "sim"
    return [], None


def get_quote(symbol: str) -> tuple[dict[str, Any] | None, str | None]:
    if _sim_on() and symbol == SIM_SYMBOL:
        from sim import market as _market

        return _market.quote(symbol), "sim"
    try:
        from ibkr.ticks import last_quotes

        row = last_quotes([symbol]).get(symbol)
    except Exception:
        row = None
    if row:
        return row, "ibkr_l1"
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
    if _sim_on() and symbol == SIM_SYMBOL:
        from sim import market as _market

        payload = _market.chart_bars(symbol, timeframe, cap)
        return _normalize_bars(list(payload.get("bars") or [])), "sim"
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
