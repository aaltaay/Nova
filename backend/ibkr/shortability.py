"""IBKR shortability truth for Phase K (ADR 009).

Wraps tick-236 listing flags with fail-closed states + freshness TTL.
Alpaca shortable/ETB is never consulted here.
"""
from __future__ import annotations

import time
from typing import Any, Literal

from constants import (
    IBKR_SHORTABILITY_TTL_SEC,
    IBKR_SHORTABLE_EST_MIN_SHARES,
)
from ibkr import listing_flags as _listing_flags

ShortState = Literal["shortable_est", "thin", "htb_likely", "unknown"]

# Orderable for short_entry only when state is shortable_est and not stale.
_ORDERABLE_STATES = frozenset({"shortable_est"})


def state_from_shares(shares: float | None) -> ShortState:
    """Map IBKR shortableShares estimate to a Nova shortability state."""
    if shares is None:
        return "unknown"
    try:
        s = float(shares)
    except (TypeError, ValueError):
        return "unknown"
    if s != s:  # NaN
        return "unknown"
    if s <= 0:
        return "htb_likely"
    if s < float(IBKR_SHORTABLE_EST_MIN_SHARES):
        return "thin"
    return "shortable_est"


def enrich_ibkr_listing(raw: dict[str, Any], *, fetched_at: float | None = None) -> dict[str, Any]:
    """Attach state / fetched_at / stale / orderable to a listing_flags payload."""
    out = dict(raw or {})
    ts = float(fetched_at if fetched_at is not None else time.time())
    shares = out.get("shortable_shares")
    if out.get("error") or not out.get("connected"):
        state: ShortState = "unknown"
    else:
        state = state_from_shares(shares if isinstance(shares, (int, float)) else None)
        if state == "unknown" and shares is None and not out.get("qualified"):
            state = "unknown"
    age = max(0.0, time.time() - ts)
    stale = age > float(IBKR_SHORTABILITY_TTL_SEC)
    out["state"] = state
    out["fetched_at"] = ts
    out["age_sec"] = round(age, 3)
    out["stale"] = stale
    out["ttl_sec"] = float(IBKR_SHORTABILITY_TTL_SEC)
    out["orderable"] = (state in _ORDERABLE_STATES) and not stale
    if state == "shortable_est" and not stale:
        out.setdefault(
            "short_type_detail",
            "IBKR tick 236 estimate -- confirm fee / locate in TWS before shorting.",
        )
    elif state == "thin":
        out["short_type_detail"] = (
            "Thin locate (IBKR estimate) -- Nova refuses short entry (fail closed)."
        )
    elif state == "htb_likely":
        out["short_type_detail"] = (
            "HTB / locate likely (IBKR shortableShares≤0) -- Nova refuses short entry."
        )
    elif state == "unknown":
        out["short_type_detail"] = (
            "Shortability unknown (no tick / disconnected / error) -- refuse short entry."
        )
    if stale:
        out["short_type_detail"] = (
            f"Shortability stale (>{IBKR_SHORTABILITY_TTL_SEC:.0f}s) -- refresh before shorting."
        )
    return out


def fetch_shortability(symbol: str) -> dict[str, Any]:
    """Fresh shortability snapshot for ``symbol`` (sync; for validate + listing)."""
    raw = _listing_flags.fetch_listing_flags_sync(symbol)
    return enrich_ibkr_listing(raw, fetched_at=time.time())


def assert_shortable_for_order(snapshot: dict[str, Any] | None) -> tuple[bool, str, str | None]:
    """Return (ok, detail, reason_code) for a short-opening SELL."""
    if not snapshot:
        return False, "Shortability unavailable", "SHORT_STALE_BORROW"
    if snapshot.get("stale"):
        return False, "Shortability stale -- refresh before shorting", "SHORT_STALE_BORROW"
    state = snapshot.get("state") or "unknown"
    if state == "unknown":
        return False, "Shortability unknown -- refuse short entry", "SHORT_NOT_SHORTABLE"
    if state in ("thin", "htb_likely"):
        return (
            False,
            f"Not shortable for Nova orders (state={state})",
            "SHORT_NOT_SHORTABLE",
        )
    if state != "shortable_est" or not snapshot.get("orderable"):
        return False, f"Short entry refused (state={state})", "SHORT_NOT_SHORTABLE"
    return True, "OK", None
