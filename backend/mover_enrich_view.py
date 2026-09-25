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
columns are a view over the row, not a mutation of it. NEWS
(``has_news`` / ``newest_headline_at``) is stamped the same way from
``scanner_news_badge`` so IBKR discovery can light the flame without a roster
write.

Float credibility (#532): each row carries ``shares_outstanding``, the
``short_interest_ts`` its short interest is from (only when the row's figure is
the cached one, so a date is never pinned on another report), and
``float_contradicted`` / ``float_contradicted_reason`` from
``fundamentals.float_credibility`` over the row's own float and shares
outstanding, and ``short_above_float`` / ``short_above_float_reason`` (a warning
no gate reads) over the row's own float and short interest.
The max-float gates that grade these rows -- the Five Pillars float pillar, the
Contenders float score, ``LEADERS_RULES`` through the recorded leaderboard row
-- read the flag and ``shares_outstanding`` through ``strategy.float_gate``.

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
    ("shares_outstanding", "shares_outstanding"),
    ("short_interest", "short_interest"),
    ("short_ratio", "short_ratio"),
    ("earnings_date", "earnings_date"),
    ("earnings_estimated", "earnings_estimated"),
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


def stamp_float_credibility(entry: dict, fund: dict) -> None:
    """The row's short-interest date, whether its float is contradicted, and the short-above-float
    warning (#532). Mutates ``entry``."""
    from fundamentals import float_credibility, short_above_float

    if entry.get("short_interest_ts") is None:
        own = entry.get("short_interest") is not None and entry.get("short_interest") == fund.get("short_interest")
        entry["short_interest_ts"] = fund.get("short_interest_ts") if own else None
    entry["float_contradicted"], entry["float_contradicted_reason"] = float_credibility(
        entry.get("float"), entry.get("shares_outstanding"), fund.get("held_percent_insiders"),
    )
    entry["short_above_float"], entry["short_above_float_reason"] = short_above_float(
        entry.get("float"), entry.get("short_interest"),
    )


def decorate_rows(rows: list[dict] | None) -> list[dict]:
    """Return new rows with reference columns filled from the yfinance cache.

    Never mutates ``rows`` and never overwrites a value another runner already
    supplied (the afterhours runner does its own enrichment) -- a cold cache
    must not blank a column that was already honest.
    """
    if not rows:
        return list(rows or [])
    from earnings_window import earnings_day_offset, earnings_session
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
        stamp_float_credibility(entry, fund)
        if entry.get("rel_volume") is None:
            entry["rel_volume"] = relative_volume(
                entry.get("volume"), ibkr_avg_volume(sym),
            )
        if entry.get("earnings_day_offset") is None:
            entry["earnings_day_offset"] = earnings_day_offset(
                fund.get("earnings_ts"),
                earnings_date=fund.get("earnings_date") or entry.get("earnings_date"),
            )
        if entry.get("earnings_session") is None:
            entry["earnings_session"] = earnings_session(fund.get("earnings_ts"))
        from scanner_news_badge import stamp_row
        stamp_row(entry)
        from catalysts.board import stamp_row as stamp_catalyst
        stamp_catalyst(entry)
        out.append(entry)
    return out
