"""
Paper-execution engine (Phase D). Consumes risk-approved setup signals and
places IBKR bracket orders. Disarmed by default and on every restart —
signals stay display-only until a human explicitly hits "Arm Automation" in
the UI.

Safety model (defense in depth; each layer is independent of the others):
  1. `is_armed()` must be True — always starts False, never persisted.
  2. `risk.can_trade()` — session halts (daily max loss, loss streaks, giveback).
  3. `risk.validate_trade_plan()` — stop-distance ceiling + minimum profit/loss ratio.
  4. Only one open executor position per symbol at a time (no pyramiding).
  5. `ibkr.orders.place_bracket_order()`'s own IBKR_ENABLED / paper-vs-live gate
     (see backend/ibkr/orders.py) — this is the last line of defense and is
     never bypassed, even if every check above were somehow removed.

Known limitations (by design, not oversight):
  - Open positions are tracked in memory only. A backend restart while a
    bracket is still working loses the in-app position record (IB itself
    still has the real orders/position; this module just stops watching
    them and will not journal that trade). Acceptable for a paper-trading
    learning tool; would need durable state before ever being used live.
  - `kill_switch()` disarms and cancels this module's own open bracket
    orders. It does NOT flatten a position that already filled — closing an
    open position is a deliberate decision this module does not make for you.
  - A trade is only written to the journal once, when its bracket fully
    closes (matches the original design note in journal/store.py). No row
    exists for a position that is still open.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

from constants import (
    EXECUTOR_ENTRY_SIDE_IBKR,
    EXECUTOR_ENTRY_SIDE_JOURNAL,
    EXECUTOR_FILL_POLL_INTERVAL_SEC,
)
from ibkr import client as _ibkr_client
from ibkr import orders as _orders
from journal.store import record_trade
from strategy import risk as _risk

logger = logging.getLogger(__name__)


@dataclass
class OpenPosition:
    symbol: str
    setup: str
    qty: int
    entry_price: float
    stop_price: float
    target_price: float
    parent_order_id: int
    target_order_id: int
    stop_order_id: int
    opened_ts: float


# ── Module-level state — mirrors risk.py's singleton pattern ────────────────
_armed: bool = False
_kill_switch_tripped: bool = False
_open_positions: dict[str, OpenPosition] = {}

_ARM_DISCLOSURE = (
    "Arming automation places PAPER bracket orders (entry + stop + target) on "
    "IBKR whenever an already risk-approved setup signal fires, with no "
    "further confirmation per trade. Paper account only, unless "
    "IBKR_LIVE_TRADING_CONFIRMED=true is also set in .env. Disarmed by "
    "default and on every backend restart."
)


def is_armed() -> bool:
    return _armed and not _kill_switch_tripped


def status() -> dict:
    return {
        "disclosure": _ARM_DISCLOSURE,
        "armed": _armed,
        "kill_switch_tripped": _kill_switch_tripped,
        "ibkr_connected": _ibkr_client.is_connected(),
        "ibkr_mode": _ibkr_client.account_mode(),
        "open_positions": [
            {
                "symbol": p.symbol,
                "setup": p.setup,
                "qty": p.qty,
                "entry_price": p.entry_price,
                "stop_price": p.stop_price,
                "target_price": p.target_price,
                "opened_ts": p.opened_ts,
            }
            for p in _open_positions.values()
        ],
    }


def arm() -> dict:
    global _armed, _kill_switch_tripped
    _kill_switch_tripped = False
    _armed = True
    logger.warning("EXECUTOR ARMED — will place paper bracket orders on risk-approved signals")
    return status()


def disarm() -> dict:
    global _armed
    _armed = False
    logger.info("Executor disarmed")
    return status()


def kill_switch() -> dict:
    """Immediately disarms and cancels every bracket order this module has
    open. Does not flatten a position that has already filled."""
    global _armed, _kill_switch_tripped
    _armed = False
    _kill_switch_tripped = True
    cancelled: list[int] = []
    for symbol, pos in list(_open_positions.items()):
        for order_id in (pos.parent_order_id, pos.target_order_id, pos.stop_order_id):
            try:
                _orders.cancel_order(order_id)
                cancelled.append(order_id)
            except Exception:
                logger.exception("kill_switch: failed to cancel order %s for %s", order_id, symbol)
    logger.warning("KILL SWITCH TRIPPED — disarmed, requested cancel of orders: %s", cancelled)
    return status()


def reset_kill_switch() -> dict:
    """Clears the tripped flag WITHOUT re-arming — call arm() separately."""
    global _kill_switch_tripped
    _kill_switch_tripped = False
    return status()


async def on_signal(symbol: str, setup_name: str, signal_dict: dict) -> dict | None:
    """Called by setups_stream right after a new eligible signal is recorded.
    Returns the position dict if a bracket order was placed, else None."""
    if not is_armed():
        return None
    if symbol in _open_positions:
        return None  # one executor position per symbol at a time

    entry = signal_dict.get("entry_price")
    stop = signal_dict.get("stop_price")
    target = signal_dict.get("target_price")
    if entry is None or stop is None or target is None:
        return None

    can_trade, halt_reason = _risk.can_trade()
    if not can_trade:
        logger.info("Executor: %s/%s skipped — risk halt: %s", symbol, setup_name, halt_reason)
        return None

    plan_ok, issues = _risk.validate_trade_plan(entry, stop, target)
    if not plan_ok:
        logger.info("Executor: %s/%s failed risk validation: %s", symbol, setup_name, issues)
        return None

    qty = _risk.position_size_shares()
    if qty <= 0:
        return None

    result = _orders.place_bracket_order(symbol, EXECUTOR_ENTRY_SIDE_IBKR, qty, entry, stop, target)
    if not result["ok"]:
        logger.warning("Executor: bracket order rejected for %s: %s", symbol, result["error"])
        return None

    pos = OpenPosition(
        symbol=symbol,
        setup=setup_name,
        qty=qty,
        entry_price=entry,
        stop_price=stop,
        target_price=target,
        parent_order_id=result["parent_order_id"],
        target_order_id=result["target_order_id"],
        stop_order_id=result["stop_order_id"],
        opened_ts=time.time(),
    )
    _open_positions[symbol] = pos
    logger.warning(
        "Executor: placed paper bracket %s/%s qty=%s entry=%s stop=%s target=%s (parent=%s)",
        symbol, setup_name, qty, entry, stop, target, pos.parent_order_id,
    )
    return status()["open_positions"][-1]


def _resolve_exit_price(ib, pos: OpenPosition) -> float | None:
    """Look up the fill that closed this bracket's target or stop leg."""
    exit_price: float | None = None
    for fill in ib.fills():
        if fill.contract.symbol != pos.symbol:
            continue
        if fill.execution.orderId in (pos.target_order_id, pos.stop_order_id):
            exit_price = float(fill.execution.avgPrice)
    return exit_price


