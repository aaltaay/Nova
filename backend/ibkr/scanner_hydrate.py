"""Roster admission for ADR 008 persistent scanner leases.

ADR 010 decision 5: a ranked IB scanner name is admitted as a row the moment IB
pushes it. Price, ``prev_close`` and ``change_pct`` arrive from the L1 hot path
(``ibkr/scanner_l1.py`` -> ``ibkr_bridge.apply_l1_quote``), which is the same
feed that keeps displayed rows fresh.

Admission must never depend on a COLD ``snapshot_quotes`` round trip. That
coupling is what emptied the desk for an entire premarket on 2026-08-24: IB had
already delivered ``TOP_PERC_GAIN`` names, every cold batch died on the 20s
``on_ib`` bridge ceiling, and ``gainer_cache_ts`` stayed 0 while the Gateway
reported healthy. An unpriced row is honest; a missing row is not.

Row order is IB's scanner rank. Nova does not re-sort a ranked scan -- doing so
invents a second ranking that disagrees with the feed as L1 ticks land.
"""
from __future__ import annotations

import logging
import time

from ibkr import client as _client
from ibkr import scanner_session as _session
from metrics.op_metrics import timed
from runtime_state import get_runtime_state

logger = logging.getLogger(__name__)

# REST commit is authoritative. A WS failure must not report the commit as
# failed (D-026) -- that split REST revision from caller/metrics truth.
_roster_push_failed = 0


def roster_push_failed_count() -> int:
    return _roster_push_failed


def reset_roster_push_failed_for_tests() -> None:
    global _roster_push_failed
    _roster_push_failed = 0


def stub_row(sym: str, rank: int, exchange: str | None = None) -> dict:
    """Newly admitted name with no quote yet.

    ``None`` (not ``0.0``) for every price field so the UI can render "waiting
    for L1" instead of a fabricated flat quote. ``exchange`` comes free from
    the same IB scan row (``contract.primaryExchange``) -- no extra IB call.

    ``admitted_ts`` is stamped once, here, and carried forward untouched by
    every later rank/reprice merge (``hydrate_rows`` and ``reprice_mover_row``
    both spread the prior row with ``{**prior, ...}``). ``roster_ts`` gets
    rewritten on every IB scanner push, so it can never age past the
    coverage grace on a busy table -- ``admitted_ts`` is the per-row clock
    integrity needs to tell "just admitted" apart from "starved for L1".
    """
    return {
        "symbol": sym,
        "rank": rank,
        "price": None,
        "prev_close": None,
        "change_pct": None,
        "change_abs": None,
        "gap_percent": None,
        "volume": 0,
        "exchange": exchange,
        "admitted_ts": time.time(),
    }


async def hydrate_rows(
    symbols: list[str],
    *,
    table: str,
    session_key: str,
    existing: list[dict] | None = None,
    exchanges: dict[str, str] | None = None,
) -> list[dict]:
    """Roster rows for *symbols* in IB rank order.

    Rows already present in *existing* (the table's live cache) keep whatever
    the L1 path has filled in; only their rank follows the fresh batch. Symbols
    absent from the current ranked batch are dropped. ``exchanges`` backfills
    an unknown exchange on a prior row -- it never overwrites one already set.
    """
    by_sym = {
        (r.get("symbol") or "").strip().upper(): r
        for r in (existing or [])
        if r.get("symbol")
    }
    exchanges = exchanges or {}
    rows: list[dict] = []
    for rank, sym in enumerate(symbols, start=1):
        prior = by_sym.get(sym)
        exch = exchanges.get(sym)
        if prior is None:
            rows.append(stub_row(sym, rank, exchange=exch))
        elif prior.get("rank") == rank and (prior.get("exchange") or not exch):
            rows.append(prior)
        else:
            next_row = {**prior, "rank": rank}
            if not next_row.get("exchange") and exch:
                next_row["exchange"] = exch
            rows.append(next_row)
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
    exchanges: dict[str, str] | None = None,
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
    if not symbols:
        # IB Warning 165 / no items. Never stamp a live roster clock for it:
        # "0 rows, scanned just now" reads as a quiet market, and that lie is
        # what hid a dead premarket feed on 2026-08-24. Integrity owns the
        # alarm; this path simply refuses to fabricate freshness.
        logger.warning(
            "scanner_stream: %s batch had no names -- leaving roster untouched",
            table,
        )
        return None
    rows_attr, ts_attr = _session.cache_attr_names(table)
    async with timed("ibkr.scanner.hydrate"):
        rows = await hydrate_rows(
            symbols,
            table=table,
            session_key=lease_session_key,
            existing=getattr(state, rows_attr) or [],
            exchanges=exchanges,
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
    wall = time.time()
    setattr(state, rows_attr, rows)
    setattr(state, ts_attr, wall)
    # A landed roster proves the feed recovered. Without this the error set by
    # a previous failed commit would paint Integrity red for the rest of the
    # session (PROBLEM_LOG 2026-07-23, sticky banner after reconnect).
    state.ibkr_bridge_last_error = ""
    from ibkr.scanner_persist import persist_roster

    persist_roster(table, rows, wall)
    ts = _session.table_attr(state, table)
    _session.mark_live(ts, source="scanner_stream", session_key=lease_session_key)
    ts.roster_ts = wall
    ts.revision += 1
    if table == _session.TABLE_GAINERS:
        # Premarket Gappers is a filtered projection of this roster (ADR 008
        # amendment 2026-08-24), so a new Gainers membership can add or drop
        # gappers even before any L1 tick lands.
        from ibkr import gapper_view

        gapper_view.refresh(state, source="gainers_commit")
    try:
        from scanner_push import broadcast_roster_replace
        await broadcast_roster_replace(table, rows, ts)
    except Exception:
        global _roster_push_failed
        _roster_push_failed += 1
        logger.warning(
            "scanner_stream: roster push failed (REST revision=%s push_failed=%s)",
            ts.revision,
            _roster_push_failed,
            exc_info=True,
        )
    try:
        from hod_roster_hooks import on_hod_roster_commit

        on_hod_roster_commit(table)
    except Exception:
        logger.debug("scanner_stream: HOD roster commit hook failed", exc_info=True)
    try:
        from large_cap_hooks import on_large_cap_roster_commit

        on_large_cap_roster_commit(table, rows)
    except Exception:
        logger.debug("scanner_stream: Large Cap roster commit hook failed", exc_info=True)
    try:
        from mover_enrich_hooks import on_mover_roster_commit

        on_mover_roster_commit(table, rows)
    except Exception:
        logger.debug("scanner_stream: mover enrich hook failed", exc_info=True)
    try:
        from scanner_news_badge import on_roster_commit

        on_roster_commit(table, rows)
    except Exception:
        logger.debug("scanner_stream: news badge hook failed", exc_info=True)
    return True


def log_shadow_parity(
    shadow: dict[str, list[dict]],
    persistent_reqids: dict[int, str],
) -> None:
    state = get_runtime_state()
    for table in (
        _session.TABLE_GAPPERS, _session.TABLE_GAINERS,
        _session.TABLE_LOSERS, _session.TABLE_AFTERHOURS, _session.TABLE_LARGE_CAP,
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
