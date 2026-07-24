"""
IBKR account summary and positions.

Reads from ib_async caches. Sync helpers that wait on the IB event loop
must not run under FastAPI — use Async variants for refresh.

Broker long qty SSOT for anti-short / flatten sizing is ``long_qty`` —
backed only by ``ib.positions()`` (never portfolio alone).
"""
from __future__ import annotations

import asyncio
import logging

from ibkr import client as _client
from ibkr.errors import IbkrAccountError, describe_exc
from metrics.op_metrics import timed, timed_sync

logger = logging.getLogger(__name__)

# Guards reqCompletedOrdersAsync from concurrent overlap (see
# refresh_completed_orders_cache) — ib_async can hang if the same request
# type is in flight twice at once.
_completed_orders_lock: asyncio.Lock | None = None


def _completed_orders_guard() -> asyncio.Lock:
    global _completed_orders_lock
    if _completed_orders_lock is None:
        _completed_orders_lock = asyncio.Lock()
    return _completed_orders_lock

_SUMMARY_TAGS = (
    "NetLiquidation",
    "TotalCashValue",
    "BuyingPower",
    "UnrealizedPnL",
    "RealizedPnL",
    "GrossPositionValue",
)


def get_positions() -> list[dict]:
    """Return open IBKR positions.

    Raises ``IbkrAccountError`` on disconnect / API failure — callers must
    never treat that as "flat" (a failed read is not the same fact as zero
    positions, and safety code like flatten/oversell checks depends on
    telling those two apart).
    """
    ib = _client.get_ib()
    if ib is None:
        raise IbkrAccountError("IBKR not connected — cannot read positions")
    try:
        with timed_sync("ibkr.account.positions_read"):
            positions = ib.positions()
        return [
            {
                "symbol": p.contract.symbol,
                "qty": p.position,
                "avg_cost": p.avgCost,
                "market_value": None,
            }
            for p in positions
        ]
    except Exception as exc:
        detail = describe_exc(exc)
        logger.exception("IBKR: get_positions error: %s", detail)
        raise IbkrAccountError(f"get_positions failed: {detail}") from exc


def long_qty(symbol: str) -> float:
    """Verified long quantity for ``symbol`` from ``ib.positions()`` only.

    This is the **only** broker long-qty API for anti-short / flatten sizing.
    Sums same-symbol rows and ignores qty ≤ 0. Returns ``0.0`` when the
    account is verified flat in that symbol. Raises ``IbkrAccountError`` when
    the positions cache cannot be read — never invent a long from portfolio.
    """
    sym = (symbol or "").strip().upper()
    if not sym:
        return 0.0
    total = 0.0
    for p in get_positions():
        if str(p.get("symbol") or "").upper() != sym:
            continue
        try:
            qty = float(p.get("qty") or 0)
        except (TypeError, ValueError):
            continue
        if qty > 0:
            total += qty
    return total


def positions_for_ui() -> list[dict]:
    """Positions rows for ``GET /api/ibkr/positions``.

    **Qty** (and avg_cost) come from ``ib.positions()`` — same SSOT as
    ``long_qty``. Mark / market value / PnL are joined from ``ib.portfolio()``
    by symbol when that cache is available. Portfolio-only symbols are never
    invented as open longs (avoids UI qty that validate/flatten would refuse).
    """
    by_sym: dict[str, dict] = {}
    for p in get_positions():
        sym = str(p.get("symbol") or "").upper()
        if not sym:
            continue
        try:
            qty = float(p.get("qty") or 0)
        except (TypeError, ValueError):
            continue
        if qty == 0:
            continue
        row = by_sym.get(sym)
        if row is None:
            by_sym[sym] = {
                "symbol": sym,
                "qty": qty,
                "avg_cost": p.get("avg_cost"),
                "market_price": None,
                "market_value": None,
                "unrealized_pnl": None,
                "realized_pnl": None,
            }
        else:
            # Multiple IB rows for same symbol (rare) — sum qty; keep first avg.
            row["qty"] = float(row["qty"]) + qty

    if not by_sym:
        return []

    try:
        portfolio = get_portfolio()
    except IbkrAccountError as exc:
        # Qty SSOT already succeeded — surface MTM as unknown rather than 503
        # the whole panel when only PnL join failed.
        logger.warning("IBKR: portfolio join failed for positions UI: %s", exc)
        portfolio = []

    mtm: dict[str, dict] = {}
    for item in portfolio:
        sym = str(item.get("symbol") or "").upper()
        if sym:
            mtm[sym] = item

    out: list[dict] = []
    for sym, row in by_sym.items():
        join = mtm.get(sym) or {}
        out.append({
            "symbol": sym,
            "qty": row["qty"],
            "avg_cost": row["avg_cost"] if row["avg_cost"] is not None else join.get("avg_cost"),
            "market_price": join.get("market_price"),
            "market_value": join.get("market_value"),
            "unrealized_pnl": join.get("unrealized_pnl"),
            "realized_pnl": join.get("realized_pnl"),
        })
    return out


def _summary_from_items(items: list) -> dict:
    summary: dict = {"connected": True, "mode": _client.account_mode()}
    for item in items:
        tag = getattr(item, "tag", None)
        if tag not in _SUMMARY_TAGS:
            continue
        currency = getattr(item, "currency", "") or ""
        if currency and currency not in ("USD", "BASE", ""):
            continue
        raw = getattr(item, "value", None)
        try:
            summary[tag] = float(raw) if raw not in (None, "") else None
        except (TypeError, ValueError):
            summary[tag] = None
    return summary


