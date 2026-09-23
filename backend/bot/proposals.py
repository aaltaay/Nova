"""Bot proposals at Eyes or Strategy -- a human places. Fixed schema (ADR 016, ADR 027)."""
from __future__ import annotations

import time
import uuid
from typing import Any

from bot.audit import record as audit
from bot.autonomy import assert_not_dark
from bot.eligibility import assert_symbol_eligible
from bot.errors import BotError
from bot.persist import load_proposals, load_session, save_proposals
from bot.risk import assert_kind


def _validate_proposal(body: dict[str, Any]) -> dict[str, Any]:
    symbol = str(body.get("symbol") or "").strip().upper()
    side = str(body.get("side") or "").strip().upper()
    kind = str(body.get("kind") or body.get("action") or body.get("shortcut") or "").strip()
    if not symbol:
        raise BotError("proposal.symbol is required", 400)
    if side not in ("BUY", "SELL"):
        raise BotError("proposal.side must be BUY or SELL", 400)
    row = load_session()
    assert_symbol_eligible(symbol, row)
    assert_kind(kind, row)
    if body.get("qty") is not None or body.get("shares") is not None:
        raise BotError("proposal qty is the session preset -- do not send shares", 400)
    reason = str(body.get("reason") or "").strip()
    if not reason:
        raise BotError("proposal.reason is required", 400)
    confidence = body.get("confidence")
    if confidence is not None:
        confidence = float(confidence)
        if confidence < 0 or confidence > 1:
            raise BotError("proposal.confidence must be 0..1", 400)
    preset_qty = int((row.get("caps") or {}).get("max_shares") or 1)
    return {
        "id": str(uuid.uuid4()),
        "symbol": symbol,
        "side": side,
        "kind": kind,
        "action": kind,
        "shortcut": kind,
        "preset_qty": preset_qty,
        "reason": reason[:280],
        "confidence": confidence,
        "status": "pending",
        "created_ts": time.time(),
    }


def list_proposals() -> list[dict[str, Any]]:
    row = load_session()
    if int(row.get("level") or 0) <= 0:
        return []
    return list(load_proposals().get("items") or [])


def submit(body: dict[str, Any], *, brain_session_id: str | None) -> dict[str, Any]:
    # Eyes or Strategy: until Strategy's read-out passes the bot proposes like Eyes (ADR 027).
    assert_not_dark()
    item = _validate_proposal(body)
    item["brain_session_id"] = (brain_session_id or "").strip() or None
    store = load_proposals()
    items = list(store.get("items") or [])
    items.append(item)
    save_proposals({"items": items})
    audit(action="proposal", outcome="pending", reason=item["reason"], inputs=item, brain_session_id=brain_session_id)
    return item


def _set_status(proposal_id: str, status: str) -> dict[str, Any]:
    store = load_proposals()
    items = list(store.get("items") or [])
    found = None
    next_items: list[dict[str, Any]] = []
    for item in items:
        if item.get("id") == proposal_id:
            found = dict(item)
            found["status"] = status
            found["resolved_ts"] = time.time()
            next_items.append(found)
        else:
            next_items.append(item)
    if found is None:
        raise BotError("proposal not found", 404)
    save_proposals({"items": next_items})
    audit(action="proposal", outcome=status, inputs={"id": proposal_id})
    return found


def accept(proposal_id: str) -> dict[str, Any]:
    """Desk accept -- does not place. Human still uses the ticket / hotkey."""
    return _set_status(proposal_id, "accepted")


def reject(proposal_id: str) -> dict[str, Any]:
    return _set_status(proposal_id, "rejected")
