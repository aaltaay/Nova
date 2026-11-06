"""Whole-account flatten through the existing execution door.

Desk HTTP: POST /api/ibkr/flatten-account (Emergency KILL + tests).
Cancel leftover working first, then place closes -- never cancel after place.
Weekday RTH closes are MKT. After hours / weekend uses an EH LMT so IBKR
cannot hold the exit until the next regular session.

One venue, read once (#1281): every cancel and close names it (``expected_venue``), the retry stays on it, and at the
first sign the desk left it the flatten stops -- nothing more is sent, nothing reaches the venue the desk moved to, and
the answer says what is still open there (the operator's decision, 2026-11-04: stop and say so, never finish there).

Every close carries its caller's ``origin`` (``emergency_kill``, or ``bot`` for the bot's own
last-resort exit), so the Orders table says who sold. The daily loss limit's Auto sell closes only
what was opened today, on its own (``loss_limit.sell``, ADR 056).
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from constants_bot import BOT_FLATTEN_RETRIES

logger = logging.getLogger(__name__)


async def _place_close(symbol: str, qty: float, side: str, *, origin: str | None = None,
                       expected_venue: str | None = None) -> dict[str, Any]:
    """``expected_venue``: the venue the close is meant for; the door refuses it on any other (ADR 069)."""
    from execution.flatten_exit import (
        plan_flatten_exit,
        plan_practice_flatten_exit,
        resolve_flatten_marks,
        ticket_to_command_fields,
    )
    from execution import venue_door
    from execution.models import ExecutionCommand
    from execution.service import execute

    if venue_door.is_practice(expected_venue):
        # The practice broker closes a held position at the last mark at any
        # hour, feed or no feed (ADR 018 / 019) -- no EH sweep, no mark needed.
        ticket = plan_practice_flatten_exit()
    else:
        bid, ask, last = resolve_flatten_marks(symbol)
        ticket = plan_flatten_exit(side, bid=bid, ask=ask, last=last)
    if not ticket.ok:
        return {"ok": False, "error": ticket.error, "reason_code": "FLATTEN_EH_NO_MARK"}

    receipt = await execute(
        ExecutionCommand(
            operation="place",
            idempotency_key=f"bot:flatten:{side.lower()}:{symbol}:{uuid.uuid4()}",
            source="flatten",
            symbol=symbol,
            side=side,
            qty=abs(float(qty)),
            skip_risk=True,
            origin=origin,  # type: ignore[arg-type]
            expected_venue=expected_venue,
            **ticket_to_command_fields(ticket),
        ),
        wait_ack=False,
    )
    out = receipt.legacy_place_dict()
    # What the broker was actually sent, so the caller can prove a whole close.
    out["sent_qty"] = _sent_qty(receipt)
    return out


def _sent_qty(receipt: Any) -> float | None:
    """The size execute() sent for this receipt, from its record (QA R33).

    A receipt's own payload does not carry ``sent_qty``; the execution record
    does (``execution.record_payload``). Unknown stays None -- never a guess.
    """
    payload = getattr(receipt, "payload", None) or {}
    sent = payload.get("sent_qty")
    execution_id = getattr(receipt, "execution_id", None)
    if sent is None and execution_id:
        try:
            from execution import store

            row = store.get_by_id(str(execution_id)) or {}
            sent = (row.get("payload") or {}).get("sent_qty")
        except Exception:
            logger.exception("bot flatten: execution record unreadable for %s", execution_id)
            return None
    try:
        return float(sent) if sent is not None else None
    except (TypeError, ValueError):
        return None


async def _cancel_working(*, symbol: str | None = None, owner: str | None = None, origin: str | None = None,
                          expected_venue: str | None = None) -> list[dict[str, Any]]:
    """Every working order, or only one stock's (``symbol``) and one book's (a row's ``owner``, ADR 069).

    ``expected_venue``: the venue these order ids belong to; the door refuses a cancel on any other, where the same
    number is another order (``execution.venue_door``). The first such refusal ends the run: the door would refuse the
    rest too.
    """
    from execution.models import ExecutionCommand
    from execution.service import execute
    from ibkr import orders as _orders

    results: list[dict[str, Any]] = []
    try:
        open_rows = _orders.open_orders()
    except Exception as exc:
        logger.exception("bot flatten: open_orders failed")
        return [{"ok": False, "error": str(exc)}]
    for row in open_rows:
        order_id = row.get("order_id")
        if order_id is None:
            continue
        if symbol is not None and str(row.get("symbol") or "").strip().upper() != symbol:
            continue
        if owner is not None and row.get("owner") != owner:
            continue
        receipt = await execute(
            ExecutionCommand(
                operation="cancel",
                idempotency_key=f"bot:flatten:cancel:{order_id}:{uuid.uuid4()}",
                source="cancel_working",
                order_id=int(order_id),
                skip_risk=True,
                origin=origin,  # type: ignore[arg-type]
                expected_venue=expected_venue,
            ),
            wait_ack=False,
        )
        results.append(receipt.legacy_place_dict())
        if _refused_as_moved(results[-1]):
            break
    return results


def _refused_as_moved(answer: dict[str, Any]) -> bool:
    """The door refused this send because the desk is not on the venue it named."""
    from execution import venue_door

    return answer.get("reason_code") == venue_door.VENUE_CHANGED


def _short_close(close: dict[str, Any], qty: float) -> str | None:
    """Why a close did not cover the position, or None when it did (QA R6)."""
    if not close.get("ok"):
        return None  # already a failure; its own error says why
    sent = close.get("sent_qty")
    try:
        sent_f = float(sent) if sent is not None else None
    except (TypeError, ValueError):
        sent_f = None
    if sent_f is not None and sent_f + 1e-9 < abs(qty):
        return f"flatten sent {sent_f:g} of {abs(qty):g} shares"
    return None


def _position_closes(positions: list[dict[str, Any]]) -> list[tuple[str, float, str]]:
    closes: list[tuple[str, float, str]] = []
    for row in positions:
        symbol = str(row.get("symbol") or "").strip().upper()
        try:
            qty = float(row.get("qty") or 0)
        except (TypeError, ValueError):
            continue
        if not symbol or abs(qty) < 1e-9:
            continue
        side = "SELL" if qty > 0 else "BUY"
        closes.append((symbol, abs(qty), side))
    return closes


async def flatten_account_once(*, origin: str | None = None, venue: str | None = None) -> dict[str, Any]:
    """One pass on ``venue``, or on the desk's now.

    Its reads are the desk's, so each is taken while the desk is there.
    """
    from execution import venue_door
    from ibkr import account as _account
    from ibkr.errors import IbkrAccountError

    from sim.mode import desk_connected

    on = venue or venue_door.current()
    if venue_door.current() != on:
        return _stopped(on)
    # A practice account is a local ledger whose broker closes a held position
    # at the last mark with the Gateway dark (ADR 018 / 019) -- the same
    # exemption execution.validate.check_account_and_position gives it.
    if not venue_door.is_practice(on) and not desk_connected():
        return {"ok": False, "error": "IBKR not connected -- cannot flatten", "results": []}
    try:
        positions = _account.get_positions()
    except IbkrAccountError as exc:
        return {"ok": False, "error": str(exc), "results": []}

    # Cancel leftover working first. Never cancel after place -- openTrades
    # can include the unfilled liquidation MKTs (wait_ack=False) and kill them.
    cancels = await _cancel_working(expected_venue=on)
    # Off the venue now, these reads may be the other venue's: a flat list there is no proof of anything here.
    if venue_door.current() != on or any(_refused_as_moved(cancel) for cancel in cancels):
        return _stopped(on, cancels=cancels)
    results: list[dict[str, Any]] = []
    for symbol, qty, side in _position_closes(positions):
        close = await _place_close(symbol, qty, side, origin=origin, expected_venue=on)
        short = _short_close(close, qty)
        if short:
            close = {**close, "ok": False, "error": short, "reason_code": "FLATTEN_PARTIAL"}
            logger.error("bot flatten: %s %s -- %s", side, symbol, short)
        results.append({"symbol": symbol, "qty": qty, "side": side, "close": close})
        if _refused_as_moved(close):
            return _stopped(on, results=results, cancels=cancels)
    ok = all((r.get("close") or {}).get("ok") for r in results) if results else True
    if cancels and not results:
        ok = all(c.get("ok") for c in cancels)
    left = _practice_left_open(positions, on) if ok and results and venue_door.is_practice(on) else []
    if left:
        # The practice broker fills a protective close at placement, so any share
        # still held means the close did not cover it -- never report success.
        ok = False
        logger.error("bot flatten: positions still open after close: %s", left)
    out: dict[str, Any] = {"ok": ok, "results": results, "cancels": cancels}
    if left is None:
        # The re-read failed: the closes were sent, but flat is unproven.
        out["ok"] = False
        out["error"] = "flatten sent, but positions could not be re-read to confirm it"
    elif left:
        out["error"] = "positions still open after flatten: " + ", ".join(left)
        out["left_open"] = left
    return out


def _practice_left_open(before: list[dict[str, Any]], venue: str) -> list[str] | None:
    """``["GRML 1"]`` for symbols the flatten closed that ``venue`` still holds, whatever the desk shows by now;
    None when the positions cannot be re-read (unproven, never "flat")."""
    from kill_switch.sweep import held_positions

    closed = {symbol for symbol, _qty, _side in _position_closes(before)}
    held = held_positions(venue)
    if held is None:
        return None
    return [f"{symbol} {abs(qty):g}" for symbol, qty in held.items() if symbol in closed]


def _stopped(venue: str, *, results: list[dict[str, Any]] | None = None,
             cancels: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """The desk left ``venue``: what the flatten answers. What is still open is read from that venue's own book,
    whatever the desk shows; a book that cannot be read is said, never "flat"."""
    from execution import venue_door
    from kill_switch.sweep import held_positions, read_working

    now = venue_door.current()
    held = held_positions(venue)
    rows = read_working(venue)[0]
    left = None if held is None else [f"{symbol} {qty:g}" for symbol, qty in sorted(held.items())]
    working = None if rows is None else len(rows)
    sent = [row["symbol"] for row in results or [] if (row.get("close") or {}).get("ok")]
    logger.error(
        "bot flatten: the desk moved from %s to %s, stopped; left open %s, %s working",
        venue, now, left, working,
    )
    return {"ok": False, "reason_code": venue_door.VENUE_CHANGED, "venue": venue, "moved_to": now,
            "error": _stopped_text(venue, now, left, working, sent), "results": results or [],
            "cancels": cancels or [], "left_open": left, "working_orders": working}


def _stopped_text(venue: str, now: str, left: list[str] | None, working: int | None, sent: list[str]) -> str:
    name, other = venue.capitalize(), now.capitalize()
    parts = [f"The desk moved from {name} to {other}, so KILL stopped and sent nothing to {other}."]
    if sent:
        parts.append(f"Closes already sent on {name}: {', '.join(sent)}.")
    still_open = list(left or [])
    if working:
        still_open.append(f"{working} working order{'' if working == 1 else 's'}")
    if still_open:
        parts.append(f"Still open on {name}: {', '.join(still_open)}.")
    if left is None or working is None:
        parts.append(f"{name}'s book could not be read in full: check it there.")
    elif not still_open:
        parts.append(f"Nothing is open on {name}.")
    if left:
        parts.append("KILL cancels first, so a position left open may have no stop.")
    return " ".join(parts)


async def flatten_account_with_retry(*, origin: str | None = None, venue: str | None = None) -> dict[str, Any]:
    """``venue``: the one KILL was pressed on, else the desk's now, read once. A pass that read the desk again would
    find the venue it moved to flat and answer ``ok`` with this one's shares still open (#1281)."""
    from execution import venue_door

    on = venue or venue_door.current()
    last: dict[str, Any] = {"ok": False, "error": "flatten not attempted", "results": []}
    attempts = 1 + int(BOT_FLATTEN_RETRIES)
    for attempt in range(attempts):
        last = await flatten_account_once(origin=origin, venue=on)
        last["attempt"] = attempt + 1
        if last.get("ok") or _refused_as_moved(last):
            return last
    return last


# One symbol's protective close, for the first-pullback bot's last resort (ADR 030).
place_close = _place_close
# One stock's working orders in one book, before the Close on a bots' row (ADR 069 decision 9).
cancel_working = _cancel_working
