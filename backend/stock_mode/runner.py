"""What Nova does for a stock on its switch (ADR 037): hear the setup scanner's triggers, send, and
manage what it sent.

Every ``STOCK_MODE_POLL_SEC``:

1. **The venue.** A venue change clears every switch and approval (``store.sync_venue``).
2. **Triggers** the scanner announced (``submit``, live feed only) on a stock whose switch is
   Auto-entry or Approve: Auto-entry buys the first go trigger at the setup's entry; Approve sends
   the approved plan as one bracket at its setup's go trigger. Anything that keeps Nova from sending
   is a skip with the reason, on the bot's audit stream and in the stock's view.
3. **Approvals** waiting on a trigger are held against their lane: a re-arm at other levels, a failed
   or disarmed setup withdraws them.
4. **Trades** Nova sent are managed: the entry fills, or is cancelled after
   ``STOCK_MODE_ENTRY_TTL_SEC`` (a miss); Approve's exits rest at the broker until one fills; an
   Auto-entry position is the operator's, and Nova only notices when it is closed.

Owner: the trades and approvals in ``stock_mode.store`` (in memory). The bot's own trade on a Nova /
Nova stock is the first-pullback bot's (``bot.first_pullback.runner``).

maintainer: one-concern the stock-mode trade state machine and the loop that drives it
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from datetime import datetime
from typing import Any, Callable
from zoneinfo import ZoneInfo

from bot.audit import record as audit
from constants_bot import BOT_FP_TRIGGER_MAX_AGE_SEC
from constants_setups import SETUP_STATE_ARMED, SETUP_STATE_NEAR, TAPE_VERDICT_GO
from constants_stock_mode import (
    STOCK_MODE_APPROVAL_CHECK_SEC,
    STOCK_MODE_APPROVE,
    STOCK_MODE_AUDIT_ACTION,
    STOCK_MODE_AUTO_ENTRY,
    STOCK_MODE_BLOCK_ENTRY_USED,
    STOCK_MODE_BLOCK_SIZE,
    STOCK_MODE_BLOCK_STALE,
    STOCK_MODE_BLOCK_TAPE,
    STOCK_MODE_BLOCK_WORKING,
    STOCK_MODE_CANCEL_RETRY_SEC,
    STOCK_MODE_ENTRY_TTL_SEC,
    STOCK_MODE_POLL_SEC,
    STOCK_MODE_SIDE_NOVA,
    STOCK_MODE_SIDE_YOU,
    STOCK_MODE_TRADE_CLOSED,
    STOCK_MODE_TRADE_ENTERING,
    STOCK_MODE_TRADE_HOLDING,
    STOCK_MODE_TRADE_MISSED,
)
from stock_mode import gates, model, orders, store

logger = logging.getLogger(__name__)
ET = ZoneInfo("America/New_York")
FILTERED = "filtered"
WAITING_STATES = (SETUP_STATE_ARMED, SETUP_STATE_NEAR, FILTERED)
LIVE_TRADE_STATES = (STOCK_MODE_TRADE_ENTERING, STOCK_MODE_TRADE_HOLDING)
_EPS = 1e-9
_inbox: deque[dict[str, Any]] = deque(maxlen=100)
_clock: Callable[[], float] = time.time
_last_approval_check = 0.0
_warned: set[str] = set()


def submit(event: dict[str, Any]) -> None:
    """The setup scanner's trigger listener: enqueue only (it runs on the scanner's tick)."""
    _inbox.append(event)


def venue_day(now: float | None = None) -> str:
    """The venue's day (the bot's clock: the replay playhead on Sim, the wall clock else)."""
    from bot.entry_rules import venue_now

    try:
        return venue_now().date().isoformat()
    except Exception:
        logger.warning("stock mode: the venue's clock could not be read -- the wall clock's day is used", exc_info=True)
        return datetime.fromtimestamp(now or _clock(), ET).date().isoformat()


async def run() -> None:
    """Background task (``app_runtime_tasks``): listen to the setup scanner, tick forever."""
    from setup_scanner.engine import get_engine

    engine = get_engine()
    engine.add_trigger_listener(submit)
    try:
        while True:
            try:
                await tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("stock mode: tick failed")
            await asyncio.sleep(STOCK_MODE_POLL_SEC)
    finally:
        engine.remove_trigger_listener(submit)


async def tick(now: float | None = None) -> None:
    global _last_approval_check
    now = _clock() if now is None else now
    venue, _replay = gates.venue_state()
    if store.sync_venue(venue):
        audit(action=STOCK_MODE_AUDIT_ACTION, outcome="withdrawn", reason=f"the desk moved to {venue}: every "
              "stock is back to Signal only", inputs={"venue": venue})
    while _inbox:
        await _on_trigger(_inbox.popleft(), now)
    if now - _last_approval_check >= STOCK_MODE_APPROVAL_CHECK_SEC:
        _last_approval_check = now
        _check_approvals(now)
    for trade in store.trades():
        if trade.get("state") in LIVE_TRADE_STATES:
            await _manage(trade, now)


# -- a trigger ------------------------------------------------------------------------
async def _on_trigger(event: dict[str, Any], now: float) -> None:
    sym = str(event.get("symbol") or "").strip().upper()
    sw = store.switch(sym)
    if not sym or not sw:
        return
    mode = model.mode_of(sw["buy"], sw["sell"])
    if mode == STOCK_MODE_AUTO_ENTRY:
        await _auto_entry(sym, sw, event, now)
    elif mode == STOCK_MODE_APPROVE:
        approval = store.approval(sym)
        if approval and approval.get("state") == "waiting" and approval.get("setup_id") == event.get("setup_id"):
            await _send_approved(sym, approval, event, now)


def _refusal(event: dict[str, Any], now: float) -> tuple[str, str] | None:
    """What keeps Nova from sending on this trigger: the venue, the desk, a stale trigger, the tape."""
    venue, replay = gates.venue_state()
    blocked = gates.venue_block(venue, replay) or gates.desk_block()
    if blocked:
        return blocked
    age = now - float(event.get("ts") or 0)
    if age > BOT_FP_TRIGGER_MAX_AGE_SEC:
        return STOCK_MODE_BLOCK_STALE, f"the trigger is {age:.0f}s old (at most {BOT_FP_TRIGGER_MAX_AGE_SEC:g}s)"
    tape = event.get("tape") or {}
    verdict = str(tape.get("verdict") or "blind")
    if verdict != TAPE_VERDICT_GO:
        first = (tape.get("reasons") or [""])[0]
        said = "blind: Nova holds no Level 2 line for it" if verdict == "blind" else verdict.upper()
        return STOCK_MODE_BLOCK_TAPE, f"the tape said {said} at the trigger" + (f" ({first})" if first else "")
    return None


async def _auto_entry(sym: str, sw: dict[str, Any], event: dict[str, Any], now: float) -> None:
    venue, _replay = gates.venue_state()
    day = venue_day(now)
    refused = _refusal(event, now)
    current = store.trade(venue, sym)
    if refused is None and store.entries_today(venue, day, sym) >= 1:
        refused = STOCK_MODE_BLOCK_ENTRY_USED, f"Nova's one buy of {sym} today is used"
    if refused is None and current and current.get("state") == STOCK_MODE_TRADE_ENTERING:
        refused = STOCK_MODE_BLOCK_WORKING, "an entry Nova sent is still working"
    setup = event.get("setup") or {}
    qty = model.size(sw.get("risk_usd"), setup.get("entry"), setup.get("stop"))
    if refused is None and qty < 1:
        refused = STOCK_MODE_BLOCK_SIZE, (f"${float(sw.get('risk_usd') or 0):g} risk buys no whole share at a "
                                          f"{_risk_text(setup)} risk")
    if refused is not None:
        _skip(sym, event, now, refused)
        return
    trade = _new_trade(STOCK_MODE_AUTO_ENTRY, sym, event, now, venue=venue, day=day, qty=qty,
                       entry=setup.get("entry"), stop=setup.get("stop"), target=setup.get("target1"),
                       attempt=str(event.get("setup_id")), exits=STOCK_MODE_SIDE_YOU)
    receipt = await orders.place_entry(trade)
    if not receipt.ok or receipt.order_id is None:
        _skip(sym, event, now, (getattr(receipt, "reason_code", None) or "REFUSED", orders.receipt_error(receipt)),
              outcome="refused")
        return
    trade["entry_order_id"] = int(receipt.order_id)
    store.set_trade(trade)
    _say(sym, now, "info", f"Nova is buying {qty:g} {sym} at {float(trade['entry']):.2f} (limit) -- the exit is yours")
    audit(action=STOCK_MODE_AUDIT_ACTION, outcome="sent", order_id=trade["entry_order_id"],
          reason=f"auto-entry: BUY {qty:g} {sym} LMT {float(trade['entry']):.2f} on the {_setup_name(event)} trigger",
          inputs=_summary(trade))


async def _send_approved(sym: str, approval: dict[str, Any], event: dict[str, Any], now: float) -> None:
    refused = _refusal(event, now)
    if refused is not None:
        store.set_approval(sym, {**approval, "state": "withdrawn", "reason": f"not sent: {refused[1]}"})
        _skip(sym, event, now, refused)
        return
    trade = await send_bracket_now(sym, approval, now, setup_type=event.get("setup_type"))
    if trade is None:
        return
    _say(sym, now, "info", f"Sent: buy {float(trade['qty']):g} {sym} at {float(trade['entry']):.2f} with stop "
                           f"{float(trade['stop']):.2f} and target {float(trade['target']):.2f}")


async def send_bracket_now(sym: str, approval: dict[str, Any], now: float, *,
                           setup_type: str | None = None) -> dict[str, Any] | None:
    """Send an approved plan as one bracket; the trade, or None when the door refused (said so)."""
    venue, _replay = gates.venue_state()
    event = {"symbol": sym, "setup_id": approval.get("setup_id"),
             "setup_type": setup_type or approval.get("setup_type")}
    trade = _new_trade(STOCK_MODE_APPROVE, sym, event, now, venue=venue, day=venue_day(now),
                       qty=int(approval["qty"]), entry=approval["entry"], stop=approval["stop"],
                       target=approval["target"], exits=STOCK_MODE_SIDE_NOVA,
                       attempt=f"{approval.get('setup_id')}@{int(float(approval.get('approved_at') or now) * 1000)}")
    receipt = await orders.send_bracket(trade)
    entry_id, target_id, stop_id = orders.leg_ids(receipt)
    if not receipt.ok or entry_id is None:
        why = orders.receipt_error(receipt)
        store.set_approval(sym, {**approval, "state": "withdrawn", "reason": f"the bracket was refused: {why}"})
        _skip(sym, event, now, (getattr(receipt, "reason_code", None) or "REFUSED", why), outcome="refused")
        return None
    trade.update(entry_order_id=entry_id, target_order_id=target_id, stop_order_id=stop_id)
    store.set_trade(trade)
    store.set_approval(sym, {**approval, "state": "sent", "reason": None})
    audit(action=STOCK_MODE_AUDIT_ACTION, outcome="sent", order_id=entry_id,
          reason=(f"approved plan: BUY {float(trade['qty']):g} {sym} LMT {float(trade['entry']):.2f}, target "
                  f"{float(trade['target']):.2f}, stop {float(trade['stop']):.2f} (one bracket)"),
          inputs=_summary(trade))
    return trade


# -- approvals wait on their lane -------------------------------------------------------
def _check_approvals(now: float) -> None:
    for sym, approval in store.approvals().items():
        if approval.get("state") != "waiting":
            continue
        lane = lane_of(sym, approval.get("setup_id"))
        why = None
        if lane is None:
            why = "the setup is gone from the scanner"
        elif lane.get("state") not in WAITING_STATES:
            if lane.get("state") == "triggered":
                at = float((lane.get("setup") or {}).get("triggered_at") or now)
                if now - at <= BOT_FP_TRIGGER_MAX_AGE_SEC + STOCK_MODE_APPROVAL_CHECK_SEC:
                    continue                    # the trigger listener sends (or says why not)
                why = "the setup triggered and nothing was sent: approve now to buy"
            else:
                why = f"the setup is {lane.get('state')}" + (f": {lane.get('reason')}" if lane.get("reason") else "")
        elif not model.plan_matches(approval, lane.get("setup")):
            why = f"the setup re-armed at {model.levels_text(lane.get('setup') or {})}: approve again"
        if why:
            store.set_approval(sym, {**approval, "state": "withdrawn", "reason": why})
            _say(sym, now, "warn", f"Approval withdrawn: {why}")
            audit(action=STOCK_MODE_AUDIT_ACTION, outcome="withdrawn", reason=why,
                  inputs={"symbol": sym, "setup_id": approval.get("setup_id")})


def lane_of(sym: str, setup_id: str | None) -> dict[str, Any] | None:
    """The scanner's lane for this stock and setup id (its state and levels), or None."""
    if not setup_id:
        return None
    try:
        from setup_scanner.engine import get_engine
        from setup_scanner.symbol_view import symbol_view

        lanes = symbol_view(get_engine(), sym).get("setups") or []
    except Exception:
        logger.warning("stock mode: the scanner's lanes for %s could not be read", sym, exc_info=True)
        return None
    return next((lane for lane in lanes if lane.get("setup_id") == setup_id), None)


