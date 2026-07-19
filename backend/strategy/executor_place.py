"""Bracket placement via centralized execution (extracted from executor.py)."""
from __future__ import annotations

import asyncio
import logging
import time
import uuid

from constants import (
    EXECUTOR_ENTRY_SIDE_IBKR,
    NOVA_OS_ACTION_DECLINED,
    NOVA_OS_ACTION_EXECUTED_PAPER,
    NOVA_OS_MODE_AUTO_PAPER,
    NOVA_OS_MODE_CONFIRM,
    NOVA_OS_MODE_SIGNAL,
)
from nova_os import control_mode as _control_mode
from nova_os import staged_tickets as _staged
from nova_os.events import KIND_ACTION, record_receipt
from strategy import risk as _risk

logger = logging.getLogger(__name__)


def _decline(symbol: str, setup: str, reason_code: str, detail: str) -> None:
    logger.info("Executor: %s/%s declined — %s: %s", symbol, setup, reason_code, detail)
    record_receipt(
        kind=KIND_ACTION,
        symbol=symbol,
        action=NOVA_OS_ACTION_DECLINED,
        mode=_control_mode.get_mode(),
        would_execute=False,
        executed=False,
        payload={
            "event": "placement_declined",
            "setup": setup,
            "reason_code": reason_code,
            "detail": detail,
        },
    )


def place_from_ticket(
    symbol: str,
    setup: str,
    entry: float,
    stop: float,
    target: float,
    shares: int | None = None,
    *,
    source: str = "approve",
    idempotency_key: str | None = None,
) -> dict | None:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(
            place_from_ticket_async(
                symbol, setup, entry, stop, target, shares,
                source=source, idempotency_key=idempotency_key,
            )
        )
    raise RuntimeError(
        "place_from_ticket() called from a running event loop — "
        "await place_from_ticket_async() instead"
    )


async def place_from_ticket_async(
    symbol: str,
    setup: str,
    entry: float,
    stop: float,
    target: float,
    shares: int | None = None,
    *,
    source: str = "approve",
    idempotency_key: str | None = None,
) -> dict | None:
    from execution.models import ExecutionCommand
    from execution.service import execute
    from strategy.executor import OpenPosition, _open_positions

    symbol = symbol.upper()
    qty = int(shares) if shares and shares > 0 else _risk.position_size_shares()
    key = idempotency_key or f"bracket:{source}:{symbol}:{setup}:{uuid.uuid4()}"
    src = "auto_paper" if source == "auto_paper" else "approve"
    receipt = await execute(
        ExecutionCommand(
            operation="bracket",
            idempotency_key=key,
            source=src,  # type: ignore[arg-type]
            symbol=symbol,
            side=EXECUTOR_ENTRY_SIDE_IBKR,
            entry_price=entry,
            stop_price=stop,
            target_price=target,
            shares=qty,
            setup=setup,
        ),
        wait_ack=False,
    )
    if not receipt.ok:
        _decline(
            symbol, setup,
            receipt.reason_code or "BRACKET_REJECTED",
            str(receipt.error or "execution failed"),
        )
        return None

    pos = OpenPosition(
        symbol=symbol,
        setup=setup,
        qty=qty,
        entry_price=entry,
        stop_price=stop,
        target_price=target,
        parent_order_id=int(receipt.parent_order_id or 0),
        target_order_id=int(receipt.target_order_id or 0),
        stop_order_id=int(receipt.stop_order_id or 0),
        opened_ts=time.time(),
    )
    _open_positions[symbol] = pos
    record_receipt(
        kind=KIND_ACTION,
        symbol=symbol,
        action=NOVA_OS_ACTION_EXECUTED_PAPER,
        mode=_control_mode.get_mode(),
        would_execute=True,
        executed=True,
        payload={
            "event": "executed_paper",
            "setup": setup,
            "qty": qty,
            "entry_price": entry,
            "stop_price": stop,
            "target_price": target,
            "parent_order_id": pos.parent_order_id,
            "target_order_id": pos.target_order_id,
            "stop_order_id": pos.stop_order_id,
            "opened_ts": pos.opened_ts,
            "execution_id": receipt.execution_id,
            "timings": receipt.timings.to_dict() if receipt.timings else None,
        },
    )
    logger.warning(
        "Executor: placed bracket %s/%s qty=%s entry=%s stop=%s target=%s (parent=%s exec=%s)",
        symbol, setup, qty, entry, stop, target, pos.parent_order_id, receipt.execution_id,
    )
    return {
        "symbol": pos.symbol,
        "setup": pos.setup,
        "qty": pos.qty,
        "entry_price": pos.entry_price,
        "stop_price": pos.stop_price,
        "target_price": pos.target_price,
        "opened_ts": pos.opened_ts,
        "execution_id": receipt.execution_id,
    }


async def on_signal(symbol: str, setup_name: str, signal_dict: dict) -> dict | None:
    from strategy.executor import _kill_switch_tripped

    _staged.expire_due()
    if _kill_switch_tripped:
        return None

    effective = _control_mode.get_effective_mode()
    if effective == NOVA_OS_MODE_SIGNAL:
        return None

    if effective == NOVA_OS_MODE_CONFIRM:
        meta = signal_dict.get("nova_os") if isinstance(signal_dict.get("nova_os"), dict) else {}
        ticket = _staged.stage_from_signal(symbol, setup_name, signal_dict, decision_meta=meta)
        return ticket.to_dict() if ticket else None

    if effective == NOVA_OS_MODE_AUTO_PAPER:
        entry = signal_dict.get("entry_price")
        stop = signal_dict.get("stop_price")
        target = signal_dict.get("target_price")
        if entry is None or stop is None or target is None:
            return None
        meta = signal_dict.get("nova_os") if isinstance(signal_dict.get("nova_os"), dict) else {}
        receipt_id = meta.get("receipt_id") or meta.get("decision_receipt_id")
        key = f"auto_paper:{symbol}:{setup_name}:{receipt_id}" if receipt_id else None
        return await place_from_ticket_async(
            symbol, setup_name, entry, stop, target,
            source="auto_paper", idempotency_key=key,
        )

    return None
