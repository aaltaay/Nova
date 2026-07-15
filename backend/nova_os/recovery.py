"""
Nova OS restart recovery (Phase P5).

On API startup: reconstruct executor `_open_positions` best-effort from the
event journal (`executed_paper`) and optionally IBKR open orders. Control mode
always remains `signal` after restart — this module never restores auto_paper.

Ambiguous / unknown state → force_signal + loud log + system receipt.
"""
from __future__ import annotations

import logging
import time

from constants import (
    NOVA_OS_ACTION_EXECUTED_PAPER,
    NOVA_OS_MODE_SIGNAL,
    NOVA_OS_RECOVERY_EVENTS_LIMIT,
)
from ibkr import client as _ibkr_client
from ibkr import orders as _orders
from nova_os import control_mode as _control_mode
from nova_os.events import KIND_SYSTEM, get_events, record_receipt
from strategy import executor as _executor

logger = logging.getLogger(__name__)

# Payload events that clear a tracked symbol after executed_paper.
_CLOSE_EVENTS = frozenset({
    "flatten",
    "cancel_working_entry",
    "kill_switch",
    "bracket_closed",
    "bracket_closed_unverified",
})


def _payload_event(ev: dict) -> str:
    payload = ev.get("payload") or {}
    return str(payload.get("event") or "")


def _order_ids_from_payload(payload: dict) -> set[int]:
    ids: set[int] = set()
    for key in ("parent_order_id", "target_order_id", "stop_order_id"):
        raw = payload.get(key)
        if raw is None:
            continue
        try:
            ids.add(int(raw))
        except (TypeError, ValueError):
            continue
    return ids


def _latest_executed_paper_by_symbol(events: list[dict]) -> dict[str, dict]:
    """Newest-first events → one executed_paper row per symbol."""
    found: dict[str, dict] = {}
    for ev in events:
        if ev.get("action") != NOVA_OS_ACTION_EXECUTED_PAPER:
            continue
        if not ev.get("executed"):
            continue
        symbol = (ev.get("symbol") or "").upper()
        if not symbol or symbol in found:
            continue
        found[symbol] = ev
    return found


def _symbol_closed_after(events: list[dict], symbol: str, after_ts: float) -> bool:
    for ev in events:
        if (ev.get("symbol") or "").upper() != symbol:
            continue
        if float(ev.get("ts") or 0) <= after_ts:
            continue
        if _payload_event(ev) in _CLOSE_EVENTS:
            return True
        # kill_switch / flatten may be system-kind without per-symbol.
    for ev in events:
        if float(ev.get("ts") or 0) <= after_ts:
            continue
        event_name = _payload_event(ev)
        if event_name == "kill_switch":
            return True
        if event_name == "flatten":
            results = (ev.get("payload") or {}).get("results") or []
            if any((r.get("symbol") or "").upper() == symbol for r in results):
                return True
    return False


def _try_build_position(ev: dict) -> _executor.OpenPosition | None:
    payload = ev.get("payload") or {}
    symbol = (ev.get("symbol") or payload.get("symbol") or "").upper()
    try:
        parent = int(payload["parent_order_id"])
        target = int(payload["target_order_id"])
        stop = int(payload["stop_order_id"])
        qty = int(payload.get("qty") or 0)
        entry = float(payload["entry_price"])
        stop_px = float(payload["stop_price"])
        target_px = float(payload["target_price"])
    except (KeyError, TypeError, ValueError):
        return None
    if not symbol or qty <= 0:
        return None
    return _executor.OpenPosition(
        symbol=symbol,
        setup=str(payload.get("setup") or "unknown"),
        qty=qty,
        entry_price=entry,
        stop_price=stop_px,
        target_price=target_px,
        parent_order_id=parent,
        target_order_id=target,
        stop_order_id=stop,
        opened_ts=float(payload.get("opened_ts") or ev.get("ts") or time.time()),
    )


