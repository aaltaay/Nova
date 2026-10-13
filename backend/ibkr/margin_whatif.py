"""IBKR's what-if margin for one order: nothing is placed (ADR 048 decision 2).

``ib.whatIfOrderAsync`` sends a copy of the order with ``whatIf`` set. IBKR answers with the margin
the order would take -- initial and maintenance, before and after, and the account's equity with
loan -- and never transmits it; ib_async settles the answer without making a trade or firing an
order event. This module is that API's only caller in Nova. It never calls ``placeOrder``, holds no
order and needs no spend gate: a what-if spends nothing.

The answer is the session's account (the Live account; the legacy paper Gateway's when that is the
login). When the account already holds the stock, IBKR nets the order against the position, so
the change is not this order's requirement: Nova refuses to read it (``holds``). The limit sits on
the listed tick (``on_tick``): IBKR refuses an off-tick price with Error 110, and a setup's entry can
carry a sub-penny print's price.

IBKR may refuse the what-if itself: a cash account answers Error 201 to every one (a short "can only
be held in a margin account"; a buy over the settled cash). That is the probe's answer, not an
order's. So the module keeps the reqIds it sent (``sent``) and says a refusal in plain words
(``plain_reason``): the answer carries the reason to the short check, and ``ibkr.log_filters``
rewrites ib_async's ERROR line for one (``probe_line``), a WARNING when the code is expected.

Runs on the IB loop (``ibkr.loop_supervisor.on_ib``). Owns one state: the reqIds it sent, for
``SHORT_WHATIF_REQID_TTL_SEC``.
"""
from __future__ import annotations

import asyncio
import logging
import math
import re
import threading
import time
from collections import OrderedDict
from typing import Any

from constants_shorts import (
    SHORT_WHATIF_EXPECTED_CODES,
    SHORT_WHATIF_REQID_MAX,
    SHORT_WHATIF_REQID_TTL_SEC,
    STOCK_SUBPENNY_TICK,
    STOCK_SUBPENNY_UNDER,
    STOCK_TICK,
)

logger = logging.getLogger(__name__)

# IBKR's "no value" double (ib_async UNSET_DOUBLE): any figure this large is not a figure.
_UNSET_FLOOR = 1e300
# ib_async's line for an IBKR error: "Error 201, reqId 285103: Order rejected - reason:...".
_LOG_LINE_RE = re.compile(r"^(?:error|warning) (\d+), reqid (-?\d+): (.*)$", re.IGNORECASE | re.DOTALL)
_REJECTED_RE = re.compile(r"^\s*order rejected\s*-\s*reason:\s*", re.IGNORECASE)
# "AVAILABLE SETTLED CASH CONVERTED TO BASE: 347.44 USD CASH NEEDED FOR THIS ORDER ...: 2525.00 USD"
_SETTLED_CASH_RE = re.compile(r"settled cash[^:]*:\s*([\d,.]+)\s*([a-z]{3}).*?needed[^:]*:\s*([\d,.]+)\s*([a-z]{3})",
                              re.IGNORECASE | re.DOTALL)

_PROBE_LINE = ("IBKR refused Nova's margin what-if for %s (nothing was placed): %s. "
               "Nova uses the published margin rules for %s (IBKR Error %s, reqId %s)")

_sent: OrderedDict[int, tuple[float, str, str]] = OrderedDict()   # reqId -> (sent at, the order, symbol)
_sent_lock = threading.Lock()


def number(raw: Any) -> float | None:
    """One of the OrderState's strings as a float; None when IBKR left it unset."""
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value) or abs(value) >= _UNSET_FLOOR:
        return None
    return value


def on_tick(price: float) -> float:
    """``price`` on the listed tick: the nearest cent at $1.00 and over, hundredth of a cent under."""
    tick = STOCK_TICK if price >= STOCK_SUBPENNY_UNDER else STOCK_SUBPENNY_TICK
    return max(tick, round(round(price / tick) * tick, 4))


def plain_reason(code: int, text: str) -> str:
    """IBKR's refusal of a what-if in plain words."""
    body = _REJECTED_RE.sub("", str(text or "")).strip().rstrip(".")
    low = body.lower()
    if code == 201 and "margin account" in low:
        return "the IBKR account is a cash account, which cannot hold a short"
    if code == 201 and "settled cash" in low:
        m = _SETTLED_CASH_RE.search(body)
        if m:
            return (f"the IBKR account is a cash account, and its settled cash ({m[1]} {m[2].upper()}) is under "
                    f"the {m[3]} {m[4].upper()} this order needs")
        return "the IBKR account is a cash account, and its settled cash is under what this order needs"
    if code == 110:
        return "IBKR refused the limit as off the stock's tick"
    return f"IBKR refused it: {body} (Error {code})"


