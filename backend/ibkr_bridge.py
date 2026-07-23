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
from constants import (
    HOD_MOMO_ACTIVE_HOT_PER_TICK,
    HOD_MOMO_ACTIVE_SET_CAPACITY,
    IBKR_DISCOVERY_BRIDGE_TIMEOUT_SEC,
    IBKR_L1_ACTIVE_TAB_MAX,
    IBKR_TABLE_REPRICE_CHUNK_SIZE,
    IBKR_TABLE_REPRICE_MAX_SYMBOLS,
)
from ibkr import discovery as _ibkr_discovery
from fundamentals import _fundamentals_cache
from ibkr import client as _ibkr_client
from ibkr import reprice as _ibkr_reprice
from ibkr import scanner_session as _ss
from runtime_state import get_runtime_state
from ticker import _ticker_ws_clients

logger = logging.getLogger(__name__)


class IbkrBridgeError(RuntimeError):
    """Thread→asyncio IBKR bridge timed out or raised."""


def run_ibkr(coro, *, on_error: str = "none", label: str = "ibkr"):
    """Bridge an ibkr coroutine into this thread.

    ``on_error`` (default ``none`` — fail loud / keep last-good):
      - ``none`` — return ``None`` so callers can keep last-good caches
      - ``empty`` — return ``[]`` (legacy list-shaped callers only)
      - ``raise`` — raise ``IbkrBridgeError`` (never silent)
    """
    try:
        return _ibkr_client.run_coro(coro, timeout=IBKR_DISCOVERY_BRIDGE_TIMEOUT_SEC, label=label)
    except Exception as exc:
        # TimeoutError / CancelledError often stringify to "" — always log type+repr.
        detail = f"{type(exc).__name__}: {exc!r}"
        logger.error(
            "IBKR discovery bridge failed (%s): %s",
            label,
            detail,
            exc_info=True,
        )
        try:
            state = get_runtime_state()
            state.ibkr_bridge_last_error = f"{label}: {detail}"
            state.ibkr_bridge_last_error_ts = time.time()
        except Exception:
            logger.debug("could not record ibkr_bridge_last_error", exc_info=True)
        if on_error == "raise":
            raise IbkrBridgeError(detail) from exc
        if on_error == "none":
            return None
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
    """Legacy mode-union symbol list (cold-path / tests). Prefer ``symbols_for_tab``."""
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


def symbols_for_tab(tab: str) -> list[str]:
    """Canonical active-tab symbol list from runtime caches (never trust clients).

    ADR 008: a frozen table must not consume scanner-owner L1 — return [].
    HOD-owner L1 remains independent via ``hod_stream_symbols``.
    """
    from ibkr import scanner_session as _ss
    from runtime_state.state import TABLE_STATE_FROZEN

    state = get_runtime_state()
    t = (tab or "none").strip().lower()
    if t in (
        _ss.TABLE_GAPPERS, _ss.TABLE_GAINERS, _ss.TABLE_LOSERS, _ss.TABLE_AFTERHOURS,
    ):
        if _ss.table_attr(state, t).state == TABLE_STATE_FROZEN:
            return []
    if t == "gappers":
        rows = state.gapper_cache
    elif t == "gainers":
        rows = state.gainer_cache
    elif t == "losers":
        rows = state.loser_cache
    elif t == "afterhours":
        rows = state.afterhours_cache
    else:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for r in rows or []:
        sym = (r.get("symbol") or "").strip().upper()
        if sym and sym not in seen:
            seen.add(sym)
            out.append(sym)
        if len(out) >= IBKR_L1_ACTIVE_TAB_MAX:
            break
    return out


def refresh_hod_active_set() -> list[str]:
    """Rebuild the deterministic HOD active set (Gappers/Gainers/Afterhours/Former).

    Always recomputes from the live table caches — no memoization. A prior
    version cached this on an ``id()`` + ``len()`` signature of the three
    table caches, which permanently stopped updating once Gappers/Gainers/
    Afterhours all freeze for the day (09:30/16:00/20:00 ET, ADR 008): frozen
    caches are never reassigned again, so the signature never changed again,
    silently locking HOD's tracked pool to whatever it last computed and
    starving `hod_momo.on_trade_update` for any symbol admitted after that
    (see PROBLEM_LOG 2026-07-23). `build_active_set` is a pure in-memory
    merge/rank/dedupe over at most ~40-70 small dict rows — cheap enough on
    every tick that memoizing it isn't worth the staleness risk.
    """
    state = get_runtime_state()
    try:
        import hod_momo_former as _former

        priority = _former.former_momo_priority_symbols()
    except Exception:
        priority = []
    snap = _hod_active.build_active_set(
        gapper_rows=state.gapper_cache,
        gainer_rows=state.gainer_cache,
        # Current-session retained AH union — not gated on current_mode, so
        # AH runners stay HOD-eligible after the session flips to "closed".
        afterhours_rows=state.afterhours_cache,
        priority_symbols=priority,
        capacity=HOD_MOMO_ACTIVE_SET_CAPACITY,
    )
    return list(snap.active)


def hod_stream_symbols() -> list[str]:
    """Reserved HOD L1 pool (quota-selected; includes off-table volume seeds)."""
    return refresh_hod_active_set()


def active_reprice_batch() -> list[str]:
    """Legacy fair batch helper (cold snapshot path / tests)."""
    active = refresh_hod_active_set()
    hot = set(get_ibkr_detail_symbols())
    for sym in active[:HOD_MOMO_ACTIVE_HOT_PER_TICK]:
        hot.add(sym)
    return _hod_active.select_fair_batch(
        active,
        hot=hot,
        chunk_size=IBKR_TABLE_REPRICE_CHUNK_SIZE,
        hot_n=HOD_MOMO_ACTIVE_HOT_PER_TICK,
    )


