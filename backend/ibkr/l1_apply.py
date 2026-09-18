"""O(1) L1 apply onto scanner caches (D-019).

``apply_l1_quote`` used to list-comprehend every live roster on each IB tick.
This module keeps a ``symbol -> row index`` per table and patches one slot.
"""
from __future__ import annotations

import logging

import afterhours_discovery as _ah_discovery
from ibkr import discovery as _ibkr_discovery
from ibkr import scanner_session as _ss
from runtime_state import get_runtime_state

logger = logging.getLogger(__name__)

# table -> (id(rows), len(rows), symbol->index). Rebuilt when the roster list
# is replaced (commit) or its length changes -- never on a single-tick patch.
_TABLE_INDEX: dict[str, tuple[int, int, dict[str, int]]] = {}


def reset_row_indexes_for_tests() -> None:
    _TABLE_INDEX.clear()


def _index(table: str, rows: list[dict]) -> dict[str, int]:
    key = id(rows)
    n = len(rows)
    cached = _TABLE_INDEX.get(table)
    if cached is not None and cached[0] == key and cached[1] == n:
        return cached[2]
    idx = {
        (r.get("symbol") or "").strip().upper(): i
        for i, r in enumerate(rows)
        if (r.get("symbol") or "").strip()
    }
    _TABLE_INDEX[table] = (key, n, idx)
    return idx


def _lookup(table: str, rows: list[dict] | None, sym: str) -> int | None:
    if not rows:
        return None
    idx = _index(table, rows)
    at = idx.get(sym)
    if at is None or at >= len(rows):
        return None
    return at


def _patch_fields(patch: dict, row: dict, volume) -> None:
    patch.update({
        "change_pct": row.get("change_pct"),
        "change_abs": row.get("change_abs"),
        "gap_percent": row.get("gap_percent"),
        "volume": row.get("volume", volume),
    })


def _maybe_refresh_gappers(state, sym: str, gainer_row: dict) -> None:
    """Rebuild the Gappers projection only when membership may flip."""
    from ibkr import gapper_view

    gapper_rows = state.gapper_cache or []
    was = _lookup(_ss.TABLE_GAPPERS, gapper_rows, sym) is not None
    now = gapper_view.row_qualifies(gainer_row)
    if was != now:
        try:
            gapper_view.refresh(state, source="l1")
        except Exception:
            logger.debug("apply_l1_quote: gapper view refresh failed", exc_info=True)
        return
    if not was:
        return
    at = _lookup(_ss.TABLE_GAPPERS, gapper_rows, sym)
    if at is None:
        return
    prev = gainer_row.get("prev_close")
    price = gainer_row.get("price")
    gapper_rows[at] = {
        **gainer_row,
        "previous_close": prev,
        "current_price": price,
        "gap_percent": gainer_row.get("change_pct"),
    }


def apply_l1_quote(
    symbol: str,
    price: float,
    volume: int | None,
    prev_close: float | None,
    ts_unix: float,
    *,
    quote_quality: str | None = None,
    open_price: float | None = None,
    get_state=None,
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
    state = (get_state or get_runtime_state)()
    q = {
        "price": float(price),
        "prev_close": prev_close,
        "volume": volume if volume is not None else 0,
        "open": open_price,
    }
    now = float(ts_unix)
    patch: dict = {
        "symbol": sym,
        "price": float(price),
        "volume": volume,
        "quote_ts": now,
    }
    if quote_quality:
        patch["quote_quality"] = quote_quality

    if state.gainer_cache and not _ss.is_table_frozen(state, _ss.TABLE_GAINERS):
        at = _lookup(_ss.TABLE_GAINERS, state.gainer_cache, sym)
        if at is not None:
            row = _ibkr_discovery.reprice_mover_row(state.gainer_cache[at], q)
            state.gainer_cache[at] = row
            state.gainer_cache_ts = now
            _patch_fields(patch, row, volume)
            _maybe_refresh_gappers(state, sym, row)

    if state.loser_cache and not _ss.is_table_frozen(state, _ss.TABLE_LOSERS):
        at = _lookup(_ss.TABLE_LOSERS, state.loser_cache, sym)
        if at is not None:
            state.loser_cache[at] = _ibkr_discovery.reprice_mover_row(
                state.loser_cache[at], q,
            )
            state.loser_cache_ts = now

    if (
        state.gapper_cache
        and not (state.gainer_cache or state.loser_cache)
        and not _ss.is_table_frozen(state, _ss.TABLE_GAPPERS)
    ):
        at = _lookup(_ss.TABLE_GAPPERS, state.gapper_cache, sym)
        if at is not None:
            row = _ibkr_discovery.reprice_gapper_row(state.gapper_cache[at], q)
            state.gapper_cache[at] = row
            state.gapper_cache_ts = now
            _patch_fields(patch, row, volume)

    if (
        state.afterhours_cache
        and state.current_mode == "afterhours"
        and not _ss.is_table_frozen(state, _ss.TABLE_AFTERHOURS)
    ):
        at = _lookup(_ss.TABLE_AFTERHOURS, state.afterhours_cache, sym)
        if at is not None:
            row = _ah_discovery.reprice_afterhours_row_ibkr(
                state.afterhours_cache[at], q, state.avg_volume_cache,
            )
            if row is not None:
                state.afterhours_cache[at] = row
                state.afterhours_cache_ts = now
                _patch_fields(patch, row, volume)

    if state.large_cap_cache:
        at = _lookup(_ss.TABLE_LARGE_CAP, state.large_cap_cache, sym)
        if at is not None:
            import large_cap_reprice as _lc_reprice

            state.large_cap_cache, lc_patch = _lc_reprice.apply_l1_tick(
                state.large_cap_cache, sym, q, now, at=at,
            )
            state.large_cap_cache_ts = now
            if lc_patch:
                patch.update(lc_patch)

    from hod_tick_feed import feed_hod_on_tick

    feed_hod_on_tick(sym, price, volume, now)
    try:
        from volume_boost import observe_l1

        observe_l1(sym, volume, float(price), now)
    except Exception:
        logger.exception("volume_boost: observe_l1 failed for %s", sym)
    return patch
