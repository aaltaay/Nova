"""The writes behind the stock-mode routes (ADR 037): set the switch, approve, withdraw, take over.

Each raises ``StockModeError`` with the reason the desk shows, and each act is a ``stock_mode`` line
on the bot's audit stream. Cancels and sends go through the execution door (``stock_mode.orders``).
"""
from __future__ import annotations

import logging
import time
from typing import Any

from bot.audit import record as audit
from bot.errors import BotError
from constants_setups import SETUP_STATE_TRIGGERED
from constants_stock_mode import (
    STOCK_MODE_APPROVE,
    STOCK_MODE_AUDIT_ACTION,
    STOCK_MODE_AUTO_ENTRY,
    STOCK_MODE_BOT,
    STOCK_MODE_HELD,
    STOCK_MODE_INVALID,
    STOCK_MODE_NAMES,
    STOCK_MODE_NOT_APPROVE,
    STOCK_MODE_NOTHING_HELD,
    STOCK_MODE_PLAN_CHANGED,
    STOCK_MODE_SEND,
    STOCK_MODE_SIDE_NOVA,
    STOCK_MODE_SIDE_YOU,
    STOCK_MODE_SIGNAL,
    STOCK_MODE_TRADE_ENTERING,
    STOCK_MODE_TRADE_HOLDING,
    STOCK_MODE_WHY_HELD,
)
from stock_mode import gates, model, orders, runner, store, view
from stock_mode.errors import StockModeError

logger = logging.getLogger(__name__)
_EPS = 1e-9


def _venue_gate(buy: str, sell: str) -> None:
    """A Nova side needs a practice venue at the live edge (decision 2)."""
    if STOCK_MODE_SIDE_NOVA not in (buy, sell):
        return
    venue, replay = gates.venue_state()
    blocked = gates.venue_block(venue, replay)
    if blocked is None:
        return
    lock = model.locks(venue, replay)
    raise StockModeError(blocked[0], (lock["buy"] if buy == STOCK_MODE_SIDE_NOVA else lock["sell"]) or blocked[1],
                         field="buy" if buy == STOCK_MODE_SIDE_NOVA else "sell")


def _held(sym: str) -> float:
    try:
        return float(orders.held_qty(sym))
    except orders.ReadError as exc:
        raise StockModeError(STOCK_MODE_HELD, f"Nova cannot read your {sym} position ({exc}), so it will not "
                             "take the exit", field="sell") from exc


def _bot_list(sym: str, on: bool) -> None:
    from bot.eligibility import add_symbol, remove_symbol
    from bot.persist import load_session, save_session

    row = load_session()
    try:
        (add_symbol if on else remove_symbol)(row, sym)
    except BotError as exc:
        raise StockModeError(STOCK_MODE_INVALID, exc.message, status=400, field="symbol") from exc
    save_session(row)


async def set_mode(symbol: str, buy_raw: Any, sell_raw: Any, risk_raw: Any, *, now: float | None = None,
                   ) -> dict[str, Any]:
    now = time.time() if now is None else now
    sym = model.symbol(symbol)
    buy, sell = model.side(buy_raw, "buy"), model.side(sell_raw, "sell")
    mode = model.mode_of(buy, sell)
    risk = model.risk_usd(risk_raw, required=mode == STOCK_MODE_AUTO_ENTRY)
    _venue_gate(buy, sell)
    before = view.build(sym, now=now)
    was_mode, was_sell = before["mode"], before["sell"]
    if sell == STOCK_MODE_SIDE_NOVA and was_sell == STOCK_MODE_SIDE_YOU and _held(sym) > _EPS:
        raise StockModeError(STOCK_MODE_HELD, STOCK_MODE_WHY_HELD.format(sym=sym), field="sell")
    if was_sell == STOCK_MODE_SIDE_NOVA and sell == STOCK_MODE_SIDE_YOU and _nova_holds_exits(sym, before):
        await take_over(sym, now=now, keep_buy=buy, risk=risk)
    if was_mode == STOCK_MODE_AUTO_ENTRY and mode != STOCK_MODE_AUTO_ENTRY:
        await _cancel_working_entry(sym, now)
    if was_mode == STOCK_MODE_APPROVE and mode != STOCK_MODE_APPROVE:
        store.clear_approval(sym)
    if mode == STOCK_MODE_BOT:
        _bot_list(sym, True)
        store.clear_switch(sym)
    else:
        if was_mode == STOCK_MODE_BOT or (before.get("bot") or {}).get("on_list"):
            _bot_list(sym, False)
        if mode == STOCK_MODE_SIGNAL:
            store.clear_switch(sym)
        else:
            store.set_switch(sym, {"buy": buy, "sell": sell, "risk_usd": risk, "set_at": now})
    if mode != was_mode:
        store.note_event(sym, now, "info", f"{STOCK_MODE_NAMES[mode]}: {_mode_words(mode, sym)}")
        audit(action=STOCK_MODE_AUDIT_ACTION, outcome="set",
              reason=f"{sym}: {STOCK_MODE_NAMES[was_mode]} -> {STOCK_MODE_NAMES[mode]}",
              inputs={"symbol": sym, "from": was_mode, "to": mode, "risk_usd": risk})
    return view.build(sym, now=now)