def apply_l1_quote(
    symbol: str,
    price: float,
    volume: int | None,
    prev_close: float | None,
    ts_unix: float,
) -> dict | None:
    """Apply one L1 tick onto scanner caches + HOD; return patch row fields.

    ADR 008: HOD's reserved L1 pool keeps ticking retained symbols after
    their table freezes (09:30/16:00/20:00). Each cache write below is
    gated on that table's ``TableState`` so a HOD-only tick can never mutate
    a table the user is told is immutable for the rest of the session.
    """
    sym = (symbol or "").strip().upper()
    if not sym or price is None:
        return None
    state = get_runtime_state()
    q = {
        "price": float(price),
        "prev_close": prev_close,
        "volume": volume if volume is not None else 0,
    }
    now = float(ts_unix)
    patch: dict = {
        "symbol": sym,
        "price": float(price),
        "volume": volume,
        "quote_ts": now,
    }

    def _touch_row(row: dict, reprice_fn) -> dict:
        return reprice_fn(row, q) if row.get("symbol", "").upper() == sym else row

    if state.gainer_cache and not _ss.is_table_frozen(state, _ss.TABLE_GAINERS):
        state.gainer_cache = [
            _touch_row(r, _ibkr_discovery.reprice_mover_row) for r in state.gainer_cache
        ]
        state.gainer_cache_ts = now
        for r in state.gainer_cache:
            if (r.get("symbol") or "").upper() == sym:
                patch.update({
                    "change_pct": r.get("change_pct"),
                    "change_abs": r.get("change_abs"),
                    "gap_percent": r.get("gap_percent"),
                    "volume": r.get("volume", volume),
                })
                break
    if state.loser_cache and not _ss.is_table_frozen(state, _ss.TABLE_LOSERS):
        state.loser_cache = [
            _touch_row(r, _ibkr_discovery.reprice_mover_row) for r in state.loser_cache
        ]
        state.loser_cache_ts = now
    if (
        state.gapper_cache
        and not (state.gainer_cache or state.loser_cache)
        and not _ss.is_table_frozen(state, _ss.TABLE_GAPPERS)
    ):
        state.gapper_cache = [
            _touch_row(r, _ibkr_discovery.reprice_gapper_row) for r in state.gapper_cache
        ]
        state.gapper_cache_ts = now
        for r in state.gapper_cache:
            if (r.get("symbol") or "").upper() == sym:
                patch.update({
                    "change_pct": r.get("change_pct"),
                    "change_abs": r.get("change_abs"),
                    "gap_percent": r.get("gap_percent"),
                    "volume": r.get("volume", volume),
                })
                break
    if (
        state.afterhours_cache
        and state.current_mode == "afterhours"
        and not _ss.is_table_frozen(state, _ss.TABLE_AFTERHOURS)
    ):
        state.afterhours_cache = _ah_discovery.reprice_afterhours_rows_ibkr(
            state.afterhours_cache, {sym: q}, state.avg_volume_cache,
        )
        state.afterhours_cache_ts = now
        for r in state.afterhours_cache:
            if (r.get("symbol") or "").upper() == sym:
                patch.update({
                    "change_pct": r.get("change_pct"),
                    "change_abs": r.get("change_abs"),
                    "gap_percent": r.get("gap_percent"),
                    "volume": r.get("volume", volume),
                })
                break

    active = set(_hod_active.get_active_symbols())
    if not active:
        active = {sym}
        refresh_hod_active_set()
        active = set(_hod_active.get_active_symbols()) or {sym}
    if sym in active:
        try:
            from ibkr import ticks as _ticks

            _hod_active.note_quote(sym, now)
            _hod_momo.on_trade_update(
                sym,
                float(price),
                now,
                volume=int(volume) if volume is not None else None,
                day_high=_ticks.get_day_high(sym),
            )
        except Exception:
            logger.exception("HOD Momo: IBKR L1 tick failed for %s", sym)
    return patch


def apply_table_quotes(quotes: dict) -> dict | None:
    """Apply async snapshot quotes onto scanner caches; feed HOD for active set."""
    state = get_runtime_state()
    gapper_frozen = _ss.is_table_frozen(state, _ss.TABLE_GAPPERS)
    gapper_in = (
        [] if (state.gainer_cache or state.loser_cache or gapper_frozen) else state.gapper_cache
    )
    result = _ibkr_reprice.apply_quote_patches(
        gapper_in, state.gainer_cache, state.loser_cache, quotes,
    )
    if result is None:
        return None
    gapper_cache, gainer_cache, loser_cache, now, rows = result
    if gapper_in and state.gapper_cache and not gapper_frozen:
        state.gapper_cache = gapper_cache
        state.gapper_cache_ts = now
    if state.gainer_cache and not _ss.is_table_frozen(state, _ss.TABLE_GAINERS):
        state.gainer_cache = gainer_cache
        state.gainer_cache_ts = now
    if state.loser_cache and not _ss.is_table_frozen(state, _ss.TABLE_LOSERS):
        state.loser_cache = loser_cache
        state.loser_cache_ts = now
    if (
        state.afterhours_cache
        and state.current_mode == "afterhours"
        and not _ss.is_table_frozen(state, _ss.TABLE_AFTERHOURS)
    ):
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
                day_high=(q or {}).get("high"),
            )
        except Exception:
            logger.exception("HOD Momo: IBKR table tick failed for %s", sym)

    return {"type": "price_patch", "ts": now, "stale": False, "rows": rows}