def run_startup_recovery() -> dict:
    """Best-effort reconstruct tracked positions; never restore auto_paper mode.

    Returns a summary dict for tests / logs. Mode stays at signal (default);
    on ambiguity calls force_signal and journals a system receipt.
    """
    # Explicit: do not restore auto_paper across restart.
    if _control_mode.get_mode() != NOVA_OS_MODE_SIGNAL:
        _control_mode.force_signal("startup_recovery_mode_reset")

    events = get_events(limit=NOVA_OS_RECOVERY_EVENTS_LIMIT)
    executed = _latest_executed_paper_by_symbol(events)

    open_ids: set[int] = set()
    ibkr_checked = False
    if _ibkr_client.is_connected():
        try:
            open_ids = {int(o["order_id"]) for o in _orders.open_orders() if "order_id" in o}
            ibkr_checked = True
        except Exception:
            logger.exception("Nova OS recovery: open_orders failed")
            ibkr_checked = False

    ambiguous: list[str] = []
    restored: list[str] = []

    for symbol, ev in executed.items():
        if _symbol_closed_after(events, symbol, float(ev.get("ts") or 0)):
            continue
        payload = ev.get("payload") or {}
        ids = _order_ids_from_payload(payload)
        if len(ids) < 3:
            ambiguous.append(f"{symbol}: executed_paper missing order ids")
            continue
        pos = _try_build_position(ev)
        if pos is None:
            ambiguous.append(f"{symbol}: executed_paper payload incomplete")
            continue
        if ibkr_checked:
            if not (ids & open_ids):
                # Legs gone — treat as already flat; do not restore.
                continue
            _executor.restore_tracked_position(pos)
            restored.append(symbol)
        else:
            # No IBKR proof either way — restoring into _open_positions here
            # would let cancel/flatten act on a position we never verified
            # exists, and would let the fill-poll loop silently "close" a
            # ghost and journal a fabricated pnl. Report it and force signal;
            # the operator must check IBKR/TWS directly before trusting it.
            ambiguous.append(
                f"{symbol}: cannot verify without IBKR — NOT restored; check IBKR/TWS manually"
            )

    if ibkr_checked:
        tracked_ids = set()
        for pos in _executor.open_positions().values():
            tracked_ids.update(
                {pos.parent_order_id, pos.target_order_id, pos.stop_order_id}
            )
        orphan = open_ids - tracked_ids
        # Loud whenever IBKR has open orders we cannot attribute to a
        # restored position — regardless of whether OTHER symbols restored
        # cleanly. A clean restore for TSLA must never hide an orphan order
        # in NVDA that recovery couldn't explain.
        if orphan:
            ambiguous.append(
                f"IBKR open order ids not matched to journal: {sorted(orphan)[:12]}"
            )

    summary = {
        "restored_symbols": restored,
        "ambiguous": ambiguous,
        "ibkr_checked": ibkr_checked,
        "mode": _control_mode.get_mode(),
    }

    if ambiguous:
        logger.error(
            "NOVA OS RECOVERY AMBIGUOUS — forcing signal. restored=%s reasons=%s",
            restored,
            ambiguous,
        )
        _control_mode.force_signal("startup_recovery_ambiguous")
        record_receipt(
            kind=KIND_SYSTEM,
            mode=NOVA_OS_MODE_SIGNAL,
            payload={
                "event": "startup_recovery",
                "status": "ambiguous",
                "restored_symbols": restored,
                "reasons": ambiguous,
                "ibkr_checked": ibkr_checked,
            },
        )
    else:
        logger.warning(
            "Nova OS recovery: restored=%s ibkr_checked=%s (mode stays signal)",
            restored,
            ibkr_checked,
        )
        record_receipt(
            kind=KIND_SYSTEM,
            mode=NOVA_OS_MODE_SIGNAL,
            payload={
                "event": "startup_recovery",
                "status": "ok",
                "restored_symbols": restored,
                "ibkr_checked": ibkr_checked,
            },
        )

    return summary
