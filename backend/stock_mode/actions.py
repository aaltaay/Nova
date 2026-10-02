"""The writes behind the stock-mode routes (ADR 037, ADR 042 F): set the switch, approve, withdraw, take over.

Each raises ``StockModeError`` with the reason the desk shows, and each act is a ``stock_mode`` line
on the bot's audit stream. Cancels and sends go through the execution door (``stock_mode.orders``).

ADR 042: this is the bot list's one owner -- ``bot.allowlist`` and every desk button set a stock here,
so each meets the same rules (the Live lock, "you hold it", the 50-stock cap). A stock has one mode:
Bot (this venue's bot list) and an Auto-entry / Approve switch never stand together. A take-over always
leaves Buy on You, and never claims a cancel it did not get. ADR 043: Buy to Nova stars the stock onto
today's hot list (``hot_list.stock_tie``); a full list refuses before anything changes.
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
    STOCK_MODE_FILTERED,
    STOCK_MODE_HELD,
    STOCK_MODE_INVALID,
    STOCK_MODE_NAMES,
    STOCK_MODE_NOT_A_TRADE,
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
from stock_mode import exit_trade, gates, model, orders, runner, store, view
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
        logger.warning("stock mode: the %s position is unreadable -- the exit is not taken", sym, exc_info=True)
        raise StockModeError(STOCK_MODE_HELD, f"Nova cannot read your {sym} position (the backend log has the error), so it will not "
                             "take the exit", field="sell") from exc


def _room_on_list(sym: str) -> None:
    """Refuse a stock the full bot list has no room for (``BOT_ALLOWLIST_FULL``), before anything changes."""
    from bot.eligibility import normalize_symbols
    from bot.persist import load_session
    from constants_bot import BOT_REASON_ALLOWLIST_FULL, BOT_SYMBOL_ALLOWLIST_CAP

    current = normalize_symbols(load_session().get("symbol_allowlist"))
    if sym not in current and len(current) >= BOT_SYMBOL_ALLOWLIST_CAP:
        raise StockModeError(BOT_REASON_ALLOWLIST_FULL, f"the bot's list is full ({BOT_SYMBOL_ALLOWLIST_CAP} stocks on "
                             f"this venue): set one back to Signal only before adding {sym}", field="symbol")


def _bot_list(sym: str, on: bool) -> None:
    """Put the stock on (or take it off) this venue's bot list; a full list is refused with its reason."""
    from bot.eligibility import add_symbol, remove_symbol
    from bot.persist import load_session, save_session

    row = load_session()
    try:
        (add_symbol if on else remove_symbol)(row, sym)
    except BotError as exc:
        raise StockModeError(exc.reason or STOCK_MODE_INVALID, exc.message, status=exc.status_code,
                             field="symbol") from exc
    save_session(row)


async def set_mode(symbol: str, buy_raw: Any, sell_raw: Any, risk_raw: Any = None, *,
                   now: float | None = None) -> dict[str, Any]:
    """Set the stock's switch. ``risk_raw`` is ignored (ADR 042: risk per trade is the venue sleeve's)."""
    del risk_raw
    now = time.time() if now is None else now
    sym = model.symbol(symbol)
    buy, sell = model.side(buy_raw, "buy"), model.side(sell_raw, "sell")
    mode = model.mode_of(buy, sell)
    _venue_gate(buy, sell)
    from hot_list import stock_tie

    star = stock_tie.star_needed(sym, buy)   # ADR 043: Nova buys only listed stocks; a full list refuses first
    before = view.build(sym, now=now)
    was_mode, was_sell = before["mode"], before["sell"]
    if sell == STOCK_MODE_SIDE_YOU and _exit_held(sym):
        await _take_exits(sym, now)          # Sell: You takes back the exit you handed Nova
        return view.build(sym, now=now)
    if mode == was_mode:
        if star:
            stock_tie.star(sym)
        return before
    if sell == STOCK_MODE_SIDE_NOVA and was_sell == STOCK_MODE_SIDE_YOU and _held(sym) > _EPS:
        raise StockModeError(STOCK_MODE_HELD, STOCK_MODE_WHY_HELD.format(sym=sym), field="sell")
    if mode == STOCK_MODE_BOT:
        _room_on_list(sym)              # first: a full list refuses before anything else changes
    if star:
        stock_tie.star(sym)             # the first change: Buy to Nova puts the stock on today's hot list
    if was_sell == STOCK_MODE_SIDE_NOVA and sell == STOCK_MODE_SIDE_YOU and _nova_holds_exits(sym, before):
        await _take_exits(sym, now)
    if was_mode == STOCK_MODE_AUTO_ENTRY and mode != STOCK_MODE_AUTO_ENTRY:
        await _cancel_working_entry(sym, now)
    if was_mode == STOCK_MODE_APPROVE and mode != STOCK_MODE_APPROVE:
        store.clear_approval(sym)
    if mode == STOCK_MODE_BOT:
        _bot_list(sym, True)
        store.clear_switch(sym)
        store.clear_approval(sym)
    else:
        if was_mode == STOCK_MODE_BOT or (before.get("bot") or {}).get("on_list"):
            _bot_list(sym, False)
        if mode == STOCK_MODE_SIGNAL:
            store.clear_switch(sym)
        else:
            store.set_switch(sym, {"buy": buy, "sell": sell, "set_at": now})
    store.note_event(sym, now, "info", f"{STOCK_MODE_NAMES[mode]}: {_mode_words(mode, sym)}")
    audit(action=STOCK_MODE_AUDIT_ACTION, outcome="set",
          reason=f"{sym}: {STOCK_MODE_NAMES[was_mode]} -> {STOCK_MODE_NAMES[mode]}",
          inputs={"symbol": sym, "from": was_mode, "to": mode})
    return view.build(sym, now=now)


