"""
Paper-execution engine — Nova OS control modes (Phase P5).

Control modes (in-memory; restart → signal):
  signal     — display only; on_signal returns None
  confirm    — stage expiring tickets; human Approve places
  auto_paper — auto-place paper brackets when set_mode gates pass
  auto_live  — not enabled (no live money)

Safety model (defense in depth):
  1. Kill switch / force_signal — no new entries; staged rejected.
  2. risk.can_trade() + validate_trade_plan().
  3. One open executor position per symbol; max concurrent = open + staged.
  4. ibkr.orders.place_bracket_order() env/paper gates — never bypassed.

Emergency semantics:
  - kill_switch: force signal, reject staged, cancel ONLY unfilled parents
    (+ children). If parent already filled, protective stop/target are preserved.
  - cancel_working_entry: cancel one symbol's unfilled parent (+ children).
  - flatten_positions (strategy/executor_flatten.py): typed FLATTEN token;
    reconciles against IBKR's real position qty before selling — a tracked
    position whose parent never filled has nothing to sell and is dropped
    without an order; fail loud if IBKR unavailable.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

from constants import (
    EXECUTOR_ENTRY_SIDE_JOURNAL,
    EXECUTOR_FILL_POLL_INTERVAL_SEC,
    NOVA_OS_MAX_CONCURRENT_POSITIONS,
    NOVA_OS_MODE_CONFIRM,
    NOVA_OS_MODE_SIGNAL,
)
from ibkr import client as _ibkr_client
from ibkr import orders as _orders
from journal.store import record_trade
from nova_os import control_mode as _control_mode
from nova_os import staged_tickets as _staged
from nova_os.events import KIND_ACTION, KIND_SYSTEM, record_receipt
from strategy import executor_flatten as _executor_flatten
from strategy import executor_place as _executor_place
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


_kill_switch_tripped: bool = False
_open_positions: dict[str, OpenPosition] = {}

_MODE_DISCLOSURE = (
    "Control mode starts at signal on every restart and is never persisted. "
    "P5 allows signal (display), confirm (stage → Approve), and auto_paper "
    "(paper Gateway + orders enabled + risk clear + not holiday — places without "
    "Approve). auto_live stays blocked. Kill forces signal, rejects staged, and "
    "cancels only unfilled entry parents — protective stops on filled positions "
    "are preserved. Flatten requires typing FLATTEN."
)


def open_positions() -> dict[str, OpenPosition]:
    return _open_positions


def restore_tracked_position(pos: OpenPosition) -> None:
    """Startup recovery / tests — register a tracked position without placing."""
    _open_positions[pos.symbol.upper()] = pos


def is_armed() -> bool:
    """Legacy: True when mode is not signal and kill is clear (confirm stages)."""
    return (not _kill_switch_tripped) and _control_mode.get_mode() != NOVA_OS_MODE_SIGNAL


def is_kill_switch_tripped() -> bool:
    return _kill_switch_tripped


def status() -> dict:
    effective, loss_reason = _control_mode.get_effective_mode_detail()
    _staged.expire_due()
    return {
        "disclosure": _MODE_DISCLOSURE,
        "armed": is_armed(),
        "control_mode": _control_mode.get_mode(),
        "effective_mode": effective,
        "loss_policy_reason": loss_reason,
        "kill_switch_tripped": _kill_switch_tripped,
        "ibkr_connected": _ibkr_client.is_connected(),
        "ibkr_mode": _ibkr_client.account_mode(),
        "staged": [t.to_dict() for t in _staged.list_staged()],
        "open_positions": [
            {
                "symbol": p.symbol,
                "setup": p.setup,
                "qty": p.qty,
                "entry_price": p.entry_price,
                "stop_price": p.stop_price,
                "target_price": p.target_price,
                "opened_ts": p.opened_ts,
                "parent_order_id": p.parent_order_id,
                "target_order_id": p.target_order_id,
                "stop_order_id": p.stop_order_id,
            }
            for p in _open_positions.values()
        ],
    }


def arm() -> dict:
    """P4: arm → confirm mode (stage tickets).

    Does NOT clear a kill trip — kill switch is a deliberate stop that must
    be cleared explicitly via reset_kill_switch() before automation can be
    raised again. set_mode() raises ValueError if kill is still tripped.
    """
    _control_mode.set_mode(NOVA_OS_MODE_CONFIRM)
    logger.warning("EXECUTOR ARMED — confirm mode (stage tickets; Approve to place)")
    return status()


def disarm() -> dict:
    _control_mode.force_signal("disarm")
    logger.info("Executor disarmed → signal")
    return status()


def _cancel_bracket_if_parent_unfilled(pos: OpenPosition) -> tuple[list[int], str]:
    """Cancel parent+children only when parent is still in open_orders.

    Returns (cancelled_ids, outcome) where outcome is
    'cancelled_unfilled' | 'preserved_protective' | 'unknown_state'.
    Cancels go through execution.service (ADR 007).
    """
    if not _ibkr_client.is_connected():
        return [], "unknown_state"
    try:
        open_ids = {o["order_id"] for o in _orders.open_orders()}
    except _orders.IbkrAccountError as exc:
        # Cannot verify whether the parent is still working — treat as
        # unknown rather than guessing "unfilled" and cancelling a filled
        # position's live protective stop/target.
        logger.error("kill/cancel: open_orders failed for %s — %s", pos.symbol, exc)
        return [], "unknown_state"
    if pos.parent_order_id not in open_ids:
        return [], "preserved_protective"
    cancelled: list[int] = []
    for order_id in (pos.parent_order_id, pos.target_order_id, pos.stop_order_id):
        try:
            _cancel_via_service(order_id, source="kill")
            cancelled.append(order_id)
        except Exception:
            logger.exception("cancel failed for order %s (%s)", order_id, pos.symbol)
    return cancelled, "cancelled_unfilled"


def _cancel_via_service(order_id: int, *, source: str) -> dict:
    """Sync cancel helper for kill/flatten — uses execution.service."""
    import uuid
    from execution.models import ExecutionCommand
    from execution.service import execute

    async def _run():
        return await execute(
            ExecutionCommand(
                operation="cancel",
                idempotency_key=f"{source}:cancel:{order_id}:{uuid.uuid4()}",
                source=source,  # type: ignore[arg-type]
                order_id=order_id,
                skip_risk=True,
                skip_concurrency=True,
            ),
            wait_ack=False,
        )

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        receipt = asyncio.run(_run())
        return receipt.legacy_place_dict()
    # Nested in async context (e.g. fill poll) — schedule and do not block forever.
    # Kill/flatten routes are sync FastAPI handlers, so asyncio.run is the common path.
    raise RuntimeError("cancel from running loop — use async execute directly")


def kill_switch() -> dict:
    """Stop automation: force signal, reject staged, cancel unfilled parents only."""
    global _kill_switch_tripped
    _kill_switch_tripped = True
    _control_mode.force_signal("kill_switch")
    rejected = _staged.reject_all("kill_switch")
    cancelled: list[int] = []
    preserved: list[str] = []
    unknown: list[str] = []
    for symbol, pos in list(_open_positions.items()):
        ids, outcome = _cancel_bracket_if_parent_unfilled(pos)
        cancelled.extend(ids)
        if outcome == "preserved_protective":
            preserved.append(symbol)
        elif outcome == "unknown_state":
            unknown.append(symbol)
    record_receipt(
        kind=KIND_SYSTEM,
        mode=NOVA_OS_MODE_SIGNAL,
        payload={
            "event": "kill_switch",
            "cancelled_order_ids": cancelled,
            "preserved_symbols": preserved,
            "unknown_symbols": unknown,
            "rejected_staged": len(rejected),
        },
    )
    logger.warning(
        "KILL SWITCH — cancelled=%s preserved=%s unknown=%s staged_rejected=%s",
        cancelled, preserved, unknown, len(rejected),
    )
    return status()


def reset_kill_switch() -> dict:
    global _kill_switch_tripped
    _kill_switch_tripped = False
    return status()


def cancel_working_entry(symbol: str) -> dict:
    """Cancel one symbol's unfilled parent (+ children). Preserve filled stops."""
    symbol = symbol.upper()
    pos = _open_positions.get(symbol)
    if pos is None:
        return {"ok": False, "error": f"no tracked position for {symbol}", **status()}
    ids, outcome = _cancel_bracket_if_parent_unfilled(pos)
    if outcome == "cancelled_unfilled":
        del _open_positions[symbol]
        record_receipt(
            kind=KIND_ACTION,
            symbol=symbol,
            mode=_control_mode.get_mode(),
            payload={"event": "cancel_working_entry", "cancelled_order_ids": ids},
        )
        return {"ok": True, "cancelled_order_ids": ids, "outcome": outcome, **status()}
    return {
        "ok": False,
        "error": (
            "parent already filled — protective stop/target preserved"
            if outcome == "preserved_protective"
            else "IBKR not connected — cannot prove fill state; nothing cancelled"
        ),
        "outcome": outcome,
        **status(),
    }


