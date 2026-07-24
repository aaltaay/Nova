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
    IBKR_L1_ACTIVE_TAB_MAX,
    IBKR_L1_BATCH_FLUSH_SEC,
    IBKR_L1_RECONCILE_SEC,
    IBKR_L1_STREAM_BUDGET,
    IBKR_L1_STREAM_RESERVE,
    IBKR_L1_SUBSCRIBE_PACE_SEC,
    IBKR_L1_TAB_SWITCH_GRACE_SEC,
)
from ibkr import ticks as _ticks
from metrics.op_metrics import record_since

logger = logging.getLogger(__name__)

PushFn = Callable[[dict[str, Any]], Awaitable[None]]
ApplyQuoteFn = Callable[[str, float, Optional[int], Optional[float], float], Optional[dict]]
GetProviderFn = Callable[[], str]
GetTabSymbolsFn = Callable[[str], list[str]]
GetHodSymbolsFn = Callable[[], list[str]]
GetActiveTabFn = Callable[[], str]

_pending: dict[str, dict[str, Any]] = {}
_pending_started_ns: int | None = None
# Symbols currently subscribed under OWNER_SCANNER (the live active tab) —
# used to decide which pending ticks are safe to forward as a table-scoped
# price_patch. HOD-only reserved-pool ticks (which keep flowing for retained
# symbols after their table freezes, ADR 008) are never in this set, so they
# are dropped from the WS payload instead of leaking into a frozen table.
_active_tab_symbols: set[str] = set()
_last_ok_ts: float | None = None
_subscription_state: dict[str, Any] = {
    "tab": "none",
    "requested_tab": 0,
    "active_tab": 0,
    "requested_hod": 0,
    "active_hod": 0,
    "active_total": 0,
    "budget": IBKR_L1_STREAM_BUDGET,
    "rejected": [],
    "error": None,
}
_tab_grace_until = 0.0
_prev_tab_symbols: list[str] = []
_apply_quote: ApplyQuoteFn | None = None


def get_subscription_state() -> dict[str, Any]:
    return dict(_subscription_state)


def get_last_ok_ts() -> float | None:
    return _last_ok_ts


def on_l1_quote(
    symbol: str,
    price: float,
    volume: int | None,
    prev_close: float | None,
    ts_unix: float,
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
    if _apply_quote is not None:
        try:
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


def _budget_for_streams() -> int:
    return max(1, int(IBKR_L1_STREAM_BUDGET) - int(IBKR_L1_STREAM_RESERVE))


def plan_stream_symbols(
    tab_symbols: list[str],
    hod_symbols: list[str],
    *,
    budget: int | None = None,
    tab_max: int = IBKR_L1_ACTIVE_TAB_MAX,
) -> dict[str, Any]:
    """Pure planner: reserve tab slots first, then HOD, dedupe, reject overflow."""
    cap = int(budget if budget is not None else _budget_for_streams())
    tab_cap = max(0, min(int(tab_max), cap))
    tab: list[str] = []
    seen: set[str] = set()
    for raw in tab_symbols:
        sym = (raw or "").strip().upper()
        if not sym or sym in seen:
            continue
        seen.add(sym)
        tab.append(sym)
        if len(tab) >= tab_cap:
            break
    rejected: list[str] = []
    # Excess tab rows beyond tab_cap
    for raw in tab_symbols[len(tab):]:
        sym = (raw or "").strip().upper()
        if sym and sym not in seen:
            rejected.append(sym)

    hod_slots = max(0, cap - len(tab))
    hod: list[str] = []
    for raw in hod_symbols:
        sym = (raw or "").strip().upper()
        if not sym or sym in seen:
            continue
        if len(hod) >= hod_slots:
            rejected.append(sym)
            continue
        seen.add(sym)
        hod.append(sym)

    return {
        "tab": tab,
        "hod": hod,
        "combined": tab + [s for s in hod if s not in tab],
        "rejected": rejected,
        "budget": cap,
    }


async def _reconcile_once(
    get_provider: GetProviderFn,
    get_active_tab: GetActiveTabFn,
    get_tab_symbols: GetTabSymbolsFn,
    get_hod_symbols: GetHodSymbolsFn,
) -> None:
    global _subscription_state, _tab_grace_until, _prev_tab_symbols

    if (get_provider() or "").strip().lower() != "ibkr":
        await _ticks.set_owner_symbols(_ticks.OWNER_SCANNER, [])
        await _ticks.set_owner_symbols(_ticks.OWNER_HOD, [])
        _active_tab_symbols.clear()
        _subscription_state = {
            **_subscription_state,
            "tab": "none",
            "requested_tab": 0,
            "active_tab": 0,
            "requested_hod": 0,
            "active_hod": 0,
            "active_total": 0,
            "rejected": [],
            "error": None,
        }
        return

    tab = (get_active_tab() or "none").strip().lower()
    raw_tab = get_tab_symbols(tab) if tab and tab != "none" else []
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

    # Scanner owner = active tab rows; HOD owner = reserved HOD pool
    # (overlap keeps both owners so leaving the tab does not drop HOD eval).
    # ADR 008: this set gates flush_loop's price_patch forwarding — a symbol
    # only reaches the WS as this table's row when it is actually subscribed
    # here, not merely because it is the dominant client tab hint.
    _active_tab_symbols.clear()
    _active_tab_symbols.update(plan["tab"])
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

    _subscription_state = {
        "tab": tab,
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
    get_active_tab: GetActiveTabFn,
    get_tab_symbols: GetTabSymbolsFn,
    get_hod_symbols: GetHodSymbolsFn,
) -> None:
    while True:
        try:
            await _reconcile_once(
                get_provider, get_active_tab, get_tab_symbols, get_hod_symbols,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("scanner_l1: reconcile failed")
            _subscription_state["error"] = "reconcile failed"
        await asyncio.sleep(float(IBKR_L1_RECONCILE_SEC))


async def flush_loop(push: PushFn) -> None:
    global _pending, _pending_started_ns
    while True:
        try:
            await asyncio.sleep(float(IBKR_L1_BATCH_FLUSH_SEC))
            if not _pending:
                continue
            pending = _pending
            _pending = {}
            started_ns = _pending_started_ns
            _pending_started_ns = None
            # Table-scoped: only forward ticks for symbols actually subscribed
            # under the active scanner tab (ADR 008). HOD-only reserved-pool
            # ticks for retained/frozen-table symbols are dropped here rather
            # than tagged with the dominant tab — that tag previously leaked
            # HOD-pool price updates into a frozen table's displayed row.
            rows = [row for sym, row in pending.items() if sym in _active_tab_symbols]
            if not rows:
                continue
            ts = time.time()
            table = _subscription_state.get("tab") or "none"
            try:
                await push({
                    "type": "price_patch",
                    "table": table if table != "none" else None,
                    "ts": ts,
                    "stale": False,
                    "subscription": get_subscription_state(),
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
    _active_tab_symbols.clear()