def _mode_words(mode: str, sym: str) -> str:
    return {
        STOCK_MODE_SIGNAL: "Nova draws the plan and tells you when; it places nothing",
        STOCK_MODE_APPROVE: "approve the plan, and Nova sends the buy with its stop and target",
        STOCK_MODE_AUTO_ENTRY: (f"Nova buys {sym} by the bot's rules (a setup at Strategy, while the bot is "
                                "Active); every sell is yours"),
        STOCK_MODE_BOT: "the bot trades it in and out by its own rules",
    }[mode]


def _exit_held(sym: str) -> bool:
    """Nova holds the exit of a stock you bought (``exit_trade``) on the desk's venue."""
    venue, _replay = gates.venue_state()
    trade = store.trade(venue, sym)
    return bool(trade and trade.get("kind") == exit_trade.KIND_EXIT and trade.get("state") == STOCK_MODE_TRADE_HOLDING
                and trade.get("exits") == STOCK_MODE_SIDE_NOVA)


async def take_exit(symbol: str, body: dict[str, Any], *, now: float | None = None) -> dict[str, Any]:
    """Nova takes the exit of the shares you hold (``exit_trade.take``): Paper, and Sim at the live edge."""
    return await exit_trade.take(symbol, stop=body.get("stop"), trail=bool(body.get("trail", True)), now=now)


def _nova_holds_exits(sym: str, before: dict[str, Any]) -> bool:
    trade = before.get("trade") or {}
    return trade.get("state") in (STOCK_MODE_TRADE_ENTERING, STOCK_MODE_TRADE_HOLDING) \
        and trade.get("exits") == STOCK_MODE_SIDE_NOVA


async def _cancel_working_entry(sym: str, now: float) -> None:
    """Auto-entry turned off: an entry Nova sent that has not filled is cancelled -- or the refusal is said."""
    venue, _replay = gates.venue_state()
    trade = store.trade(venue, sym)
    if not trade or trade.get("kind") != STOCK_MODE_AUTO_ENTRY or trade.get("state") != STOCK_MODE_TRADE_ENTERING \
            or not trade.get("entry_order_id"):
        return
    receipt = await orders.cancel(trade, int(trade["entry_order_id"]), source="manual")
    if not receipt.ok:
        raise StockModeError(STOCK_MODE_SEND, f"Nova's working buy of {sym} could not be cancelled "
                             f"({orders.receipt_error(receipt)}) -- it still rests; the switch is unchanged")
    trade["cancel_sent_at"] = now
    store.set_trade(trade)


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
    try:
        lane = runner.lane_of(sym, approved["setup_id"])
    except runner.LanesUnreadable as exc:
        logger.warning("stock mode: the scanner's lanes are unreadable -- nothing is approved", exc_info=True)
        raise StockModeError(STOCK_MODE_PLAN_CHANGED, "the setup scanner could not be read (the backend log has the error): Nova cannot "
                             "check the plan, so it approves nothing") from exc
    if lane is None:
        raise StockModeError(STOCK_MODE_PLAN_CHANGED, "that setup is gone from the scanner: nothing to approve")
    if lane.get("state") == "filtered":
        why = str(lane.get("reason") or "").removeprefix("filtered: ")
        raise StockModeError(STOCK_MODE_FILTERED, f"the template's stock filter keeps {sym} out ({why}): Nova sends "
                             "no approval for it")
    judged = model.lane_verdict(lane, view.spread_of(sym))
    if not judged["ok"]:
        raise StockModeError(STOCK_MODE_NOT_A_TRADE, "not a trade: " + "; ".join(judged["reasons"]))
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
        if not receipt.ok:
            raise StockModeError(STOCK_MODE_SEND, f"the entry could not be cancelled: {orders.receipt_error(receipt)} "
                                 "-- it still rests")
        trade["cancel_sent_at"] = now
        store.set_trade(trade)
    elif not approval or approval.get("state") != "waiting":
        raise StockModeError(STOCK_MODE_NOTHING_HELD, f"no approval of {sym} is waiting")
    store.clear_approval(sym)
    store.note_event(sym, now, "info", "Approval cancelled")
    audit(action=STOCK_MODE_AUDIT_ACTION, outcome="withdrawn", reason=f"{sym}: you cancelled the approval",
          inputs={"symbol": sym, "setup_id": (approval or {}).get("setup_id")})
    return view.build(sym, now=now)


