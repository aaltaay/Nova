"""Read-only views over the shared L1 owner map (kept out of ticks.py budget).

Every function takes the ``ticks._subs`` mapping so this module never imports
back into ``ibkr.ticks``. Nothing here touches ``ib.*`` or mutates ownership.
"""
from __future__ import annotations

import time
from typing import Any

from constants import IBKR_L1_STREAM_BUDGET


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def ticker_budget_status(
    subs: dict[str, dict[str, Any]], owners: tuple[str, ...],
) -> dict[str, Any]:
    """Live ``reqMktData`` lines vs ``IBKR_L1_STREAM_BUDGET`` (Error 101).

    One line per symbol. Owner counts can sum higher than ``reqMktData_lines``
    when scanner / HOD / detail / depth / listing share a stream.
    """
    from ibkr import session_errors as _se

    by_owner: dict[str, int] = {owner: 0 for owner in owners}
    for sub in subs.values():
        for owner in sub.get("owners") or ():
            key = str(owner)
            by_owner[key] = by_owner.get(key, 0) + 1
    lines = len(subs)
    limit = int(IBKR_L1_STREAM_BUDGET)
    return {
        "reqMktData_lines": lines,
        "reqMktData_by_owner": by_owner,
        "reqMktData_limit": limit,
        "reqMktData_remaining": max(0, limit - lines),
        "max_tickers_hit": bool(_se.max_tickers_hit()),
        "max_tickers_ts": _se.max_tickers_ts(),
    }


def last_quotes(
    subs: dict[str, dict[str, Any]], symbols: list[str] | None = None,
) -> dict[str, dict[str, Any]]:
    """Last known L1 price/ts for subscribed symbols (heartbeat use)."""
    wanted = None
    if symbols is not None:
        wanted = {(s or "").strip().upper() for s in symbols if s and str(s).strip()}
    out: dict[str, dict[str, Any]] = {}
    for sym, sub in subs.items():
        if wanted is not None and sym not in wanted:
            continue
        price = _as_float(sub.get("last_price"))
        if price is None:
            continue
        row = {
            "price": price,
            "last_update_ts": sub.get("last_update_ts"),
            "owners": set(sub.get("owners") or set()),
        }
        day_high = _as_float(sub.get("day_high"))
        if day_high is not None:
            row["day_high"] = day_high
        cum = sub.get("last_cum_volume")
        if cum is not None:
            try:
                vol = int(cum)
            except (TypeError, ValueError):
                vol = None
            if vol is not None and vol >= 0:
                row["volume"] = vol
        out[sym] = row
    return out


def get_day_high(subs: dict[str, dict[str, Any]], symbol: str) -> float | None:
    """IBKR L1 tick-6 day High for a subscribed symbol, if known."""
    sub = subs.get((symbol or "").strip().upper())
    if not sub:
        return None
    high = _as_float(sub.get("day_high"))
    if high is None:
        return None
    return high if high > 0 else None


def is_fresh(
    subs: dict[str, dict[str, Any]], symbol: str, max_age_sec: float,
) -> bool:
    """True if ``symbol`` has a live stream that ticked within ``max_age_sec``."""
    sub = subs.get(symbol.upper())
    if sub is None:
        return False
    last_ts = sub.get("last_update_ts")
    if last_ts is None:
        return False
    return (time.time() - last_ts) <= max_age_sec