async def _check_fills_once() -> None:
    """Poll IBKR's open orders; once none of a tracked position's three
    bracket legs remain open, the bracket has finished (filled or was
    cancelled) — resolve the outcome and journal it."""
    if not _open_positions:
        return
    ib = _ibkr_client.get_ib()
    if ib is None:
        return

    open_ids = {o["order_id"] for o in _orders.open_orders()}
    for symbol, pos in list(_open_positions.items()):
        still_open = {pos.parent_order_id, pos.target_order_id, pos.stop_order_id} & open_ids
        if still_open:
            continue

        exit_price = _resolve_exit_price(ib, pos)
        del _open_positions[symbol]
        if exit_price is None:
            # No fill found (e.g. cancelled before the entry ever filled) —
            # nothing to journal.
            continue

        pnl = (exit_price - pos.entry_price) * pos.qty
        record_trade(
            symbol=pos.symbol,
            setup=pos.setup,
            side=EXECUTOR_ENTRY_SIDE_JOURNAL,
            qty=pos.qty,
            entry_price=pos.entry_price,
            stop_price=pos.stop_price,
            target_price=pos.target_price,
            exit_price=exit_price,
            pnl=pnl,
            adherent=True,  # automation never deviates from the risk-approved plan
            opened_ts=pos.opened_ts,
            closed_ts=time.time(),
            notes=f"Automated paper bracket (parent order {pos.parent_order_id}).",
        )
        _risk.record_trade_result(pnl)
        logger.warning("Executor: %s bracket closed, exit=%.2f pnl=%.2f", symbol, exit_price, pnl)


async def fill_poll_loop() -> None:
    """Background asyncio task — call once from the app lifespan, mirrors
    setups_stream.scan_loop()'s pattern."""
    while True:
        try:
            await _check_fills_once()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Executor: fill poll iteration failed")
        await asyncio.sleep(EXECUTOR_FILL_POLL_INTERVAL_SEC)
