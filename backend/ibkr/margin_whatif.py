"""IBKR's what-if margin for one order: nothing is placed (ADR 048 decision 2).

``ib.whatIfOrderAsync`` sends a copy of the order with ``whatIf`` set. IBKR answers with the margin
the order would take -- initial and maintenance, before and after, and the account's equity with
loan -- and never transmits it; ib_async settles the answer without making a trade or firing an
order event. This module is that API's only caller in Nova. It never calls ``placeOrder``, holds no
order and needs no spend gate: a what-if spends nothing.

The answer is the session's account (the Live account; the legacy paper Gateway's when that is the
login). When the account already holds the stock, IBKR nets the order against the position, so
the change is not this order's requirement: Nova refuses to read it (``holds``).

Runs on the IB loop (``ibkr.loop_supervisor.on_ib``). Owns no state.
"""
from __future__ import annotations

import asyncio
import logging
import math
import time
from typing import Any

logger = logging.getLogger(__name__)

# IBKR's "no value" double (ib_async UNSET_DOUBLE): any figure this large is not a figure.
_UNSET_FLOOR = 1e300


def number(raw: Any) -> float | None:
    """One of the OrderState's strings as a float; None when IBKR left it unset."""
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value) or abs(value) >= _UNSET_FLOOR:
        return None
    return value


def _held(ib: Any, symbol: str) -> float:
    total = 0.0
    for pos in ib.positions() or []:
        if str(getattr(pos.contract, "symbol", "") or "").upper() == symbol:
            total += float(pos.position or 0)
    return total


def _refused(symbol: str, side: str, qty: float, price: float, error: str) -> dict[str, Any]:
    return {"ok": False, "symbol": symbol, "side": side, "qty": qty, "price": price, "error": error,
            "ts": time.time()}


async def ask(symbol: str, side: str, qty: float, price: float, *, timeout: float) -> dict[str, Any]:
    """IBKR's what-if for a ``side`` limit of ``qty`` at ``price``: ``{ok, init_change, maint_change, ...}``.

    ``ok`` false with ``error`` when IBKR is not ready, the account holds the stock, or IBKR does not
    answer within ``timeout``. Must run on the IB loop.
    """
    from ib_async import LimitOrder, Stock

    from ibkr import client as _client

    sym = (symbol or "").strip().upper()
    side_u = (side or "").strip().upper()
    q, p = float(qty), float(price)
    if side_u not in ("BUY", "SELL") or not (q > 0 and p > 0):
        return _refused(sym, side_u, q, p, "a what-if needs BUY or SELL, a quantity and a price")
    ib = _client.get_ib()
    if ib is None or not _client.is_ready():
        return _refused(sym, side_u, q, p, "IBKR is not connected")
    held = _held(ib, sym)
    if abs(held) > 1e-9:
        return _refused(sym, side_u, q, p, f"the account holds {held:g} {sym}: IBKR's what-if would net it")
    try:
        qualified = await asyncio.wait_for(ib.qualifyContractsAsync(Stock(sym, "SMART", "USD")), timeout)
        contract = next((c for c in qualified or [] if c is not None), None)
        if contract is None:
            return _refused(sym, side_u, q, p, f"IBKR could not qualify {sym}")
        order = LimitOrder(side_u, q, p)
        order.tif = "DAY"
        state = await asyncio.wait_for(ib.whatIfOrderAsync(contract, order), timeout)
    except asyncio.TimeoutError:
        return _refused(sym, side_u, q, p, f"IBKR's what-if did not answer within {timeout:g} s")
    except Exception as exc:  # an IBKR error is an answer: not this order's margin
        logger.warning("IBKR what-if for %s %g %s @ %g failed: %s", side_u, q, sym, p, exc)
        return _refused(sym, side_u, q, p, f"IBKR's what-if failed: {exc}")
    accounts = list(ib.managedAccounts() or [])
    return {
        "ok": True, "symbol": sym, "side": side_u, "qty": q, "price": p, "error": None, "ts": time.time(),
        "account": accounts[0] if accounts else None,
        "init_change": number(getattr(state, "initMarginChange", None)),
        "maint_change": number(getattr(state, "maintMarginChange", None)),
        "init_after": number(getattr(state, "initMarginAfter", None)),
        "maint_after": number(getattr(state, "maintMarginAfter", None)),
        "equity_with_loan_after": number(getattr(state, "equityWithLoanAfter", None)),
        "warning": str(getattr(state, "warningText", "") or "") or None,
    }