def sent(req_id: int, *, now: float | None = None) -> tuple[str, str] | None:
    """``(the order, symbol)`` a what-if Nova sent under ``req_id`` asked about ("SELL 33 JBDI @ 5.47"),
    while it is younger than ``SHORT_WHATIF_REQID_TTL_SEC``; None for any other reqId (an order's)."""
    t = time.time() if now is None else float(now)
    with _sent_lock:
        got = _sent.get(int(req_id))
    if got is None or t - got[0] > SHORT_WHATIF_REQID_TTL_SEC:
        return None
    return got[1], got[2]


def probe_line(message: str, *, now: float | None = None) -> tuple[str, tuple[Any, ...], bool] | None:
    """ib_async's ``Error <code>, reqId <id>: <text>`` line in plain words when ``<id>`` is a what-if
    this module sent: ``(template, args, expected)`` -- a log record's ``msg`` and ``args``, so Sentry
    groups by the template, and whether the code is IBKR's expected answer
    (``SHORT_WHATIF_EXPECTED_CODES``). None for any other line: an order's reject is never rewritten."""
    m = _LOG_LINE_RE.match(str(message or "").strip())
    if not m:
        return None
    code, req_id = int(m[1]), int(m[2])
    got = sent(req_id, now=now)
    if got is None:
        return None
    order, symbol = got
    return _PROBE_LINE, (order, plain_reason(code, m[3]), symbol, code, req_id), code in SHORT_WHATIF_EXPECTED_CODES


def _note(req_id: int, order: str, symbol: str) -> None:
    with _sent_lock:
        _sent[req_id] = (time.time(), order, symbol)
        _sent.move_to_end(req_id)
        while len(_sent) > SHORT_WHATIF_REQID_MAX:
            _sent.popitem(last=False)


def _sent_id(ib: Any, fut: Any) -> int | None:
    """The orderId ib_async gave the what-if whose future is ``fut`` (its request registry's
    ``WhatIfKey``); None when the registry does not say, and IBKR's refusal then stays an ERROR."""
    registry = getattr(getattr(ib, "wrapper", None), "requests", None)
    if registry is None:
        return None
    try:
        for req in registry:
            if getattr(req, "future", None) is fut:
                order_id = getattr(getattr(req, "key", None), "orderId", None)
                return int(order_id) if order_id is not None else None
    except Exception as exc:  # an ib_async that keeps its requests otherwise: the refusal stays an ERROR
        logger.warning("IBKR what-if: could not read the reqId ib_async gave it: %s", exc)
    return None


async def _what_if(ib: Any, contract: Any, order: Any, symbol: str, timeout: float) -> tuple[Any, str | None]:
    """Send the what-if, keep its reqId, and wait: ``(OrderState, None)``, or ``(None, why)`` when IBKR
    refused it (ib_async settles a refused what-if with its empty accumulator, ``[]``, not an OrderState;
    ``ib.errorEvent`` says why)."""
    refusals: list[tuple[int, str]] = []
    ids: list[int] = []

    def on_error(req_id: int, code: int, text: str, *_: Any) -> None:
        if ids and req_id == ids[0]:
            refusals.append((int(code), str(text)))

    event = getattr(ib, "errorEvent", None)
    if event is not None:
        event.connect(on_error)
    try:
        fut = ib.whatIfOrderAsync(contract, order)
        req_id = _sent_id(ib, fut)
        if req_id is not None:     # before the first await: IBKR's answer cannot arrive sooner
            ids.append(req_id)
            _note(req_id, f"{order.action} {order.totalQuantity:g} {symbol} @ {order.lmtPrice:g}", symbol)
        state = await asyncio.wait_for(fut, timeout)
    finally:
        if event is not None:
            event.disconnect(on_error)
    if state is None or not hasattr(state, "maintMarginChange"):
        return None, plain_reason(*refusals[-1]) if refusals else None
    return state, None


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
    """IBKR's what-if for a ``side`` limit of ``qty`` at ``price`` (on its tick): ``{ok, init_change, ...}``.

    ``ok`` false with ``error`` when IBKR is not ready, the account holds the stock, IBKR refuses the
    what-if (why, in plain words) or does not answer within ``timeout``. Must run on the IB loop.
    """
    from ib_async import LimitOrder, Stock

    from ibkr import client as _client

    sym = (symbol or "").strip().upper()
    side_u = (side or "").strip().upper()
    q, p = float(qty), float(price)
    if side_u not in ("BUY", "SELL") or not (q > 0 and p > 0):
        return _refused(sym, side_u, q, p, "a what-if needs BUY or SELL, a quantity and a price")
    p = on_tick(p)
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
        state, refusal = await _what_if(ib, contract, order, sym, timeout)
    except asyncio.TimeoutError:
        return _refused(sym, side_u, q, p, f"IBKR's what-if did not answer within {timeout:g} s")
    except Exception as exc:  # an IBKR error is an answer: not this order's margin
        logger.warning("IBKR what-if for %s %g %s @ %g failed: %s", side_u, q, sym, p, exc)
        return _refused(sym, side_u, q, p, f"IBKR's what-if failed: {exc}")
    if state is None:
        return _refused(sym, side_u, q, p, refusal or "IBKR answered the what-if with no figures")
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


def reset_for_tests() -> None:
    with _sent_lock:
        _sent.clear()