def get_account_summary() -> dict:
    """Snapshot from Gateway cache (no nested event-loop wait).

    When disconnected (no IB instance), returns ``{connected: False}`` for
    status UI. When connected, raises ``IbkrAccountError`` if
    ``accountValues()`` fails — never disguise that as a normal summary
    (BUY LMT BuyingPower check must fail closed, not skip).
    """
    ib = _client.get_ib()
    if ib is None:
        return {"connected": False, "mode": "disconnected"}

    try:
        with timed_sync("ibkr.account.summary_read"):
            values = list(ib.accountValues())
        summary = _summary_from_items(values)
        if "NetLiquidation" not in summary:
            summary["pending"] = True
        return summary
    except Exception as exc:
        detail = describe_exc(exc)
        logger.exception("IBKR: get_account_summary error: %s", detail)
        raise IbkrAccountError(f"get_account_summary failed: {detail}") from exc


async def refresh_account_summary() -> dict:
    """Async refresh via accountSummaryAsync, then return snapshot.

    Propagates ``IbkrAccountError`` honestly — does not swallow into a
    ``{connected: False}`` dict that would skip BUY BuyingPower checks.
    """
    ib = _client.get_ib()
    if ib is None:
        return {"connected": False, "mode": "disconnected"}
    try:
        async with timed("ibkr.account.summary_refresh"):
            items = await ib.accountSummaryAsync()
        if items:
            return _summary_from_items(list(items))
        return get_account_summary()
    except IbkrAccountError:
        raise
    except Exception as exc:
        detail = describe_exc(exc)
        logger.exception("IBKR: refresh_account_summary error: %s", detail)
        raise IbkrAccountError(f"refresh_account_summary failed: {detail}") from exc


async def refresh_positions_cache(ib: object | None = None) -> None:
    """Best-effort ``reqPositionsAsync`` after connect so ``positions()`` is warm.

    Logged on failure; subsequent ``long_qty`` / ``get_positions`` still fail
    closed if the cache remains empty or unreadable.

    ``ib`` lets the connect/warm-up path in ``ibkr.client`` pass the just-
    connected instance directly — ``client.get_ib()`` is gated on session
    READY, and this warm-up call is exactly what earns READY, so it must not
    go through that gate itself. External callers omit ``ib`` and get the
    normal gated lookup.
    """
    if ib is None:
        ib = _client.get_ib()
    if ib is None:
        return
    req = getattr(ib, "reqPositionsAsync", None)
    if req is None:
        return
    try:
        async with timed("ibkr.account.positions_refresh"):
            await req()
        logger.info("IBKR: positions cache refreshed after connect")
    except Exception as exc:
        logger.warning(
            "IBKR: positions cache refresh failed (long_qty may see empty): %s",
            describe_exc(exc),
        )


async def refresh_completed_orders_cache(ib: object | None = None) -> None:
    """Best-effort ``reqCompletedOrdersAsync(apiOnly=False)`` after connect so
    ``ib.trades()`` (and therefore Closed Orders) includes terminal orders
    from *before* this API session connected — e.g. a position opened via
    TWS/manual order, or a fill that happened across a Gateway/API restart.
    ``apiOnly=False`` matches Positions, which also surfaces manual fills.

    Single-flighted: overlapping callers serialize on the same lock rather
    than firing a second concurrent ``reqCompletedOrdersAsync`` — ib_async
    can hang if that request type is in flight twice at once. Logged on
    failure only; callers still fail closed via ``closed_orders()``'s own
    disconnect check, never silently substituting an empty result here.

    ``ib`` — see ``refresh_positions_cache`` docstring; lets the connect
    warm-up path bypass the READY gate it is itself trying to satisfy.
    """
    if ib is None:
        ib = _client.get_ib()
    if ib is None:
        return
    req = getattr(ib, "reqCompletedOrdersAsync", None)
    if req is None:
        return
    from constants_ibkr import IBKR_COMPLETED_ORDERS_TIMEOUT_SEC

    async with _completed_orders_guard():
        try:
            await asyncio.wait_for(
                req(False),
                timeout=float(IBKR_COMPLETED_ORDERS_TIMEOUT_SEC),
            )
            logger.info("IBKR: completed-orders cache refreshed after connect")
        except Exception as exc:
            logger.warning(
                "IBKR: completed-orders cache refresh failed (Closed Orders "
                "may miss pre-session fills): %s",
                describe_exc(exc),
            )


def get_portfolio() -> list[dict]:
    """Return portfolio (positions + live P&L). Raises ``IbkrAccountError`` on
    disconnect / API failure — see ``get_positions`` docstring."""
    ib = _client.get_ib()
    if ib is None:
        raise IbkrAccountError("IBKR not connected — cannot read portfolio")
    try:
        with timed_sync("ibkr.account.portfolio_read"):
            portfolio = ib.portfolio()
        return [
            {
                "symbol": item.contract.symbol,
                "qty": item.position,
                "market_price": item.marketPrice,
                "market_value": item.marketValue,
                "avg_cost": item.averageCost,
                "unrealized_pnl": item.unrealizedPNL,
                "realized_pnl": item.realizedPNL,
            }
            for item in portfolio
        ]
    except Exception as exc:
        detail = describe_exc(exc)
        logger.exception("IBKR: get_portfolio error: %s", detail)
        raise IbkrAccountError(f"get_portfolio failed: {detail}") from exc