# -- take over the exit -------------------------------------------------------------------
async def take_over(symbol: str, *, now: float | None = None, **_ignored: Any) -> dict[str, Any]:
    """Cancel the exits Nova holds on the stock: Approve's bracket legs, or the bot's trade (``handed``).
    Buy goes to You as well -- a take-over never turns into Auto-entry -- so the stock is Signal only.
    A cancel the broker refuses keeps the trade and says the order still rests."""
    now = time.time() if now is None else now
    sym = model.symbol(symbol)
    before = view.build(sym, now=now)
    await _take_exits(sym, now)
    store.clear_switch(sym)
    if (before.get("bot") or {}).get("on_list"):
        _bot_list(sym, False)
    store.clear_approval(sym)
    store.note_event(sym, now, "info", "You took over the exit: Nova no longer sells it, and buys nothing more here")
    audit(action=STOCK_MODE_AUDIT_ACTION, outcome="set", reason=f"{sym}: {STOCK_MODE_NAMES[before['mode']]} -> "
          f"{STOCK_MODE_NAMES[STOCK_MODE_SIGNAL]} (you took over the exit)",
          inputs={"symbol": sym, "from": before["mode"], "to": STOCK_MODE_SIGNAL})
    return view.build(sym, now=now)


async def _take_exits(sym: str, now: float) -> None:
    venue, _replay = gates.venue_state()
    trade = store.trade(venue, sym)
    before = view.build(sym, now=now)
    if trade and trade.get("kind") == exit_trade.KIND_EXIT and trade.get("exits") == STOCK_MODE_SIDE_NOVA \
            and trade.get("state") == STOCK_MODE_TRADE_HOLDING:
        await exit_trade.take_back(trade, now)
    elif trade and trade.get("kind") == STOCK_MODE_APPROVE and trade.get("exits") == STOCK_MODE_SIDE_NOVA \
            and trade.get("state") in (STOCK_MODE_TRADE_ENTERING, STOCK_MODE_TRADE_HOLDING):
        await _take_bracket(trade, now)
    elif (before.get("trade") or {}).get("kind") == STOCK_MODE_BOT:
        await _take_bot(sym, now)
    else:
        raise StockModeError(STOCK_MODE_NOTHING_HELD, f"Nova holds no exit of {sym} to take over")


async def _take_bracket(trade: dict[str, Any], now: float) -> None:
    sym = trade["symbol"]
    if trade.get("state") == STOCK_MODE_TRADE_ENTERING:
        receipt = await orders.cancel(trade, int(trade["entry_order_id"]), source="manual")
        if not receipt.ok:
            raise StockModeError(STOCK_MODE_SEND, f"the entry could not be cancelled ({orders.receipt_error(receipt)}) "
                                 "-- it still rests, with its stop and target: Nova keeps the trade")
        trade["cancel_sent_at"] = now
    else:
        refused = []
        for leg in ("target_order_id", "stop_order_id"):
            if trade.get(leg):
                receipt = await orders.cancel(trade, int(trade[leg]), source="manual")
                if receipt.ok:
                    trade[leg] = None
                else:
                    refused.append(f"the {leg.split('_')[0]} ({orders.receipt_error(receipt)})")
        if refused:
            store.set_trade(trade)
            audit(action=STOCK_MODE_AUDIT_ACTION, outcome="refused",
                  reason=f"{sym}: {', '.join(refused)} could not be cancelled -- it still rests; Nova keeps the trade",
                  inputs={"symbol": sym, "setup_id": trade.get("setup_id")})
            raise StockModeError(STOCK_MODE_SEND, f"{', '.join(refused)} could not be cancelled and still rests: "
                                 "Nova keeps the exit -- try again, or flatten")
        trade["exits"] = STOCK_MODE_SIDE_YOU
        trade["note"] = "you took over the exit"
    store.set_trade(trade)
    audit(action=STOCK_MODE_AUDIT_ACTION, outcome="handed", reason=f"{sym}: you took over the exit -- the bracket's "
          "stop and target were cancelled", inputs={"symbol": sym, "setup_id": trade.get("setup_id")})


async def _take_bot(sym: str, now: float) -> None:
    from bot.first_pullback.handover import hand_over

    try:
        await hand_over(sym, now=now)
    except BotError as exc:
        raise StockModeError(exc.reason or STOCK_MODE_SEND, exc.message) from exc
