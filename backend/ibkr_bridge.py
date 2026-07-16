"""
IBKR bridge helpers — discovery coroutine runner + table-reprice callbacks.
"""
from __future__ import annotations

import logging
import time

import afterhours_discovery as _ah_discovery
import exchanges as _exchanges
import hod_momo as _hod_momo
import hod_momo_active as _hod_active
import hod_momo_universe as _hod_uni
from constants import (
    HOD_MOMO_ACTIVE_HOT_PER_TICK,
    HOD_MOMO_ACTIVE_SET_CAPACITY,
    IBKR_DISCOVERY_BRIDGE_TIMEOUT_SEC,
    IBKR_TABLE_REPRICE_CHUNK_SIZE,
    IBKR_TABLE_REPRICE_MAX_SYMBOLS,
)
from fundamentals import _fundamentals_cache
from ibkr import client as _ibkr_client
from ibkr import reprice as _ibkr_reprice
from runtime_state import get_runtime_state
from ticker import _ticker_ws_clients

logger = logging.getLogger(__name__)


def run_ibkr(coro):
    """Bridge an ibkr coroutine into this thread; [] on any failure."""
    try:
        return _ibkr_client.run_coro(coro, timeout=IBKR_DISCOVERY_BRIDGE_TIMEOUT_SEC)
    except Exception as exc:
        logger.warning("IBKR discovery bridge failed: %s", exc)
        return []


def enrich_ibkr_mover(entry: dict, news: dict[str, str]) -> dict:
    """Attach RVOL / news / fundamentals / exchange to an IBKR mover row."""
    state = get_runtime_state()
    sym = entry["symbol"]
    avg_vol = state.avg_volume_cache.get(sym)
    vol = entry["volume"]
    fund = _fundamentals_cache.get(sym, {})
    entry["rel_volume"] = round(vol / avg_vol, 2) if avg_vol and avg_vol > 0 and vol > 0 else None
    entry["has_news"] = sym in news
    entry["newest_headline_at"] = news.get(sym)
    entry["market_cap"] = fund.get("market_cap")
    entry["float"] = fund.get("float_shares")
    entry["short_interest"] = fund.get("short_interest")
    entry["short_ratio"] = fund.get("short_ratio")
    return _exchanges.attach_exchange(entry)


def get_ibkr_detail_symbols() -> list[str]:
    """Symbols with an open ticker-detail WebSocket right now (usually 0-2)."""
    return [sym for sym, clients in _ticker_ws_clients.items() if clients]


def table_reprice_symbols() -> list[str]:
    """Symbols for the 1Hz table snapshot — scanner rows only (UI path)."""
    state = get_runtime_state()
    if state.current_mode == "afterhours" and state.afterhours_cache:
        rows = state.afterhours_cache + state.gainer_cache + state.loser_cache
    elif state.gainer_cache or state.loser_cache:
        rows = state.gainer_cache + state.loser_cache
    else:
        rows = state.gapper_cache
    out: list[str] = []
    seen: set[str] = set()
    for r in rows:
        sym = (r.get("symbol") or "").strip().upper()
        if sym and sym not in seen:
            seen.add(sym)
            out.append(sym)
        if len(out) >= IBKR_TABLE_REPRICE_MAX_SYMBOLS:
            break
    return out


def refresh_hod_active_set() -> list[str]:
    """Rebuild capacity-bounded active evaluation set from discovery + scanners."""
    state = get_runtime_state()
    discovery = set(state.hod_momo_universe)
    snap = _hod_active.build_active_set(
        discovery=discovery,
        gainer_rows=state.gainer_cache,
        loser_rows=state.loser_cache,
        gapper_rows=state.gapper_cache,
        afterhours_rows=state.afterhours_cache if state.current_mode == "afterhours" else None,
        seed_symbols=_hod_uni.get_seed_symbols(),
        detail_symbols=get_ibkr_detail_symbols(),
        capacity=HOD_MOMO_ACTIVE_SET_CAPACITY,
    )
    return snap.active


def active_reprice_batch() -> list[str]:
    """Fair hot + age-rotating tail batch for HOD evaluation (≤ chunk size)."""
    active = refresh_hod_active_set()
    hot = set(get_ibkr_detail_symbols())
    # Top of active list is already priority-ordered (open ticker / top gainers).
    for sym in active[:HOD_MOMO_ACTIVE_HOT_PER_TICK]:
        hot.add(sym)
    return _hod_active.select_fair_batch(
        active,
        hot=hot,
        chunk_size=IBKR_TABLE_REPRICE_CHUNK_SIZE,
        hot_n=HOD_MOMO_ACTIVE_HOT_PER_TICK,
    )


def apply_table_quotes(quotes: dict) -> dict | None:
    """Apply async snapshot quotes onto scanner caches; feed HOD for active set."""
    state = get_runtime_state()
    gapper_in = [] if (state.gainer_cache or state.loser_cache) else state.gapper_cache
    result = _ibkr_reprice.apply_quote_patches(
        gapper_in, state.gainer_cache, state.loser_cache, quotes,
    )
    if result is None:
        return None
    gapper_cache, gainer_cache, loser_cache, now, rows = result
    if gapper_in and state.gapper_cache:
        state.gapper_cache = gapper_cache
        state.gapper_cache_ts = now
    if state.gainer_cache:
        state.gainer_cache = gainer_cache
        state.gainer_cache_ts = now
    if state.loser_cache:
        state.loser_cache = loser_cache
        state.loser_cache_ts = now
    if state.afterhours_cache and state.current_mode == "afterhours":
        state.afterhours_cache = _ah_discovery.reprice_afterhours_rows_ibkr(
            state.afterhours_cache, quotes, state.avg_volume_cache,
        )
        state.afterhours_cache_ts = now
        by_sym = {r["symbol"]: r for r in rows}
        for r in state.afterhours_cache:
            by_sym[r["symbol"]] = {
                "symbol": r["symbol"],
                "price": r.get("price") or r.get("current_price"),
                "change_pct": r.get("change_pct"),
                "change_abs": r.get("change_abs"),
                "volume": r.get("volume"),
                "gap_percent": r.get("gap_percent"),
            }
        rows = list(by_sym.values())

    active = set(_hod_active.get_active_symbols())
    # If active set not yet built this tick, still evaluate quoted symbols
    # (bootstrap) then refresh for next tick.
    if not active:
        active = set(quotes.keys())

    trade_ts = time.time()
    for sym, q in quotes.items():
        price = (q or {}).get("price")
        if price is None:
            continue
        sym_u = (sym or "").strip().upper()
        if active and sym_u not in active:
            # Scanner UI patch only — do not pretend uncovered discovery is live HOD.
            continue
        vol = (q or {}).get("volume")
        try:
            _hod_active.note_quote(sym_u, trade_ts)
            _hod_momo.on_trade_update(
                sym_u,
                float(price),
                trade_ts,
                volume=int(vol) if vol is not None else None,
            )
        except Exception:
            logger.exception("HOD Momo: IBKR table tick failed for %s", sym)

    return {"type": "price_patch", "ts": now, "stale": False, "rows": rows}