def _mode_words(mode: str, sym: str) -> str:
    return {
        STOCK_MODE_SIGNAL: "Nova draws the plan and tells you when; it places nothing",
        STOCK_MODE_APPROVE: "approve the plan, and Nova sends the buy with its stop and target",
        STOCK_MODE_AUTO_ENTRY: f"Nova buys {sym} once, at the trigger; every sell is yours",
        STOCK_MODE_BOT: "the bot trades it in and out by its own rules",
    }[mode]


def _nova_holds_exits(sym: str, before: dict[str, Any]) -> bool:
    trade = before.get("trade") or {}
    return trade.get("state") in (STOCK_MODE_TRADE_ENTERING, STOCK_MODE_TRADE_HOLDING) \
        and trade.get("exits") == STOCK_MODE_SIDE_NOVA


async def _cancel_working_entry(sym: str, now: float) -> None:
    """Auto-entry turned off: an entry Nova sent that has not filled is cancelled."""
    venue, _replay = gates.venue_state()
    trade = store.trade(venue, sym)
    if not trade or trade.get("kind") != STOCK_MODE_AUTO_ENTRY or trade.get("state") != STOCK_MODE_TRADE_ENTERING \
            or not trade.get("entry_order_id"):
        return
    receipt = await orders.cancel(trade, int(trade["entry_order_id"]), source="manual")
    trade["cancel_sent_at"] = now
    store.set_trade(trade)
    if not receipt.ok:
        logger.warning("stock mode: cancelling %s's working entry refused -- %s", sym, orders.receipt_error(receipt))


# -- approve ----------------------------------------------------------------------------
async def approve(symbol: str, body: dict[str, Any], *, now: float | None = None) -> dict[str, Any]:
    now = time.time() if now is None else now
    sym = model.symbol(symbol)
    current = view.build(sym, now=now)
    if current["mode"] != STOCK_MODE_APPROVE:
        raise StockModeError(STOCK_MODE_NOT_APPROVE, f"{sym} is not in Approve: set Buy to You and Sell to Nova first")
    _venue_gate(STOCK_MODE_SIDE_YOU, STOCK_MODE_SIDE_NOVA)
    try:
        approved = {"setup_id": str(body["setup_id"]), "entry": float(body["entry"]), "stop": float(body["stop"]),
                    "target": float(body["target"]), "qty": int(body["qty"])}
    except (KeyError, TypeError, ValueError):
        raise StockModeError(STOCK_MODE_INVALID, "an approval names setup_id, entry, stop, target and qty",
                             status=400) from None
    if approved["qty"] < 1:
        raise StockModeError(STOCK_MODE_INVALID, "the size is at least one share", status=400, field="qty")
    if not approved["stop"] < approved["entry"] < approved["target"]:
        raise StockModeError(STOCK_MODE_INVALID, "a long plan has its stop under the entry and its target over it",
                             status=400)
    lane = runner.lane_of(sym, approved["setup_id"])
    if lane is None:
        raise StockModeError(STOCK_MODE_PLAN_CHANGED, "that setup is gone from the scanner: nothing to approve")
    if not model.plan_matches(approved, lane.get("setup")):
        raise StockModeError(STOCK_MODE_PLAN_CHANGED,
                             f"the setup is armed at {model.levels_text(lane.get('setup') or {})} now: approve "
                             "those levels")
    state = lane.get("state")
    approval = {**approved, "setup_type": lane.get("setup_type"), "approved_at": now, "state": "waiting",
                "reason": None}
    if state in runner.WAITING_STATES:
        if body.get("now"):
            raise StockModeError(STOCK_MODE_PLAN_CHANGED, "the setup has not triggered: approve it and Nova sends "
                                 "at the trigger")
        store.set_approval(sym, approval)
        store.note_event(sym, now, "info", f"Approved: Nova sends at the {float(lane['setup'].get('trigger') or 0):.2f} "
                                           f"trigger if the tape says go")
        audit(action=STOCK_MODE_AUDIT_ACTION, outcome="approved",
              reason=f"{sym}: buy {approved['qty']} at {approved['entry']:.2f}, stop {approved['stop']:.2f}, target "
                     f"{approved['target']:.2f} at the trigger", inputs={"symbol": sym, **approved})
        return view.build(sym, now=now)
    if state == SETUP_STATE_TRIGGERED and body.get("now"):
        blocked = gates.desk_block()
        if blocked:
            raise StockModeError(STOCK_MODE_SEND, blocked[1])
        store.set_approval(sym, approval)
        audit(action=STOCK_MODE_AUDIT_ACTION, outcome="approved", reason=f"{sym}: buy now at {approved['entry']:.2f}",
              inputs={"symbol": sym, **approved, "now": True})
        trade = await runner.send_bracket_now(sym, approval, now, setup_type=lane.get("setup_type"))
        if trade is None:
            refused = store.approval(sym) or {}
            raise StockModeError(STOCK_MODE_SEND, str(refused.get("reason") or "the execution door refused it"))
        store.note_event(sym, now, "info", f"Sent: buy {approved['qty']} {sym} at {approved['entry']:.2f} with its stop "
                                           "and target")
        return view.build(sym, now=now)
    raise StockModeError(STOCK_MODE_PLAN_CHANGED, f"the setup is {state}: nothing to approve")


