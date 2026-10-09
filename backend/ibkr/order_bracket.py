"""IBKR's bracket order: three legs that reach IBKR whole, or are taken back.

maintainer: one-concern a Live bracket never leaves its entry at IBKR without the legs it was sent with

``ib.bracketOrder`` sends the entry and the target with ``transmit=False`` and the stop with
``transmit=True``: the Gateway holds the first two until the stop transmits all three. Two ways that
leaves an entry behind, both reported by other projects on IBKR's API:

- a later leg's ``placeOrder`` raises after the earlier ones went: the stop never transmits, so the
  entry and target sit untransmitted at the Gateway (and in ib_async's trades as PendingSubmit,
  which the desk lists as working). ``place_bracket_order`` cancels the legs that went;
- IBKR refuses a leg as the stop transmits: the entry can stay held, or work without its stop.
  ``take_back`` cancels the entry and its exits; ``execution.live_send`` calls it when a leg is
  refused before it ever worked (``IBKR_BRACKET_LEG_REFUSAL_WINDOW_SEC``).

Adapter only -- callers enter via ``execution.service.execute`` (ADR 007). The cancels here are the
bracket send's own: they take back what that one send put at IBKR, on Live whatever the desk shows.
"""
from __future__ import annotations

import logging

from ibkr import client as _client
from ibkr import safety as _safety
from ibkr.order_build import OrderSide, normalize_tif, tif_error as _tif_error
from sim.account_hooks import practice_refusal as _practice_refusal

logger = logging.getLogger(__name__)


def _failure(error: str, mode: str, **extra) -> dict:
    return {
        "ok": False, "parent_order_id": None, "target_order_id": None,
        "stop_order_id": None, "error": error, "mode": mode, **extra,
    }


def leg_ref(order_ref: str | None, role: str) -> str | None:
    """The reference an exit leg carries: the entry's plus its role (``-tp`` / ``-sl``)."""
    from constants_ibkr import IBKR_ORDER_REF_LEG_SUFFIX

    return f"{order_ref}{IBKR_ORDER_REF_LEG_SUFFIX[role]}" if order_ref else None


def _cancel_legs(ib, orders: list) -> tuple[list[int], list[int]]:
    """Cancel each of ``orders`` (exits first, then the entry): ``(cancelled ids, ids not cancelled)``."""
    cancelled: list[int] = []
    failed: list[int] = []
    for order in reversed(orders):
        try:
            ib.cancelOrder(order)
            cancelled.append(int(order.orderId))
        except Exception:
            logger.exception("IBKR bracket: the cancel of leg %s could not be sent", getattr(order, "orderId", None))
            failed.append(int(getattr(order, "orderId", 0) or 0))
    return cancelled, failed


def place_bracket_order(
    symbol: str,
    side: OrderSide,
    qty: int,
    entry_price: float,
    stop_price: float,
    target_price: float,
    tif: str | None = None,
    outside_rth: bool = False,
    order_ref: str | None = None,
) -> dict:
    """
    Place a bracket order: a LMT entry with a linked LMT profit target and a
    linked STP loss. Uses ib_async's native IB.bracketOrder() helper.
    ``tif`` / ``outside_rth`` apply to all three legs (None tif = DAY).
    ``order_ref`` is the entry's reference; the exits carry it with their role.
    """
    from ibkr import orders as _orders
    from sim.mode import is_practice_venue

    if is_practice_venue():
        from sim.guard import refuse_bracket

        return _practice_refusal(refuse_bracket())

    tif = normalize_tif(tif)
    bad_tif = _tif_error(tif)
    if bad_tif:
        return _failure(bad_tif, _client.account_mode())

    ok, reason = _orders._safety_check()
    if not ok:
        logger.warning("IBKR bracket order blocked: %s", reason)
        return _failure(reason, _client.account_mode())

    ib = _client.get_ib()
    if ib is None:
        return _failure("Not connected", "disconnected")

    try:
        from ib_async import Stock
        contract = Stock(symbol, "SMART", "USD")
        from ibkr.order_times import remember_nova_placed, wall_utc_now_iso

        def _place_bracket():
            bracket = ib.bracketOrder(
                side, qty, entry_price, target_price, stop_price,
                tif=tif, outsideRth=bool(outside_rth),
            )
            if order_ref:
                bracket.parent.orderRef = order_ref
                bracket.takeProfit.orderRef = leg_ref(order_ref, "target")
                bracket.stopLoss.orderRef = leg_ref(order_ref, "stop")
            nova_stamp = wall_utc_now_iso()
            sent: list = []
            for order in bracket:
                try:
                    ib.placeOrder(contract, order)
                except Exception as exc:
                    # The leg that raised -- the entry included -- may have reached the Gateway before it
                    # did: it is cancelled with the legs before it.
                    cancelled, failed = _cancel_legs(ib, [*sent, order])
                    return None, nova_stamp, exc, cancelled, failed
                sent.append(order)
                remember_nova_placed(order.orderId, nova_stamp)
            return bracket, nova_stamp, None, [], []

        bracket, nova_stamp, broke, cancelled, failed = _orders._ib_sync(_place_bracket, "placeOrder")
        if broke is not None:
            error = f"the bracket broke while its legs went to the Gateway ({broke}); the stop never transmitted them"
            if failed:
                error += f". Nova could NOT cancel order(s) {', '.join(map(str, failed))}: cancel them in TWS"
            else:
                error += f", and Nova cancelled them ({', '.join(map(str, cancelled))})"
            logger.error("IBKR: %s bracket for %s: %s", _client.account_mode(), symbol, error)
            return _failure(error, _client.account_mode(), taken_back=cancelled, not_taken_back=failed)
        logger.info(
            "IBKR: placed %s bracket %s %s qty=%s entry=%s target=%s stop=%s "
            "tif=%s outside_rth=%s ref=%s (parent=%s nova_placed_at_utc=%s)",
            _client.account_mode(), side, symbol, qty, entry_price, target_price, stop_price,
            tif, bool(outside_rth), order_ref, bracket.parent.orderId, nova_stamp,
        )
        return {
            "ok": True,
            "parent_order_id": bracket.parent.orderId,
            "target_order_id": bracket.takeProfit.orderId,
            "stop_order_id": bracket.stopLoss.orderId,
            "error": None,
            "mode": _client.account_mode(),
            "submitted_at": nova_stamp,
            "nova_placed_at": nova_stamp,
        }
    except Exception as exc:
        logger.exception("IBKR: bracket order error for %s: %s", symbol, exc)
        return _failure(str(exc), _client.account_mode())


def take_back(order_ids: list[int]) -> tuple[list[int], list[int]]:
    """Cancel a refused bracket's legs (entry first in ``order_ids``) on IBKR, on the IB loop.

    ``(cancelled ids, ids not cancelled)``; the exits are cancelled before the entry.

    Live whatever the desk shows (the bracket went to Live); refused only while IBKR cannot take a
    cancel at all (disconnected), which leaves every id in the second list.
    """
    ok, reason = _safety.assert_cancel_allowed(
        client_enabled=_client.is_enabled(), connected=_client.is_connected(),
    )
    ib = _client.get_ib()
    ids = [int(i) for i in order_ids if i]
    if not ok or ib is None:
        logger.error("IBKR bracket: legs %s could not be taken back -- %s", ids, reason or "not connected")
        return [], ids
    from ib_async import Order

    return _cancel_legs(ib, [Order(orderId=i) for i in ids])
