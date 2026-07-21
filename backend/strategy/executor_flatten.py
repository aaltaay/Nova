"""
Nova OS deliberate flatten — extracted from strategy/executor.py to keep that
module under the file-size-limits.mdc ceiling (backend-modularity.mdc: each
domain concern gets its own module).

Reconciles against IBKR's REAL position qty before selling anything. A
tracked executor position whose parent never filled has NOTHING to sell —
placing a market SELL there would open an accidental short. Cancels
protective legs unconditionally on a real close, since a stale SELL
stop/target left open after the position is gone could fire against a
future position in the same symbol.

Lazily imports `strategy.executor` inside each function (not at module load
time) so `executor.py` can import this module at its own top level without a
circular-import — `executor` -> `executor_flatten` -> (deferred) `executor`.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from constants import NOVA_OS_FLATTEN_CONFIRM_TOKEN
from ibkr import account as _account
from ibkr import client as _ibkr_client
from ibkr import orders as _orders
from ibkr.errors import IbkrAccountError
from nova_os import control_mode as _control_mode
from nova_os.events import KIND_ACTION, record_receipt

if TYPE_CHECKING:
    from strategy.executor import OpenPosition

logger = logging.getLogger(__name__)


def flatten_preview() -> dict:
    from strategy import executor as _executor

    tracked = [
        {
            "symbol": p.symbol,
            "qty": p.qty,
            "side": "SELL",
            "entry_price": p.entry_price,
            "stop_order_id": p.stop_order_id,
            "target_order_id": p.target_order_id,
            "source": "executor_tracked",
        }
        for p in _executor.open_positions().values()
    ]
    try:
        ibkr_positions = _account.get_positions()
        ibkr_positions_error = None
    except IbkrAccountError as exc:
        ibkr_positions = []
        ibkr_positions_error = str(exc)
    return {
        "disclosure": (
            f"Flatten closes tracked executor longs with a market SELL and cancels "
            f"working bracket legs when the parent is still unfilled. Type "
            f"{NOVA_OS_FLATTEN_CONFIRM_TOKEN} to confirm. Protective stops are "
            f"cancelled only as part of this deliberate flatten."
        ),
        "confirm_token_required": NOVA_OS_FLATTEN_CONFIRM_TOKEN,
        "account_mode": _ibkr_client.account_mode(),
        "ibkr_connected": _ibkr_client.is_connected(),
        "positions": tracked,
        "ibkr_positions": ibkr_positions,
        "ibkr_positions_error": ibkr_positions_error,
    }


def _actual_position_qty(symbol: str) -> float | None:
    """Real IBKR long qty for `symbol`, or None if verified flat.

    Uses ``account.long_qty`` (``ib.positions()`` SSOT) — same as validate
    anti-short. Raises ``IbkrAccountError`` when the read fails — callers must
    not treat that as "no position", or a transient failure could make
    ``flatten_positions`` skip selling a real position and cancel its
    protective stop/target instead.
    """
    qty = _account.long_qty(symbol)
    return qty if qty > 0 else None


def _cancel_protective_legs(pos: "OpenPosition") -> list[int]:
    """Unconditionally cancel the stop + target children (and the parent, if
    it is still working). Used only by a deliberate flatten: once we place a
    market close, the old bracket's protective legs must not survive it —
    a stale SELL stop/target left open after the position is gone can fire
    against a future position in the same symbol.

    Cancels go through execution.service (ADR 007).
    """
    from strategy.executor import _cancel_via_service

    cancelled: list[int] = []
    open_ids: set = set()
    if _ibkr_client.is_connected():
        try:
            open_ids = {o["order_id"] for o in _orders.open_orders()}
        except IbkrAccountError:
            # Cannot verify which legs are still working — leave them alone
            # rather than guessing. We're about to sell the real qty below
            # regardless, so a leg we fail to cancel here is not a new risk.
            logger.exception("flatten: open_orders failed for %s — leaving legs uncancelled", pos.symbol)
    for order_id in (pos.parent_order_id, pos.target_order_id, pos.stop_order_id):
        if order_id not in open_ids:
            continue
        try:
            _cancel_via_service(order_id, source="flatten")
            cancelled.append(order_id)
        except Exception:
            logger.exception("flatten: cancel failed for order %s (%s)", order_id, pos.symbol)
    return cancelled


def _flatten_market_sell(symbol: str, qty: float) -> dict:
    """Market SELL through the centralized execution path (ADR 007)."""
    import asyncio
    import uuid
    from execution.models import ExecutionCommand
    from execution.service import execute

    async def _run():
        return await execute(
            ExecutionCommand(
                operation="place",
                idempotency_key=f"flatten:sell:{symbol}:{uuid.uuid4()}",
                source="flatten",
                symbol=symbol,
                side="SELL",
                qty=qty,
                order_type="MKT",
                skip_risk=True,
                skip_concurrency=True,
            ),
            wait_ack=False,
        )

    receipt = asyncio.run(_run())
    return receipt.legacy_place_dict()


def flatten_positions(confirm_token: str) -> dict:
    """Market-close tracked longs — reconciled against IBKR's real position
    qty, not the in-memory claim. A tracked position whose parent never
    filled has NOTHING to sell; placing a SELL there would open a short by
    accident. Cancel its (unfilled) legs and drop it instead of selling.
    """
    from strategy import executor as _executor

    if confirm_token != NOVA_OS_FLATTEN_CONFIRM_TOKEN:
        raise ValueError(
            f"flatten requires confirm_token={NOVA_OS_FLATTEN_CONFIRM_TOKEN!r}"
        )
    if not _ibkr_client.is_connected():
        return {
            "ok": False,
            "error": "IBKR not connected — cannot flatten; close manually in TWS/Gateway",
            "preview": flatten_preview(),
        }

    open_positions = _executor.open_positions()
    results: list[dict] = []
    for symbol, pos in list(open_positions.items()):
        try:
            actual_qty = _actual_position_qty(symbol)
        except IbkrAccountError as exc:
            # Cannot verify real IBKR qty — abort rather than assume flat.
            # Positions already processed this call are untouched; the rest
            # (including this symbol) are left tracked for a retry.
            logger.exception("flatten: aborting — cannot verify %s position at IBKR", symbol)
            return {
                "ok": False,
                "error": (
                    f"IBKR position check failed for {symbol} — flatten aborted, "
                    f"no orders touched for remaining positions: {exc}"
                ),
                "results": results,
                **_executor.status(),
            }

        if actual_qty is None:
            # No real position at IBKR — the parent never filled (or it's
            # already flat). Cancel any working legs; do NOT sell.
            cancelled = _cancel_protective_legs(pos)
            row = {
                "symbol": symbol,
                "qty": pos.qty,
                "outcome": "no_position_skipped_sell",
                "cancelled_order_ids": cancelled,
                "close": None,
            }
            results.append(row)
            del open_positions[symbol]
            logger.warning(
                "flatten: %s has no real IBKR position — skipped sell, cancelled legs %s",
                symbol, cancelled,
            )
            continue

        if abs(actual_qty - pos.qty) > 1e-6:
            logger.warning(
                "flatten: %s tracked qty=%s but IBKR reports qty=%s — closing IBKR's qty",
                symbol, pos.qty, actual_qty,
            )
        sell_qty = actual_qty

        cancelled = _cancel_protective_legs(pos)
        close = _flatten_market_sell(symbol, float(sell_qty))
        row = {
            "symbol": symbol,
            "qty": sell_qty,
            "outcome": "closed_real_position",
            "cancelled_order_ids": cancelled,
            "close": close,
        }
        results.append(row)
        if close.get("ok"):
            del open_positions[symbol]
        else:
            logger.error("flatten: market close failed for %s: %s", symbol, close.get("error"))

    ok = all(r["close"] is None or r["close"].get("ok") for r in results) if results else True
    record_receipt(
        kind=KIND_ACTION,
        mode=_control_mode.get_mode(),
        would_execute=True,
        executed=ok and bool(results),
        payload={"event": "flatten", "results": results},
    )
    return {"ok": ok, "results": results, **_executor.status()}