# -- a trade Nova sent -------------------------------------------------------------------
async def _manage(trade: dict[str, Any], now: float) -> None:
    venue, _replay = gates.venue_state()
    if venue != trade.get("venue"):
        _warn_once(f"venue:{trade['venue']}:{trade['symbol']}", "stock mode: the desk left %s -- %s waits there",
                   trade.get("venue"), trade["symbol"])
        return
    try:
        if trade["state"] == STOCK_MODE_TRADE_ENTERING:
            await _manage_entry(trade, now)
        elif trade["kind"] == STOCK_MODE_APPROVE and trade.get("exits") == STOCK_MODE_SIDE_NOVA:
            _manage_exits(trade, now)
        else:
            _manage_yours(trade, now)
    except orders.ReadError as exc:
        _warn_once(f"read:{trade['symbol']}:{trade['state']}", "stock mode: %s -- %s not managed this tick",
                   exc, trade["symbol"])


async def _manage_entry(trade: dict[str, Any], now: float) -> None:
    row = orders.order_row(trade.get("entry_order_id"))
    state = orders.order_state(row)
    filled = float((row or {}).get("filled_qty") or 0)
    sym = trade["symbol"]
    if state == "filled" or (state in ("dead", "gone") and filled > _EPS):
        fill = _num((row or {}).get("avg_fill_price")) or float(trade["entry"])
        qty = filled or float(trade["qty"])
        trade.update(state=STOCK_MODE_TRADE_HOLDING, qty=qty, fill_price=fill, filled_at=now)
        store.set_trade(trade)
        if trade["kind"] == STOCK_MODE_AUTO_ENTRY:
            store.add_entry(trade["venue"], trade["venue_day"], sym)
        exits = ("the stop and the target rest at the broker" if trade["exits"] == STOCK_MODE_SIDE_NOVA
                 else "the exit is yours")
        _say(sym, now, "ok", f"Nova bought {qty:g} {sym} at {fill:.2f} -- {exits}")
        audit(action=STOCK_MODE_AUDIT_ACTION, outcome="filled", order_id=trade.get("entry_order_id"),
              reason=f"bought {qty:g} {sym} at {fill:.2f} (limit {float(trade['entry']):.2f}); {exits}",
              inputs=_summary(trade))
        return
    if state in ("dead", "gone"):
        why = (f"not filled in {STOCK_MODE_ENTRY_TTL_SEC:g}s -- the price ran past {float(trade['entry']):.2f}"
               if trade.get("cancel_sent_at") else
               "the entry was cancelled outside Nova" if state == "dead" else
               "the entry is gone from the ledger (a Sim rewind or an account reset)")
        trade.update(state=STOCK_MODE_TRADE_MISSED, closed_at=now, note=why)
        store.set_trade(trade)
        if trade["kind"] == STOCK_MODE_APPROVE:
            approval = store.approval(sym)
            if approval and approval.get("state") == "sent":
                store.set_approval(sym, {**approval, "state": "withdrawn", "reason": f"missed: {why}"})
        _say(sym, now, "warn", f"Missed: {why}")
        audit(action=STOCK_MODE_AUDIT_ACTION, outcome="missed", order_id=trade.get("entry_order_id"), reason=why,
              inputs=_summary(trade))
        return
    sent_cancel = trade.get("cancel_sent_at")
    due = now >= float(trade["sent_at"]) + STOCK_MODE_ENTRY_TTL_SEC
    retry = sent_cancel is not None and now - float(sent_cancel) >= STOCK_MODE_CANCEL_RETRY_SEC
    if (sent_cancel is None and due) or retry:
        receipt = await orders.cancel(trade, int(trade["entry_order_id"]))
        trade["cancel_sent_at"] = now
        store.set_trade(trade)
        if not receipt.ok:
            logger.warning("stock mode: cancelling %s's entry %s refused -- %s", sym, trade["entry_order_id"],
                           orders.receipt_error(receipt))


