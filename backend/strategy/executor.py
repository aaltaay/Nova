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

Kill switch scope (D-037 decision, 2026-09-11):
  Kill means "no Nova-originated spend of ANY source until reset" — not
  "stop automation". `execution.service.execute` refuses every place/bracket
  while the latch is set, including manual ticket places and Nova Action
  hotkeys that pass `skip_risk=True`. Only the protective sources
  (kill / flatten / cancel_working) may still reach the broker.
  The latch is persisted (strategy/kill_switch_state.py) so an API restart
  cannot silently re-arm the desk; only reset_kill_switch() clears it.

Emergency semantics:
  - kill_switch: force signal, reject staged, cancel unfilled parents
    (+ children), then cancel every other open order on the account so a
    manual working LMT cannot fill after the kill. If a parent already
    filled, its protective stop/target are preserved.
  - cancel_working_entry: cancel one symbol's unfilled parent (+ children).
  - Cancel mechanics live in strategy/executor_cancel.py (ADR 007 cancels).
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
    NOVA_OS_MODE_CONFIRM,
    NOVA_OS_MODE_SIGNAL,
)
from ibkr import client as _ibkr_client
from ibkr import orders as _orders
from journal.store import record_trade
from nova_os import control_mode as _control_mode
from nova_os import staged_tickets as _staged
from nova_os.events import KIND_ACTION, KIND_SYSTEM, record_receipt
from strategy import executor_cancel as _cancel
from strategy import executor_flatten as _executor_flatten
from strategy import executor_place as _executor_place
from strategy import kill_switch_state as _kill_state
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


# None = not hydrated from disk yet. Read through is_kill_switch_tripped()
# so a restart restores a tripped latch (strategy/kill_switch_state.py).
_kill_switch_tripped: bool | None = None
_open_positions: dict[str, OpenPosition] = {}

_MODE_DISCLOSURE = (
    "Control mode starts at signal on every restart and is never persisted. "
    "P5 allows signal (display), confirm (stage → Approve), and auto_paper "
    "(paper Gateway + orders enabled + risk clear + not holiday — places without "
    "Approve). auto_live stays blocked. Kill forces signal, rejects staged, blocks "
    "every new place (including manual tickets and hotkeys) until reset, survives "
    "an API restart, and cancels working orders — protective stops on already "
    "filled positions are preserved. Flatten requires typing FLATTEN."
)


def open_positions() -> dict[str, OpenPosition]:
    return _open_positions


def restore_tracked_position(pos: OpenPosition) -> None:
    """Startup recovery / tests — register a tracked position without placing."""
    _open_positions[pos.symbol.upper()] = pos


def is_armed() -> bool:
    """Legacy: True when mode is not signal and kill is clear (confirm stages)."""
    return (
        not is_kill_switch_tripped()
        and _control_mode.get_mode() != NOVA_OS_MODE_SIGNAL
    )


def is_kill_switch_tripped() -> bool:
    """Sole read of the latch — hydrates from disk once per process."""
    global _kill_switch_tripped
    if _kill_switch_tripped is None:
        _kill_switch_tripped = bool(_kill_state.load()["tripped"])
        if _kill_switch_tripped:
            logger.warning(
                "KILL SWITCH restored from disk — Nova will refuse every place "
                "until reset_kill_switch()"
            )
    return _kill_switch_tripped


def status() -> dict:
    from sim.mode import desk_mode_label, venue as _desk_venue

    effective, loss_reason = _control_mode.get_effective_mode_detail()
    _staged.expire_due()
    return {
        "disclosure": _MODE_DISCLOSURE,
        "armed": is_armed(),
        "control_mode": _control_mode.get_mode(),
        "effective_mode": effective,
        "loss_policy_reason": loss_reason,
        "kill_switch_tripped": is_kill_switch_tripped(),
        "ibkr_connected": _ibkr_client.is_connected(),
        # ADR 020: the desk venue on Paper / Sim (Auto Paper keys on "paper"),
        # IBKR's port label on Live.
        "ibkr_mode": desk_mode_label(),
        "venue": _desk_venue(),
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


def kill_switch() -> dict:
    """Kill all Nova spend: latch, force signal, reject staged, cancel working.

    The latch is set (and persisted) FIRST so no place can race in between the
    cancels — `execution.service.execute` refuses every non-protective place
    while it is set.
    """
    global _kill_switch_tripped
    _kill_switch_tripped = True
    _kill_state.save(tripped=True, reason="kill_switch")
    _control_mode.force_signal("kill_switch")
    rejected = _staged.reject_all("kill_switch")
    cancelled: list[int] = []
    preserved: list[str] = []
    unknown: list[str] = []
    preserve_ids: set[int] = set()
    for symbol, pos in list(_open_positions.items()):
        ids, outcome = _cancel.cancel_bracket_if_parent_unfilled(pos)
        cancelled.extend(ids)
        if outcome == "preserved_protective":
            preserved.append(symbol)
            preserve_ids.update({pos.target_order_id, pos.stop_order_id})
        elif outcome == "unknown_state":
            unknown.append(symbol)
            preserve_ids.update({pos.target_order_id, pos.stop_order_id})
    swept, sweep_failed = _cancel.cancel_remaining_open_orders(
        preserve_ids=preserve_ids, already_cancelled=set(cancelled),
    )
    cancelled.extend(swept)
    record_receipt(
        kind=KIND_SYSTEM,
        mode=NOVA_OS_MODE_SIGNAL,
        payload={
            "event": "kill_switch",
            "cancelled_order_ids": cancelled,
            "swept_order_ids": swept,
            "failed_cancel_order_ids": sweep_failed,
            "preserved_symbols": preserved,
            "unknown_symbols": unknown,
            "rejected_staged": len(rejected),
            "blocks_manual_places": True,
            "persisted": True,
        },
    )
    logger.warning(
        "KILL SWITCH — cancelled=%s swept=%s failed=%s preserved=%s unknown=%s "
        "staged_rejected=%s (manual + hotkey places blocked until reset)",
        cancelled, swept, sweep_failed, preserved, unknown, len(rejected),
    )
    return status()


def reset_kill_switch() -> dict:
    """Sole invalidation trigger for the persisted latch."""
    global _kill_switch_tripped
    _kill_switch_tripped = False
    _kill_state.save(tripped=False, reason="reset_kill_switch")
    return status()


def cancel_working_entry(symbol: str) -> dict:
    """Cancel one symbol's unfilled parent (+ children). Preserve filled stops."""
    symbol = symbol.upper()
    pos = _open_positions.get(symbol)
    if pos is None:
        return {"ok": False, "error": f"no tracked position for {symbol}", **status()}
    ids, outcome = _cancel.cancel_bracket_if_parent_unfilled(pos)
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
        trade_id = record_trade(
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
            close_key=f"{pos.symbol}|bracket|{pos.parent_order_id}",
        )
        if trade_id:
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
