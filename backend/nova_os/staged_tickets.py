"""
Nova OS staged-ticket queue (Phase P4 confirm mode).

When control mode is `confirm`, BUY signals stage an expiring ticket instead of
placing an order. A human must Approve before `NOVA_OS_CONFIRM_TIMEOUT_SEC` or
the ticket expires. Never persists across restart.
"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import asdict, dataclass

from constants import (
    NOVA_OS_ACTION_CONFIRMED,
    NOVA_OS_ACTION_DECLINED,
    NOVA_OS_ACTION_STAGED,
    NOVA_OS_CONFIRM_TIMEOUT_SEC,
    NOVA_OS_MAX_CONCURRENT_POSITIONS,
    NOVA_OS_MODE_CONFIRM,
)
from nova_os.events import KIND_ACTION, record_receipt

logger = logging.getLogger(__name__)


@dataclass
class StagedTicket:
    id: str
    symbol: str
    setup: str
    entry: float
    stop: float
    target: float
    shares: int
    decision_receipt_id: int | None
    expires_at: float
    created_at: float
    mode: str = NOVA_OS_MODE_CONFIRM
    status: str = "staged"  # staged | approved | rejected | expired

    def to_dict(self) -> dict:
        d = asdict(self)
        d["seconds_remaining"] = max(0.0, self.expires_at - time.time())
        return d


_staged: dict[str, StagedTicket] = {}


def _open_position_count() -> int:
    from strategy import executor as _executor

    return len(_executor.open_positions())


def list_staged() -> list[StagedTicket]:
    return list(_staged.values())


def get_staged(ticket_id: str) -> StagedTicket | None:
    return _staged.get(ticket_id)


def stage_from_signal(
    symbol: str,
    setup: str,
    signal_dict: dict,
    decision_meta: dict | None = None,
) -> StagedTicket | None:
    """Stage a confirm-mode ticket. Returns None if rejected (max concurrent / bad ticket)."""
    expire_due()
    symbol = symbol.upper()
    entry = signal_dict.get("entry_price")
    stop = signal_dict.get("stop_price")
    target = signal_dict.get("target_price")
    if entry is None or stop is None or target is None:
        logger.info("staged_tickets: %s/%s missing entry/stop/target", symbol, setup)
        return None

    meta = decision_meta or {}
    shares = int(meta.get("shares") or signal_dict.get("shares") or 0)
    if shares <= 0:
        from strategy import risk as _risk

        shares = int(_risk.position_size_shares())
    if shares <= 0:
        return None

    concurrent = _open_position_count() + len(_staged)
    if concurrent >= NOVA_OS_MAX_CONCURRENT_POSITIONS:
        logger.warning(
            "staged_tickets: at max concurrent (%s) — refusing %s/%s",
            NOVA_OS_MAX_CONCURRENT_POSITIONS,
            symbol,
            setup,
        )
        record_receipt(
            kind=KIND_ACTION,
            symbol=symbol,
            action=NOVA_OS_ACTION_DECLINED,
            mode=NOVA_OS_MODE_CONFIRM,
            would_execute=False,
            executed=False,
            payload={
                "event": "stage_rejected_max_concurrent",
                "setup": setup,
                "open_positions": _open_position_count(),
                "staged": len(_staged),
            },
        )
        return None

    now = time.time()
    ticket = StagedTicket(
        id=str(uuid.uuid4()),
        symbol=symbol,
        setup=setup,
        entry=float(entry),
        stop=float(stop),
        target=float(target),
        shares=shares,
        decision_receipt_id=meta.get("receipt_id") or meta.get("decision_receipt_id"),
        expires_at=now + NOVA_OS_CONFIRM_TIMEOUT_SEC,
        created_at=now,
        mode=NOVA_OS_MODE_CONFIRM,
    )
    _staged[ticket.id] = ticket
    receipt = record_receipt(
        kind=KIND_ACTION,
        symbol=symbol,
        action=NOVA_OS_ACTION_STAGED,
        mode=NOVA_OS_MODE_CONFIRM,
        would_execute=True,
        executed=False,
        payload={"event": "staged", "ticket": ticket.to_dict()},
    )
    logger.warning(
        "staged_tickets: staged %s/%s id=%s expires_in=%ss (receipt=%s)",
        symbol,
        setup,
        ticket.id,
        NOVA_OS_CONFIRM_TIMEOUT_SEC,
        receipt.get("id"),
    )
    return ticket


def reject(ticket_id: str, reason: str = "rejected") -> dict | None:
    ticket = _staged.pop(ticket_id, None)
    if ticket is None:
        return None
    ticket.status = "rejected"
    receipt = record_receipt(
        kind=KIND_ACTION,
        symbol=ticket.symbol,
        action=NOVA_OS_ACTION_DECLINED,
        mode=ticket.mode,
        would_execute=False,
        executed=False,
        payload={"event": "staged_rejected", "ticket_id": ticket_id, "reason": reason},
    )
    return {"ticket": ticket.to_dict(), "receipt": receipt}


def reject_all(reason: str) -> list[dict]:
    results = []
    for ticket_id in list(_staged.keys()):
        out = reject(ticket_id, reason=reason)
        if out is not None:
            results.append(out)
    return results


def approve(ticket_id: str) -> dict:
    """Approve a staged ticket and place via executor.place_from_ticket.

    Raises ValueError if missing/expired. Returns placement result + receipt.
    """
    expire_due()
    ticket = _staged.get(ticket_id)
    if ticket is None:
        raise ValueError(f"staged ticket not found: {ticket_id}")
    if time.time() >= ticket.expires_at:
        expire_due()
        raise ValueError(f"staged ticket expired: {ticket_id}")

    del _staged[ticket_id]
    ticket.status = "approved"
    receipt = record_receipt(
        kind=KIND_ACTION,
        symbol=ticket.symbol,
        action=NOVA_OS_ACTION_CONFIRMED,
        mode=ticket.mode,
        would_execute=True,
        executed=False,
        payload={"event": "staged_approved", "ticket_id": ticket_id, "ticket": ticket.to_dict()},
    )

    from strategy import executor as _executor

    placed = _executor.place_from_ticket(
        ticket.symbol,
        ticket.setup,
        ticket.entry,
        ticket.stop,
        ticket.target,
        shares=ticket.shares,
    )
    return {
        "ticket": ticket.to_dict(),
        "receipt": receipt,
        "placed": placed,
        "ok": placed is not None,
    }


def expire_due() -> list[dict]:
    """Mark and remove expired tickets; journal each expiry."""
    now = time.time()
    expired: list[dict] = []
    for ticket_id, ticket in list(_staged.items()):
        if now < ticket.expires_at:
            continue
        del _staged[ticket_id]
        ticket.status = "expired"
        receipt = record_receipt(
            kind=KIND_ACTION,
            symbol=ticket.symbol,
            action=NOVA_OS_ACTION_DECLINED,
            mode=ticket.mode,
            would_execute=False,
            executed=False,
            payload={"event": "staged_expired", "ticket_id": ticket_id, "ticket": ticket.to_dict()},
        )
        expired.append({"ticket": ticket.to_dict(), "receipt": receipt})
        logger.info("staged_tickets: expired %s id=%s", ticket.symbol, ticket_id)
    return expired


def reset_for_tests() -> None:
    _staged.clear()