def _manage_exits(trade: dict[str, Any], now: float) -> None:
    """Approve: the bracket's exits rest at the broker; the first to fill closes the trade."""
    sym = trade["symbol"]
    for leg, reason in (("target_order_id", "target"), ("stop_order_id", "stop")):
        row = orders.order_row(trade.get(leg))
        if orders.order_state(row) == "filled":
            price = _num((row or {}).get("avg_fill_price")) or float(trade[reason])
            _close(trade, now, reason, price)
            return
    if orders.held_qty(sym) <= _EPS:
        _close(trade, now, "outside", None)


def _manage_yours(trade: dict[str, Any], now: float) -> None:
    """Auto-entry (or a taken-over bracket): the position is the operator's; Nova only notices it closed."""
    if orders.held_qty(trade["symbol"]) <= _EPS:
        _close(trade, now, "outside", None)


def _close(trade: dict[str, Any], now: float, reason: str, price: float | None) -> None:
    sym = trade["symbol"]
    fill = trade.get("fill_price")
    pnl = round((price - float(fill)) * float(trade["qty"]), 2) if price is not None and fill is not None else None
    trade.update(state=STOCK_MODE_TRADE_CLOSED, exit_reason=reason, exit_price=price, closed_at=now)
    store.set_trade(trade)
    said = {"target": f"the target {float(trade['target']):.2f} filled",
            "stop": f"the stop {float(trade['stop']):.2f} filled",
            "outside": "the position was closed"}.get(reason, reason)
    money = f" · {'+' if pnl >= 0 else '-'}${abs(pnl):.2f}" if pnl is not None else ""
    tone = "ok" if reason == "target" else ("bad" if reason == "stop" else "info")
    _say(sym, now, tone, f"Closed: {said}" + (f" at {price:.2f}" if price is not None else "") + money)
    if trade["kind"] == STOCK_MODE_APPROVE:
        store.clear_approval(sym)
    audit(action=STOCK_MODE_AUDIT_ACTION, outcome="closed", reason=f"{said}{money}", inputs=_summary(trade))


