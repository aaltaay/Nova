"""Hydration + shadow parity for ADR 008 persistent scanner stream."""
from __future__ import annotations

import logging
import time
from typing import Any

from constants import GAPPER_MIN_GAP_PCT, IBKR_QUOTE_BATCH_TIMEOUT_SEC, SCANNER_MIN_PRICE
from ibkr import client as _client
from ibkr import discovery as _discovery
from ibkr import scanner_session as _session
from metrics.op_metrics import timed
from runtime_state import get_runtime_state

logger = logging.getLogger(__name__)

# Per-table known-good rows, keyed by symbol. Persists across batches so an
# unchanged symbol's row is preserved rather than re-quoted (plan §2: "cold
# reqTickersAsync hydration only for newly admitted symbols"). Live price
# refresh for displayed/live rows comes from the separate L1 hot path once a
# table is active — this cold path only backfills roster/rank for new names.
_known_rows: dict[str, dict[str, dict]] = {}
_known_session: dict[str, str] = {}


def _known_for(table: str, session_key: str) -> dict[str, dict]:
    if _known_session.get(table) != session_key:
        _known_rows[table] = {}
        _known_session[table] = session_key
    return _known_rows.setdefault(table, {})


def reset_known(table: str | None = None) -> None:
    """Clear cached known-good rows (process shutdown / lease reopen)."""
    if table is None:
        _known_rows.clear()
        _known_session.clear()
    else:
        _known_rows.pop(table, None)
        _known_session.pop(table, None)


def row_from_quote(sym: str, q: dict, *, as_gapper: bool) -> dict | None:
    price, prev_close = q.get("price"), q.get("prev_close")
    if price is None or price < SCANNER_MIN_PRICE or not prev_close:
        return None
    change = (price - prev_close) / prev_close
    if as_gapper and change * 100 < GAPPER_MIN_GAP_PCT:
        return None
    base = {
        "symbol": sym,
        "price": price,
        "prev_close": prev_close,
        "change_pct": change,
        "change_abs": price - prev_close,
        "volume": q.get("volume", 0),
        "exchange": q.get("exchange"),
    }
    if as_gapper:
        base.update({
            "previous_close": prev_close,
            "current_price": price,
            "gap_percent": change,
        })
    else:
        open_price = q.get("open")
        base["gap_percent"] = (
            (open_price - prev_close) / prev_close if open_price and prev_close else None
        )
    return base


async def hydrate_rows(
    symbols: list[str],
    *,
    table: str,
    session_key: str,
    as_gapper: bool,
    reverse: bool,
) -> list[dict]:
    """Roster rows for *symbols*, cold-quoting only newly admitted names.

    Symbols already known this session keep their last row unchanged
    (rank/order still follows the fresh ``symbols`` sequence from IB) —
    price freshness for live/displayed rows comes from the L1 hot path,
    not a repeated cold ``reqTickersAsync`` on every scanner batch.
    """
    known = _known_for(table, session_key)
    new_symbols = [s for s in symbols if s not in known]
    if new_symbols:
        quotes = await _discovery.snapshot_quotes(
            new_symbols, timeout_sec=IBKR_QUOTE_BATCH_TIMEOUT_SEC, require_success=False,
        )
        for sym in new_symbols:
            q = quotes.get(sym)
            if not q:
                continue
            row = row_from_quote(sym, q, as_gapper=as_gapper)
            if row:
                known[sym] = row
    # Drop symbols no longer present in the current ranked batch.
    for sym in list(known):
        if sym not in symbols:
            known.pop(sym, None)
    rows = [known[s] for s in symbols if s in known]
    sort_key = "gap_percent" if as_gapper else "change_pct"
    rows.sort(key=lambda r: r.get(sort_key) or 0, reverse=reverse)
    return rows


async def commit_table(
    *,
    table: str,
    symbols: list[str],
    lease_generation: int,
    lease_epoch: int,
    lease_session_key: str,
    epoch: int,
    shadow: dict[str, list[dict]],
) -> bool | None:
    state = get_runtime_state()
    gen = _client.current_generation()
    if not _session.can_commit_roster(
        state, table,
        generation=gen, epoch=epoch,
        fence_generation=lease_generation, fence_epoch=lease_epoch,
        session_key=lease_session_key,
    ):
        logger.debug("scanner_stream: discard stale commit for %s", table)
        return None
    as_gapper = table == _session.TABLE_GAPPERS
    async with timed("ibkr.scanner.hydrate"):
        rows = await hydrate_rows(
            symbols,
            table=table,
            session_key=lease_session_key,
            as_gapper=as_gapper,
            reverse=table != _session.TABLE_LOSERS,
        )
    shadow[table] = rows
    if not _session.is_persistent_authoritative():
        logger.debug(
            "scanner_stream shadow %s: %d rows (epoch=%d gen=%d)",
            table, len(rows), lease_epoch, lease_generation,
        )
        return True
    if not _session.can_commit_roster(
        state, table,
        generation=_client.current_generation(), epoch=epoch,
        fence_generation=lease_generation, fence_epoch=lease_epoch,
        session_key=lease_session_key,
    ):
        return None
    rows_attr, ts_attr = _session.cache_attr_names(table)
    wall = time.time()
    setattr(state, rows_attr, rows)
    setattr(state, ts_attr, wall)
    ts = _session.table_attr(state, table)
    _session.mark_live(ts, source="scanner_stream", session_key=lease_session_key)
    ts.roster_ts = wall
    ts.revision += 1
    try:
        from scanner_push import broadcast_roster_replace
        await broadcast_roster_replace(table, rows, ts)
    except Exception:
        logger.debug("scanner_stream: roster push failed", exc_info=True)
        return False
    return True


def log_shadow_parity(
    shadow: dict[str, list[dict]],
    persistent_reqids: dict[int, str],
) -> None:
    state = get_runtime_state()
    for table in (
        _session.TABLE_GAPPERS, _session.TABLE_GAINERS,
        _session.TABLE_LOSERS, _session.TABLE_AFTERHOURS,
    ):
        shadow_syms = {r["symbol"] for r in (shadow.get(table) or []) if r.get("symbol")}
        rows_attr, _ = _session.cache_attr_names(table)
        live_syms = {
            r.get("symbol") for r in (getattr(state, rows_attr) or []) if r.get("symbol")
        }
        if not shadow_syms and not live_syms:
            continue
        logger.info(
            "scanner_stream shadow parity %s: shadow=%d live=%d only_shadow=%s only_live=%s slots=%d",
            table, len(shadow_syms), len(live_syms),
            sorted(shadow_syms - live_syms)[:5],
            sorted(live_syms - shadow_syms)[:5],
            len(persistent_reqids),
        )
