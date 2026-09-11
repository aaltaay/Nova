"""Active-tab + reserved HOD Level-1 streaming → batched /ws/scanner patches.

Replaces the infeasible 1Hz reqTickersAsync table loop. IBKR L1 is one
reqMktData subscription per symbol; ticks are coalesced into price_patch
batches. HOD discovery remains independent (volume seeds) with a reserved
live pool that cannot be starved by the active gainer/gapper table.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Awaitable, Callable, Optional

from constants import (
    IBKR_L1_BATCH_FLUSH_SEC,
    IBKR_L1_RECONCILE_SEC,
    IBKR_L1_STREAM_BUDGET,
    IBKR_L1_SUBSCRIBE_PACE_SEC,
    IBKR_L1_TAB_SWITCH_GRACE_SEC,
)
from archive import bar_builder as _bar_builder
from ibkr import ticks as _ticks
from ibkr import l1_minute as _l1_minute
from ibkr import tape_10sec as _tape_10sec
from ibkr.scanner_l1_plan import count_tab_contributions, plan_stream_symbols
from metrics.op_metrics import record_since

logger = logging.getLogger(__name__)

PushFn = Callable[[dict[str, Any]], Awaitable[None]]
ApplyQuoteFn = Callable[[str, float, Optional[int], Optional[float], float], Optional[dict]]
GetProviderFn = Callable[[], str]
GetTabSymbolsFn = Callable[[str], list[str]]
GetHodSymbolsFn = Callable[[], list[str]]
GetActiveTablesFn = Callable[[], list[str]]

_pending: dict[str, dict[str, Any]] = {}
_pending_started_ns: int | None = None
# Symbol → the displayed scanner table that owns it, for symbols currently
# subscribed under OWNER_SCANNER. This gates flush_loop's price_patch
# forwarding and supplies each row's table tag. HOD-only reserved-pool ticks
# (which keep flowing for retained symbols after their table freezes, ADR 008)
# are never in this map, so they are dropped from the WS payload instead of
# leaking into a frozen table. A per-symbol table (rather than one dominant
# tab) is what lets the desk show Gappers and Gainers at the same time.
_active_tab_tables: dict[str, str] = {}
_last_ok_ts: float | None = None


def _idle_state() -> dict[str, Any]:
    """Subscription state when nothing scanner-ish is streaming."""
    return {
        "tab": "none",
        "tables": [],
        "tab_counts": {},
        "requested_tab": 0,
        "active_tab": 0,
        "requested_hod": 0,
        "active_hod": 0,
        "active_total": 0,
        "budget": IBKR_L1_STREAM_BUDGET,
        "rejected": [],
        "error": None,
    }


_subscription_state: dict[str, Any] = _idle_state()
_tab_grace_until = 0.0
_prev_tab_symbols: list[str] = []
_apply_quote: ApplyQuoteFn | None = None
_reconcile_event: asyncio.Event | None = None


def _ensure_reconcile_event() -> asyncio.Event:
    global _reconcile_event
    if _reconcile_event is None:
        _reconcile_event = asyncio.Event()
    return _reconcile_event


def request_reconcile() -> None:
    """Wake reconcile_loop early after a roster commit (G8)."""
    try:
        _ensure_reconcile_event().set()
    except Exception:
        logger.debug("scanner_l1: request_reconcile failed", exc_info=True)


def get_subscription_state() -> dict[str, Any]:
    return dict(_subscription_state)


def note_capacity_error(message: str) -> None:
    """Surface Error 101 (max tickers) into the subscription error field."""
    global _subscription_state
    text = (message or "").strip() or "IBKR L1 capacity error"
    prev = _subscription_state.get("error")
    _subscription_state = {
        **_subscription_state,
        "error": text if not prev else f"{prev}; {text}",
    }


def get_last_ok_ts() -> float | None:
    return _last_ok_ts


def on_l1_quote(
    symbol: str,
    price: float,
    volume: int | None,
    prev_close: float | None,
    ts_unix: float,
    *,
    quote_quality: str | None = None,
    open_price: float | None = None,
) -> None:
    """ticks.py quote listener — buffer for the next batch flush."""
    sym = (symbol or "").strip().upper()
    if not sym:
        return
    global _last_ok_ts, _pending_started_ns
    row: dict[str, Any] = {
        "symbol": sym,
        "price": price,
        "volume": volume,
        "quote_ts": ts_unix,
    }
    if quote_quality:
        row["quote_quality"] = quote_quality
    try:
        _l1_minute.on_last(sym, float(price), float(ts_unix))
    except Exception:
        logger.debug("scanner_l1: l1_minute.on_last failed", exc_info=True)
    if _apply_quote is not None:
        try:
            try:
                patched = _apply_quote(
                    sym,
                    price,
                    volume,
                    prev_close,
                    ts_unix,
                    quote_quality=quote_quality,
                    open_price=open_price,
                )
            except TypeError:
                try:
                    patched = _apply_quote(
                        sym,
                        price,
                        volume,
                        prev_close,
                        ts_unix,
                        quote_quality=quote_quality,
                    )
                except TypeError:
                    patched = _apply_quote(sym, price, volume, prev_close, ts_unix)
            if patched:
                row.update(patched)
        except Exception:
            logger.exception("scanner_l1: apply_quote failed for %s", sym)
    if not _pending:
        _pending_started_ns = time.perf_counter_ns()
    _pending[sym] = row
    _last_ok_ts = ts_unix


def configure(apply_quote: ApplyQuoteFn) -> None:
    global _apply_quote
    _apply_quote = apply_quote
    _ticks.add_quote_listener(on_l1_quote)


def _collect_tab_symbols(
    tables: list[str],
    get_tab_symbols: GetTabSymbolsFn,
) -> tuple[list[str], dict[str, str]]:
    """Ordered symbol union across displayed tables + the owning table per symbol.

    ``tables`` arrives most-demanded first, so the active-tab budget fills from
    the table the desk is watching most. A table that yields nothing (frozen
    Gappers after 09:30 — ADR 008) simply contributes no symbols instead of
    zeroing the whole active-tab set.
    """
    ordered: list[str] = []
    owner_table: dict[str, str] = {}
    for table in tables:
        for raw in get_tab_symbols(table) or []:
            sym = (raw or "").strip().upper()
            if not sym or sym in owner_table:
                continue
            owner_table[sym] = table
            ordered.append(sym)
    return ordered, owner_table


async def _reconcile_once(
    get_provider: GetProviderFn,
    get_active_tables: GetActiveTablesFn,
    get_tab_symbols: GetTabSymbolsFn,
    get_hod_symbols: GetHodSymbolsFn,
) -> None:
    global _subscription_state, _tab_grace_until, _prev_tab_symbols

    if (get_provider() or "").strip().lower() != "ibkr":
        await _ticks.set_owner_symbols(_ticks.OWNER_SCANNER, [])
        await _ticks.set_owner_symbols(_ticks.OWNER_HOD, [])
        _active_tab_tables.clear()
        _subscription_state = {**_subscription_state, **_idle_state()}
        return

    tables = [t for t in (get_active_tables() or []) if t and t != "none"]
    raw_tab, owner_table = _collect_tab_symbols(tables, get_tab_symbols)
    raw_hod = list(get_hod_symbols() or [])
    # Skip symbols already known unqualifiable — don't burn qualify slots.
    try:
        import hod_momo_active as _hod_active

        raw_hod = [s for s in raw_hod if not _hod_active.is_l1_subscribe_blocked(s)]
        raw_tab = [s for s in raw_tab if not _hod_active.is_l1_subscribe_blocked(s)]
    except Exception as exc:
        from ibkr.errors import describe_exc

        logger.warning(
            "IBKR L1: blocklist filter skipped: %s",
            describe_exc(exc),
            exc_info=True,
        )
    plan = plan_stream_symbols(raw_tab, raw_hod)

    # Brief grace: keep prior tab streams during switch so prices don't blink out.
    now = time.time()
    desired_tab = list(plan["tab"])
    if desired_tab != _prev_tab_symbols:
        if _prev_tab_symbols:
            if _tab_grace_until <= 0:
                _tab_grace_until = now + float(IBKR_L1_TAB_SWITCH_GRACE_SEC)
            if now < _tab_grace_until:
                grace_tab = list(dict.fromkeys(desired_tab + _prev_tab_symbols))
                plan = plan_stream_symbols(grace_tab, raw_hod)
            else:
                _prev_tab_symbols = desired_tab
                _tab_grace_until = 0.0
        else:
            _prev_tab_symbols = desired_tab
            _tab_grace_until = 0.0
    elif _tab_grace_until > 0 and now >= _tab_grace_until:
        _prev_tab_symbols = desired_tab
        _tab_grace_until = 0.0

    # Scanner owner = displayed table rows; HOD owner = reserved HOD pool
    # (overlap keeps both owners so leaving the tab does not drop HOD eval).
    # ADR 008: this map gates flush_loop's price_patch forwarding — a symbol
    # only reaches the WS as a table's row when it is actually subscribed
    # here, and it is tagged with the table that requested it.
    # Symbols held only by the switch grace keep their previous table so a row
    # still on screen does not blink out mid-switch.
    carried = dict(_active_tab_tables)
    _active_tab_tables.clear()
    for sym in plan["tab"]:
        table = owner_table.get(sym) or carried.get(sym)
        if table:
            _active_tab_tables[sym] = table
    tab_result = await _ticks.set_owner_symbols(_ticks.OWNER_SCANNER, plan["tab"])
    if IBKR_L1_SUBSCRIBE_PACE_SEC > 0:
        await asyncio.sleep(float(IBKR_L1_SUBSCRIBE_PACE_SEC))
    hod_result = await _ticks.set_owner_symbols(_ticks.OWNER_HOD, plan["hod"])

    failed = list(tab_result.get("failed") or []) + list(hod_result.get("failed") or [])
    error = None
    if failed:
        error = f"IBKR L1 subscribe failed for {len(failed)} symbol(s)"
        # Keep unqualifiable explore names out of the next HOD active set so
        # they cannot occupy a dead slot and flap coverage 98%→fail.
        try:
            import hod_momo_active as _hod_active

            _hod_active.note_l1_subscribe_failed(failed)
        except Exception:
            logger.debug(
                "scanner_l1: could not record L1 subscribe failures",
                exc_info=True,
            )
    if plan["rejected"]:
        error = (error + "; " if error else "") + (
            f"capacity: {len(plan['rejected'])} symbol(s) not streamed"
        )
    # Fail loud, not quiet: the desk asked for tables that do have rows, yet
    # nothing is streaming. Silence here is what froze the whole scanner column.
    starved = sorted(
        {t for t in tables if t not in set(_active_tab_tables.values())}
        & {owner_table[s] for s in owner_table}
    )
    if starved:
        error = (error + "; " if error else "") + (
            f"no live L1 for displayed table(s): {', '.join(starved)}"
        )

    _subscription_state = {
        "tab": tables[0] if tables else "none",
        "tables": list(tables),
        "tab_counts": count_tab_contributions(
            tables, raw_tab, owner_table, _active_tab_tables,
        ),
        "requested_tab": len(raw_tab),
        "active_tab": len(tab_result.get("active") or []),
        "requested_hod": len(raw_hod),
        "active_hod": len(hod_result.get("active") or []),
        "active_total": len(_ticks.subscribed_symbols()),
        "budget": plan["budget"],
        "rejected": plan["rejected"][:40],
        "failed": failed[:40],
        "error": error,
    }


async def reconcile_loop(
    get_provider: GetProviderFn,
    get_active_tables: GetActiveTablesFn,
    get_tab_symbols: GetTabSymbolsFn,
    get_hod_symbols: GetHodSymbolsFn,
) -> None:
    while True:
        try:
            await _reconcile_once(
                get_provider, get_active_tables, get_tab_symbols, get_hod_symbols,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("scanner_l1: reconcile failed")
            _subscription_state["error"] = "reconcile failed"
        ev = _ensure_reconcile_event()
        try:
            await asyncio.wait_for(ev.wait(), timeout=float(IBKR_L1_RECONCILE_SEC))
        except asyncio.TimeoutError:
            pass
        else:
            ev.clear()


async def flush_loop(push: PushFn) -> None:
    global _pending, _pending_started_ns
    while True:
        try:
            await asyncio.sleep(float(IBKR_L1_BATCH_FLUSH_SEC))
            now = time.time()
            _l1_minute.flush_elapsed(now)
            # Same heartbeat closes out quiet 10Sec tape buckets (D-003) --
            # a Trader symbol with no new prints for 10s must still flush.
            _tape_10sec.flush_elapsed(now)
            _bar_builder.flush_elapsed(now, queued=True)
            if not _pending:
                continue
            pending = _pending
            _pending = {}
            started_ns = _pending_started_ns
            _pending_started_ns = None
            # Table-scoped: only forward ticks for symbols actually subscribed
            # under a displayed scanner table (ADR 008). HOD-only reserved-pool
            # ticks for retained/frozen-table symbols are dropped here rather
            # than tagged with someone else's table — that tag previously
            # leaked HOD-pool price updates into a frozen table's row. Rows are
            # grouped per table so two tables on screen cannot cross-tag.
            by_table: dict[str, list[dict[str, Any]]] = {}
            for sym, row in pending.items():
                table = _active_tab_tables.get(sym)
                if not table:
                    continue
                by_table.setdefault(table, []).append(row)
            if not by_table:
                continue
            ts = time.time()
            subscription = get_subscription_state()
            try:
                for table, rows in by_table.items():
                    await push({
                        "type": "price_patch",
                        "table": table,
                        "ts": ts,
                        "stale": False,
                        "subscription": subscription,
                        "rows": rows,
                    })
            except BaseException:
                if started_ns is not None:
                    record_since("ws.scanner.price_patch_buffer_to_broadcast", started_ns, ok=False)
                raise
            else:
                if started_ns is not None:
                    record_since("ws.scanner.price_patch_buffer_to_broadcast", started_ns)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("scanner_l1: flush failed")


async def shutdown() -> None:
    global _pending_started_ns
    await _ticks.set_owner_symbols(_ticks.OWNER_SCANNER, [])
    await _ticks.set_owner_symbols(_ticks.OWNER_HOD, [])
    _pending.clear()
    _pending_started_ns = None
    _active_tab_tables.clear()