flatten_preview = _executor_flatten.flatten_preview
flatten_positions = _executor_flatten.flatten_positions


# Placement / on_signal live in executor_place (file-size + ADR 007 boundary).
place_from_ticket = _executor_place.place_from_ticket
place_from_ticket_async = _executor_place.place_from_ticket_async
on_signal = _executor_place.on_signal


def _resolve_exit_price(ib, pos: OpenPosition) -> float | None:
    exit_price: float | None = None
    for fill in ib.fills():
        if fill.contract.symbol != pos.symbol:
            continue
        if fill.execution.orderId in (pos.target_order_id, pos.stop_order_id):
            exit_price = float(fill.execution.avgPrice)
    return exit_price


async def _check_fills_once() -> None:
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
            # Legs are gone from open_orders but no matching fill was found
            # (e.g. cancelled before any fill, or fills() aged out of the IB
            # cache). Recovery must still be able to see this symbol closed —
            # an unverified close is still a close, not silence.
            record_receipt(
                kind=KIND_ACTION,
                symbol=symbol,
                mode=_control_mode.get_mode(),
                would_execute=True,
                executed=True,
                payload={
                    "event": "bracket_closed_unverified",
                    "parent_order_id": pos.parent_order_id,
                    "target_order_id": pos.target_order_id,
                    "stop_order_id": pos.stop_order_id,
                },
            )
            logger.warning(
                "Executor: %s bracket legs gone but no fill found — dropped without journal entry",
                symbol,
            )
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
            adherent=True,
            opened_ts=pos.opened_ts,
            closed_ts=time.time(),
            notes=f"Automated paper bracket (parent order {pos.parent_order_id}).",
        )
        _risk.record_trade_result(pnl)
        record_receipt(
            kind=KIND_ACTION,
            symbol=symbol,
            mode=_control_mode.get_mode(),
            would_execute=True,
            executed=True,
            payload={
                "event": "bracket_closed",
                "exit_price": exit_price,
                "pnl": pnl,
                "parent_order_id": pos.parent_order_id,
                "target_order_id": pos.target_order_id,
                "stop_order_id": pos.stop_order_id,
            },
        )
        logger.warning("Executor: %s bracket closed, exit=%.2f pnl=%.2f", symbol, exit_price, pnl)


async def fill_poll_loop() -> None:
    while True:
        try:
            await _check_fills_once()
            _staged.expire_due()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Executor: fill poll iteration failed")
        await asyncio.sleep(EXECUTOR_FILL_POLL_INTERVAL_SEC)
