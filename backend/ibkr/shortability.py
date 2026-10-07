"""IBKR shortability truth for Phase K (ADR 009).

Wraps tick-236 listing flags with fail-closed states + freshness TTL.
Alpaca shortable/ETB is never consulted here.

The execution door never asks IBKR (ADR 048): ``for_order`` is a cache read, and a stale or
missing read asks IBKR again on a worker thread (``request_refresh``) so the next try finds one.
An open Trader tab re-reads its stock's borrow every ``IBKR_SHORTABILITY_REFRESH_SEC``, under the
TTL, so the read it holds never goes stale between the socket's wakes.
"""
from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Literal

from constants import (
    IBKR_SHORTABILITY_TTL_SEC,
    IBKR_SHORTABLE_EST_MIN_SHARES,
)
from constants_ibkr import (
    IBKR_SHORTABILITY_REFRESH_SEC,
    IBKR_SHORTABILITY_REFRESH_WORKERS,
    IBKR_SHORTABILITY_RETRY_UNKNOWN_SEC,
)
from ibkr import listing_flags as _listing_flags

logger = logging.getLogger(__name__)

ShortState = Literal["shortable_est", "thin", "htb_likely", "unknown"]

# Orderable for short_entry only when state is shortable_est and not stale.
_ORDERABLE_STATES = frozenset({"shortable_est"})
# The last snapshot read per symbol (ADR 036): the stock read shows it with its age, never waits.
_last: dict[str, dict[str, Any]] = {}


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
    snap = enrich_ibkr_listing(raw, fetched_at=time.time())
    _last[(symbol or "").strip().upper()] = snap
    return snap


def cached(symbol: str) -> dict[str, Any] | None:
    """The last snapshot read for ``symbol``, its age and staleness as of now; None when none was read.

    A read, never a wait: ``fetch_shortability`` asks IBKR (up to its timeout) -- the Trader's ticker
    socket does that while the tab is open.
    """
    snap = _last.get((symbol or "").strip().upper())
    if snap is None:
        return None
    return enrich_ibkr_listing(snap, fetched_at=float(snap.get("fetched_at") or 0.0))


def refresh_due(snapshot: dict[str, Any] | None, age_sec: float) -> bool:
    """Whether a socket that read ``snapshot`` ``age_sec`` ago should ask IBKR again.

    A known state is re-read before its TTL runs out (ADR 048: the door reads the cache only).
    """
    state = (snapshot or {}).get("state") or "unknown"
    wait = IBKR_SHORTABILITY_RETRY_UNKNOWN_SEC if state == "unknown" else IBKR_SHORTABILITY_REFRESH_SEC
    return age_sec >= float(wait)


def for_order(symbol: str) -> dict[str, Any] | None:
    """The cached read the execution door judges a short entry by: ``cached``, never a wait.

    None when nothing was read for ``symbol``. A missing or stale read asks IBKR again in the
    background, so the next try can find a fresh one.
    """
    snap = cached(symbol)
    if snap is None or snap.get("stale"):
        request_refresh(symbol)
    return snap


_pool: ThreadPoolExecutor | None = None
_pool_lock = threading.Lock()
_refreshing: set[str] = set()


def _refresh(symbol: str) -> None:
    try:
        fetch_shortability(symbol)
    except Exception:
        logger.warning("shortability: the background read of %s failed", symbol, exc_info=True)
    finally:
        with _pool_lock:
            _refreshing.discard(symbol)


def request_refresh(symbol: str) -> bool:
    """Ask IBKR for ``symbol``'s borrow on a worker thread; False when one is already on its way."""
    sym = (symbol or "").strip().upper()
    if not sym:
        return False
    global _pool
    with _pool_lock:
        if sym in _refreshing:
            return False
        _refreshing.add(sym)
        if _pool is None:
            _pool = ThreadPoolExecutor(
                max_workers=IBKR_SHORTABILITY_REFRESH_WORKERS, thread_name_prefix="nova-borrow",
            )
        pool = _pool
    pool.submit(_refresh, sym)
    return True


def remember_for_tests(symbol: str, snapshot: dict[str, Any]) -> None:
    """Seed the cache as a read would (tests only)."""
    _last[(symbol or "").strip().upper()] = snapshot


def reset_for_tests() -> None:
    with _pool_lock:
        _refreshing.clear()
    _last.clear()


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