async def withdraw(symbol: str, *, now: float | None = None) -> dict[str, Any]:
    """Withdraw a waiting approval; a sent entry that has not filled is cancelled (its exits go with it)."""
    now = time.time() if now is None else now
    sym = model.symbol(symbol)
    approval = store.approval(sym)
    venue, _replay = gates.venue_state()
    trade = store.trade(venue, sym)
    if trade and trade.get("kind") == STOCK_MODE_APPROVE and trade.get("state") == STOCK_MODE_TRADE_ENTERING:
        receipt = await orders.cancel(trade, int(trade["entry_order_id"]), source="manual")
        trade["cancel_sent_at"] = now
        store.set_trade(trade)
        if not receipt.ok:
            raise StockModeError(STOCK_MODE_SEND, f"the entry could not be cancelled: {orders.receipt_error(receipt)}")
    elif not approval or approval.get("state") != "waiting":
        raise StockModeError(STOCK_MODE_NOTHING_HELD, f"no approval of {sym} is waiting")
    store.clear_approval(sym)
    store.note_event(sym, now, "info", "Approval cancelled")
    audit(action=STOCK_MODE_AUDIT_ACTION, outcome="withdrawn", reason=f"{sym}: you cancelled the approval",
          inputs={"symbol": sym, "setup_id": (approval or {}).get("setup_id")})
    return view.build(sym, now=now)


# -- take over the exit -------------------------------------------------------------------
async def take_over(symbol: str, *, now: float | None = None, keep_buy: str | None = None,
                    risk: float | None = None) -> dict[str, Any]:
    """Cancel the exits Nova holds on the stock: Approve's bracket legs, or the bot's trade (``handed``).
    The stock's Sell becomes You; a handed bot entry counts as the stock's Nova entry today."""
    now = time.time() if now is None else now
    sym = model.symbol(symbol)
    venue, _replay = gates.venue_state()
    trade = store.trade(venue, sym)
    before = view.build(sym, now=now)
    if trade and trade.get("kind") == STOCK_MODE_APPROVE and trade.get("exits") == STOCK_MODE_SIDE_NOVA \
            and trade.get("state") in (STOCK_MODE_TRADE_ENTERING, STOCK_MODE_TRADE_HOLDING):
        await _take_bracket(trade, now)
    elif (before.get("trade") or {}).get("kind") == STOCK_MODE_BOT:
        await _take_bot(sym, venue, now)
    else:
        raise StockModeError(STOCK_MODE_NOTHING_HELD, f"Nova holds no exit of {sym} to take over")
    buy = keep_buy or (before.get("buy") or STOCK_MODE_SIDE_YOU)
    if buy == STOCK_MODE_SIDE_NOVA and (risk or (store.switch(sym) or {}).get("risk_usd")):
        store.set_switch(sym, {"buy": buy, "sell": STOCK_MODE_SIDE_YOU,
                               "risk_usd": risk or (store.switch(sym) or {}).get("risk_usd"), "set_at": now})
    else:
        store.clear_switch(sym)
    if (before.get("bot") or {}).get("on_list"):
        _bot_list(sym, False)
    store.clear_approval(sym)
    store.note_event(sym, now, "info", "You took over the exit: Nova no longer sells it")
    return view.build(sym, now=now)


async def _take_bracket(trade: dict[str, Any], now: float) -> None:
    sym = trade["symbol"]
    if trade.get("state") == STOCK_MODE_TRADE_ENTERING:
        receipt = await orders.cancel(trade, int(trade["entry_order_id"]), source="manual")
        trade["cancel_sent_at"] = now
    else:
        refused = []
        for leg in ("target_order_id", "stop_order_id"):
            if trade.get(leg):
                receipt = await orders.cancel(trade, int(trade[leg]), source="manual")
                if not receipt.ok:
                    refused.append(orders.receipt_error(receipt))
        if refused:
            raise StockModeError(STOCK_MODE_SEND, f"the exits could not all be cancelled: {'; '.join(refused)}")
        trade["exits"] = STOCK_MODE_SIDE_YOU
        trade["note"] = "you took over the exit"
    store.set_trade(trade)
    audit(action=STOCK_MODE_AUDIT_ACTION, outcome="handed", reason=f"{sym}: you took over the exit -- the bracket's "
          "stop and target were cancelled", inputs={"symbol": sym, "setup_id": trade.get("setup_id")})


async def _take_bot(sym: str, venue: str | None, now: float) -> None:
    from bot.first_pullback import runner as bot_runner

    try:
        handed = await bot_runner.hand_over(sym, now=now)
    except BotError as exc:
        raise StockModeError(exc.reason, exc.message) from exc
    if handed.get("state") == "handed":
        store.add_entry(venue, runner.venue_day(now), sym)
