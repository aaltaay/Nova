"""RVOL and day-volume adapters."""
from __future__ import annotations

from typing import Any

from large_cap_metrics import compute_rvol
from sensors.envelope import build_envelope
from sensors.feeds import get_quote, peek_avg_volume


def _day_volume(quote: dict[str, Any] | None) -> float | None:
    if not quote:
        return None
    raw = quote.get("volume")
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def read_day_volume(symbol: str) -> dict[str, Any]:
    quote, source = get_quote(symbol)
    volume = _day_volume(quote)
    return build_envelope(
        sensor="day-volume",
        symbol=symbol,
        status="live",
        data={
            "source": source,
            "day_volume": volume,
            "last": (quote or {}).get("price") or (quote or {}).get("last"),
        },
        error=None if volume is not None else "No day volume on the shared L1 / Sim quote.",
    )


def read_rvol(symbol: str) -> dict[str, Any]:
    quote, q_source = get_quote(symbol)
    today = _day_volume(quote)
    adv = peek_avg_volume(symbol)
    pace = compute_rvol(today, adv)
    rvol_5min = None
    try:
        from hod_momo_market import peek_rvol_5min

        rvol_5min = peek_rvol_5min(symbol)
    except Exception:
        rvol_5min = None
    return build_envelope(
        sensor="rvol",
        symbol=symbol,
        status="live",
        data={
            "quote_source": q_source,
            "day_volume": today,
            "average_volume": adv,
            "rvol_vs_adv_pace": pace,
            "rvol_5min": rvol_5min,
            "tod_20d": None,
            "note": (
                "20-day time-of-day average is not stored. "
                "Using existing ADV pace (today / expected-by-clock) and Warrior 5-min when present."
            ),
        },
        error=None
        if (pace is not None or rvol_5min is not None or today is not None)
        else "No volume / ADV yet for RVOL.",
    )
