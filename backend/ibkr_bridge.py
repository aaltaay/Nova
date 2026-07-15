"""
IBKR bridge helpers — discovery coroutine runner + table-reprice callbacks.

Extracted from ``main.py``. Cache mutations go through ``import main``.
"""
from __future__ import annotations

import logging
import time

import afterhours_discovery as _ah_discovery
import exchanges as _exchanges
import hod_momo as _hod_momo
from constants import IBKR_DISCOVERY_BRIDGE_TIMEOUT_SEC, IBKR_TABLE_REPRICE_MAX_SYMBOLS
from fundamentals import _fundamentals_cache
from ibkr import client as _ibkr_client
from ibkr import reprice as _ibkr_reprice
from ticker import _ticker_ws_clients

logger = logging.getLogger(__name__)


def _m():
    import main as _main
    return _main


def run_ibkr(coro):
    """Bridge an ibkr coroutine into this thread; [] on any failure."""
    try:
        return _ibkr_client.run_coro(coro, timeout=IBKR_DISCOVERY_BRIDGE_TIMEOUT_SEC)
    except Exception as exc:
        logger.warning("IBKR discovery bridge failed: %s", exc)
        return []


def enrich_ibkr_mover(entry: dict, news: dict[str, str]) -> dict:
    """Attach RVOL / news / fundamentals / exchange to an IBKR mover row."""
    m = _m()
    sym = entry["symbol"]
    avg_vol = m._avg_volume_cache.get(sym)
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
    """Symbols for the 1Hz table snapshot — scanner rows only (fast path)."""
    m = _m()
    if m._current_mode == "afterhours" and m._afterhours_cache:
        rows = m._afterhours_cache + m._gainer_cache + m._loser_cache
    elif m._gainer_cache or m._loser_cache:
        rows = m._gainer_cache + m._loser_cache
    else:
        rows = m._gapper_cache
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


def apply_table_quotes(quotes: dict) -> dict | None:
    """Apply async snapshot quotes onto scanner caches; return WS price_patch or None."""
    m = _m()
    gapper_in = [] if (m._gainer_cache or m._loser_cache) else m._gapper_cache
    result = _ibkr_reprice.apply_quote_patches(
        gapper_in, m._gainer_cache, m._loser_cache, quotes,
    )
    if result is None:
        return None
    gapper_cache, gainer_cache, loser_cache, now, rows = result
    if gapper_in and m._gapper_cache:
        m._gapper_cache = gapper_cache
        m._gapper_cache_ts = now
    if m._gainer_cache:
        m._gainer_cache = gainer_cache
        m._gainer_cache_ts = now
    if m._loser_cache:
        m._loser_cache = loser_cache
        m._loser_cache_ts = now
    if m._afterhours_cache and m._current_mode == "afterhours":
        m._afterhours_cache = _ah_discovery.reprice_afterhours_rows_ibkr(
            m._afterhours_cache, quotes, m._avg_volume_cache,
        )
        m._afterhours_cache_ts = now
        by_sym = {r["symbol"]: r for r in rows}
        for r in m._afterhours_cache:
            by_sym[r["symbol"]] = {
                "symbol": r["symbol"],
                "price": r.get("price") or r.get("current_price"),
                "change_pct": r.get("change_pct"),
                "change_abs": r.get("change_abs"),
                "volume": r.get("volume"),
                "gap_percent": r.get("gap_percent"),
            }
        rows = list(by_sym.values())

    trade_ts = time.time()
    for sym, q in quotes.items():
        price = (q or {}).get("price")
        if price is None:
            continue
        vol = (q or {}).get("volume")
        try:
            _hod_momo.on_trade_update(
                sym,
                float(price),
                trade_ts,
                volume=int(vol) if vol is not None else None,
            )
        except Exception:
            logger.exception("HOD Momo: IBKR table tick failed for %s", sym)

    return {"type": "price_patch", "ts": now, "stale": False, "rows": rows}
