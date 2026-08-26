"""Read-time reference-column decoration for scanner mover rows.

Under ``discovery=ibkr`` the persistent roster (ADR 008) admits names only and
the L1 reprice path fills price / change / volume / gap. Nothing ever wrote
``rel_volume`` / ``market_cap`` / ``float`` / ``short_interest``, so those
columns rendered ``N/A`` or an em-dash for the whole session:
``ibkr_bridge.enrich_ibkr_mover`` existed but was never called, and both
functions that do fetch yfinance fundamentals (``universe.enrich_gappers`` and
``scanner_runners.movers``) return early when discovery is ibkr.

Decoration happens at *serialization* time rather than in the cache so a frozen
table's stored membership, rank, and values stay immutable (ADR 008) -- these
columns are a view over the row, not a mutation of it.

Average volume comes from yfinance, never ``state.avg_volume_cache``. Alpaca's
IEX daily bars capture only a sliver of consolidated volume for the thin
low-float names these tables are full of and already blew RVOL up 100x-3000x
once (PROBLEM_LOG 2026-07-16: CJMB 7016x, LBGJ 1526x, ATPC 3025x).
"""
from __future__ import annotations

from typing import Any

# yfinance fundamentals key → scanner row key.
_FUND_FIELDS: tuple[tuple[str, str], ...] = (
    ("market_cap", "market_cap"),
    ("float", "float_shares"),
    ("short_interest", "short_interest"),
    ("short_ratio", "short_ratio"),
)


def relative_volume(volume: Any, avg_volume: float | None) -> float | None:
    """Session volume over yfinance average volume, or None when unknowable."""
    try:
        vol = float(volume or 0)
        avg = float(avg_volume or 0)
    except (TypeError, ValueError):
        return None
    if vol <= 0 or avg <= 0:
        return None
    return round(vol / avg, 2)


def decorate_rows(rows: list[dict] | None) -> list[dict]:
    """Return new rows with reference columns filled from the yfinance cache.

    Never mutates ``rows`` and never overwrites a value another runner already
    supplied (the afterhours runner does its own enrichment) -- a cold cache
    must not blank a column that was already honest.
    """
    if not rows:
        return list(rows or [])
    from fundamentals import _fundamentals_cache
    from hod_momo_enrichment import ibkr_avg_volume

    out: list[dict] = []
    for row in rows:
        sym = (row.get("symbol") or "").strip().upper()
        if not sym:
            out.append(dict(row))
            continue
        entry = dict(row)
        fund = _fundamentals_cache.get(sym) or {}
        for row_key, fund_key in _FUND_FIELDS:
            if entry.get(row_key) is None:
                entry[row_key] = fund.get(fund_key)
        if entry.get("rel_volume") is None:
            entry["rel_volume"] = relative_volume(
                entry.get("volume"), ibkr_avg_volume(sym),
            )
        out.append(entry)
    return out
