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
        incoming_gap = r.get("gap_percent")
        try:
            incoming_gap_f = float(incoming_gap) if incoming_gap is not None else None
        except (TypeError, ValueError):
            incoming_gap_f = None
        open_f = _coerce_open(r.get("open"))
        out.append({
            "symbol": sym,
            "price": price_f,
            "prev_close": prev_f,
            "open": open_f,
            "change_pct": change_f,
            "change_abs": price_f - prev_f,
            "previous_close": prev_f,
            "current_price": price_f,
            "gap_percent": _session_gap_frac(open_f, prev_f, incoming_gap_f),
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


def reprice_afterhours_row_ibkr(
    row: dict,
    quote: dict,
    avg_volume_by_symbol: dict[str, float],
) -> dict | None:
    """Reprice one AH row. ``None`` means drop (below price floor).

    Change % is last vs prior close. Gap % is open vs prior close
    (D-002). Never copy change into gap.
    """
    q = quote or {}
    price = q.get("price", row.get("price"))
    prev_close = row.get("previous_close") or row.get("prev_close") or q.get("prev_close")
    if price is None or not prev_close:
        return row
    try:
        price_f = float(price)
        prev_f = float(prev_close)
    except (TypeError, ValueError):
        return row
    if price_f < SCANNER_MIN_PRICE or prev_f <= 0:
        return None
    vol = int(q["volume"]) if q.get("volume") is not None else int(row.get("volume") or 0)
    change_frac = (price_f - prev_f) / prev_f
    open_f = _coerce_open(q.get("open") if q.get("open") is not None else row.get("open"))
    prior_gap = row.get("gap_percent")
    try:
        prior_gap_f = float(prior_gap) if prior_gap is not None else None
    except (TypeError, ValueError):
        prior_gap_f = None
    avg = avg_volume_by_symbol.get(row["symbol"])
    paced = pace_relative_volume(vol, avg) if avg and vol else None
    raw_rvol = round(vol / avg, 2) if avg and avg > 0 and vol > 0 else row.get("rel_volume")
    return {
        **row,
        "price": price_f,
        "prev_close": prev_f,
        "open": open_f if open_f is not None else row.get("open"),
        "change_pct": change_frac,
        "change_abs": price_f - prev_f,
        "current_price": price_f,
        "previous_close": prev_f,
        "gap_percent": _session_gap_frac(open_f, prev_f, prior_gap_f),
        "volume": vol,
        "rel_volume": paced if paced is not None else raw_rvol,
    }


def reprice_afterhours_rows_ibkr(
    rows: list[dict],
    quotes: dict[str, dict],
    avg_volume_by_symbol: dict[str, float],
) -> list[dict]:
    """Apply IBKR snapshot quotes onto AH cache rows; recompute change + pace RVOL."""
    updated: list[dict] = []
    for r in rows:
        next_row = reprice_afterhours_row_ibkr(
            r, quotes.get(r["symbol"]) or {}, avg_volume_by_symbol,
        )
        if next_row is None:
            continue
        updated.append(next_row)
    # Rank by session move (AH gainers), not overnight gap. Gap used to equal
    # change_pct, so this key used to be the same number.
    updated.sort(key=_change_sort_key, reverse=True)
    return updated


def _coerce_open(raw) -> float | None:
    if raw is None:
        return None
    try:
        open_f = float(raw)
    except (TypeError, ValueError):
        return None
    return open_f if open_f else None


def _session_gap_frac(
    open_price: float | None,
    prev_close: float,
    fallback: float | None,
) -> float | None:
    """Open vs prior close. Never invent a gap from last / change_pct."""
    if open_price and prev_close:
        return (open_price - prev_close) / prev_close
    return fallback


def _change_sort_key(row: dict) -> float:
    """None-safe AH rank key (ADR 010 name-only rows have change_pct=None).

    Mapping None to -inf keeps unpriced rows at the bottom. A plain
    ``sort(key=lambda x: x["change_pct"])`` raises TypeError (PROBLEM_LOG
    2026-08-25, same crash when the key was still gap_percent).
    """
    change = row.get("change_pct")
    return change if change is not None else float("-inf")
