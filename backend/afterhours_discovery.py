"""After-hours mover discovery for HOD Momo + After Hours tab.

When ``discovery=ibkr``, Warrior-style AH HOD needs live Top % Gainers —
not Alpaca IEX's thin extended-hours snapshot scan (often 0–2 rows).
IBKR ``TOP_PERC_GAIN`` works after the close the same way as RTH.
"""
from __future__ import annotations

import logging

from constants import GAPPER_MIN_GAP_PCT, SCANNER_MIN_PRICE
from market import pace_relative_volume

logger = logging.getLogger(__name__)


def build_afterhours_rows_from_ibkr_gainers(
    gainers_rows: list[dict],
    *,
    min_change_pct: float = GAPPER_MIN_GAP_PCT,
) -> list[dict]:
    """Map IBKR gainer rows into the After Hours cache shape.

    ``change_pct`` from ibkr/discovery is a fraction (0.36 = +36%).
    Filters to ``min_change_pct`` (percent points, same as gapper floor).
    """
    out: list[dict] = []
    floor = float(min_change_pct) / 100.0
    for r in gainers_rows or []:
        sym = (r.get("symbol") or "").strip().upper()
        if not sym:
            continue
        price = r.get("price")
        prev = r.get("prev_close")
        if price is None or prev is None:
            continue
        try:
            price_f = float(price)
            prev_f = float(prev)
        except (TypeError, ValueError):
            continue
        if price_f < SCANNER_MIN_PRICE or prev_f <= 0:
            continue
        change = r.get("change_pct")
        try:
            change_f = float(change) if change is not None else (price_f - prev_f) / prev_f
        except (TypeError, ValueError):
            continue
        if change_f < floor:
            continue
        out.append({
            "symbol": sym,
            "price": price_f,
            "prev_close": prev_f,
            "change_pct": change_f,
            "change_abs": price_f - prev_f,
            "previous_close": prev_f,
            "current_price": price_f,
            "gap_percent": change_f,
            "volume": int(r.get("volume") or 0),
            "exchange": r.get("exchange"),
        })
    out.sort(key=lambda x: x["change_pct"], reverse=True)
    logger.info(
        "AH IBKR movers: %d rows after %.0f%% change filter",
        len(out),
        min_change_pct,
    )
    return out


def reprice_afterhours_rows_ibkr(
    rows: list[dict],
    quotes: dict[str, dict],
    avg_volume_by_symbol: dict[str, float],
) -> list[dict]:
    """Apply IBKR snapshot quotes onto AH cache rows; recompute change + pace RVOL."""
    updated: list[dict] = []
    for r in rows:
        sym = r["symbol"]
        q = quotes.get(sym) or {}
        price = q.get("price", r.get("price"))
        prev_close = r.get("previous_close") or r.get("prev_close") or q.get("prev_close")
        if price is None or not prev_close:
            updated.append(r)
            continue
        try:
            price_f = float(price)
            prev_f = float(prev_close)
        except (TypeError, ValueError):
            updated.append(r)
            continue
        if price_f < SCANNER_MIN_PRICE or prev_f <= 0:
            continue
        vol = int(q["volume"]) if q.get("volume") is not None else int(r.get("volume") or 0)
        gap_frac = (price_f - prev_f) / prev_f
        avg = avg_volume_by_symbol.get(sym)
        paced = pace_relative_volume(vol, avg) if avg and vol else None
        raw_rvol = round(vol / avg, 2) if avg and avg > 0 and vol > 0 else r.get("rel_volume")
        updated.append({
            **r,
            "price": price_f,
            "prev_close": prev_f,
            "change_pct": gap_frac,
            "change_abs": price_f - prev_f,
            "current_price": price_f,
            "previous_close": prev_f,
            "gap_percent": gap_frac,
            "volume": vol,
            "rel_volume": paced if paced is not None else raw_rvol,
        })
    updated.sort(key=lambda x: x["gap_percent"], reverse=True)
    return updated