# -- helpers ----------------------------------------------------------------------------
def _new_trade(kind: str, sym: str, event: dict[str, Any], now: float, *, venue: str | None, day: str, qty: int,
               entry: Any, stop: Any, target: Any, attempt: str, exits: str) -> dict[str, Any]:
    return {"kind": kind, "state": STOCK_MODE_TRADE_ENTERING, "venue": venue, "venue_day": day, "symbol": sym,
            "setup_id": event.get("setup_id"), "setup_type": event.get("setup_type"), "attempt": attempt,
            "qty": int(qty), "entry": float(entry), "stop": float(stop),
            "target": float(target) if target is not None else None,
            "entry_order_id": None, "target_order_id": None, "stop_order_id": None, "sent_at": now,
            "cancel_sent_at": None, "fill_price": None, "filled_at": None, "exit_price": None,
            "exit_reason": None, "closed_at": None, "exits": exits, "note": None}


def _skip(sym: str, event: dict[str, Any], now: float, refused: tuple[str, str], *, outcome: str = "skipped") -> None:
    code, why = refused
    _say(sym, now, "warn", f"Nova did not buy: {why}")
    audit(action=STOCK_MODE_AUDIT_ACTION, outcome=outcome, reason=why,
          inputs={"symbol": sym, "setup_id": event.get("setup_id"), "setup_type": event.get("setup_type"),
                  "code": code})


def _say(sym: str, now: float, tone: str, text: str) -> None:
    store.note_event(sym, now, tone, text)


def _summary(trade: dict[str, Any]) -> dict[str, Any]:
    keys = ("symbol", "kind", "setup_id", "setup_type", "venue", "venue_day", "qty", "entry", "stop", "target",
            "entry_order_id", "target_order_id", "stop_order_id", "fill_price", "exit_price", "exit_reason", "exits")
    return {k: trade.get(k) for k in keys}


def _setup_name(event: dict[str, Any]) -> str:
    return str(event.get("setup_type") or "setup").replace("_", " ")


def _risk_text(setup: dict[str, Any]) -> str:
    try:
        return f"{float(setup.get('entry')) - float(setup.get('stop')):.2f}"
    except (TypeError, ValueError):
        return "unknown"


def _num(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out > 0 else None


def _warn_once(key: str, msg: str, *args: Any) -> None:
    if key in _warned:
        return
    _warned.add(key)
    logger.warning(msg, *args)


def reset_for_tests(clock: Callable[[], float] | None = None) -> None:
    global _clock, _last_approval_check
    _inbox.clear()
    _warned.clear()
    _last_approval_check = 0.0
    _clock = clock or time.time
