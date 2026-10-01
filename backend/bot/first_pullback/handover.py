"""The bot lets go of its trade: the operator takes over the exit, or the desk leaves the venue
(ADR 037, ADR 042 F).

- ``hand_over``: before the fill the entry is cancelled (the bracket's exits go with it) and
  the trade ends ``missed``; after it, the resting target and stop are cancelled, the bot
  stops watching, and the trade ends ``handed``. A cancel the broker refuses keeps the trade
  and says the order still rests -- the bot never claims a cancel it did not get.
- ``leave_venue``: the desk is about to leave the trade's venue -- an entry not yet filled is
  cancelled there first (the door still sends to that venue), and the trade ends ``missed``.
  A filled trade keeps its resting exits (Paper's fill while the desk is elsewhere).

Reads and sends go through ``bot.first_pullback.orders``; the trade's states are the
runner's (``runner._save`` / ``runner._close``).
"""
from __future__ import annotations

import logging
from typing import Any

from bot.audit import record as audit
from bot.errors import BotError
from bot.first_pullback import orders
from bot.persist import load_session
from constants_bot import BOT_AUDIT_ACTION_TRADE

logger = logging.getLogger(__name__)


def _runner():
    from bot.first_pullback import runner

    return runner


async def hand_over(symbol: str, now: float | None = None) -> dict[str, Any]:
    """The operator takes the exit of the bot's trade on ``symbol``. Raises ``BotError`` when the bot
    holds no trade on the stock, is already selling it, or a cancel was refused (the trade stays)."""
    from bot.gates import current_venue
    from bot.risk import adjust_bot_qty, drop_working
    from constants_stock_mode import STOCK_MODE_BOT_EXITING, STOCK_MODE_NOTHING_HELD, STOCK_MODE_SEND

    run = _runner()
    now = run.now() if now is None else now
    sym = (symbol or "").strip().upper()
    trade = load_session().get("trade")
    if not isinstance(trade, dict) or str(trade.get("symbol") or "").upper() != sym \
            or trade.get("state") not in run.LIVE_STATES:
        raise BotError(f"the bot holds no trade on {sym}", 409, STOCK_MODE_NOTHING_HELD)
    if trade.get("venue") != current_venue():
        # Its orders are another venue's ids: a cancel sent here would reach this venue's
        # order of the same number (on Live, a real IBKR order).
        raise BotError(f"the bot's trade on {sym} is on {trade.get('venue')} -- move the desk there to take "
                       "it over", 409, STOCK_MODE_NOTHING_HELD)
    trade = dict(trade)
    if trade["state"] == "exiting":
        raise BotError(f"the bot is already selling {sym} -- let it finish, or flatten", 409, STOCK_MODE_BOT_EXITING)
    if trade["state"] == "entering":
        receipt = await orders.cancel(trade, int(trade["entry_order_id"]))
        if not receipt.ok:
            row = orders.order_row(trade["entry_order_id"])
            raise BotError(f"the bot's entry on {sym} could not be cancelled ({orders.receipt_error(receipt)}) -- "
                           f"it is {orders.order_state(row)}: the bot keeps the trade", 409, STOCK_MODE_SEND)
        drop_working(int(trade["entry_order_id"]))
        why = "you took the stock back before the bot's entry filled -- the entry was cancelled"
        trade.update(state="missed", closed_ts=now, note=why)
        run._save(trade)
        audit(action=BOT_AUDIT_ACTION_TRADE, outcome="missed", order_id=trade["entry_order_id"], reason=why,
              inputs=run._summary(trade))
        return trade
    refused = await run._cancel_legs(trade)
    for leg, _receipt in refused:
        row = orders.order_row(trade[leg])
        if orders.order_state(row) == "filled":      # it filled as the operator reached for it
            reason = "target" if leg == "target_order_id" else "stop"
            run._close(trade, now, reason, run._num((row or {}).get("avg_fill_price"))
                       or float(trade["target1" if reason == "target" else "stop"]))
            return dict(load_session().get("trade") or trade)
    if refused:
        still = ", ".join(f"the {leg.split('_')[0]} ({orders.receipt_error(r)})" for leg, r in refused)
        audit(action=BOT_AUDIT_ACTION_TRADE, outcome="note", inputs=run._summary(trade),
              reason=f"you asked to take over {sym}, but {still} could not be cancelled -- it still rests; "
                     "the bot keeps the trade")
        raise BotError(f"{still} could not be cancelled and still rests: the bot keeps {sym}'s trade -- try again, "
                       "or flatten", 409, STOCK_MODE_SEND)
    trade.update(state="handed", target_order_id=None, stop_order_id=None, exit_reason="handed", closed_ts=now,
                 note="you took over the exit: the bot no longer sells it")
    adjust_bot_qty(trade["symbol"], -float(trade["qty"]))
    run._save(trade)
    audit(action=BOT_AUDIT_ACTION_TRADE, outcome="handed", reason=f"you took over the exit of {sym}: the bot "
          "cancelled its target and stop and stopped watching", inputs=run._summary(trade))
    return trade


async def leave_venue(old: str, new: str, now: float | None = None) -> list[dict[str, Any]]:
    """The desk is leaving ``old``: cancel the bot's entry still working there (and any working bot buy
    from the localhost API). ``[{venue, symbol, order_id, by, text, ok}]`` for each."""
    from bot.risk import drop_working

    run = _runner()
    now = run.now() if now is None else now
    out: list[dict[str, Any]] = []
    row = load_session()
    trade = row.get("trade")
    entry_id = None
    if isinstance(trade, dict) and trade.get("state") == "entering" and trade.get("venue") == old \
            and trade.get("entry_order_id"):
        trade = dict(trade)
        entry_id = int(trade["entry_order_id"])
        receipt = await orders.cancel(trade, entry_id)
        if receipt.ok:
            drop_working(entry_id)
            why = f"the desk left {old} before the entry filled -- the entry was cancelled there"
            trade.update(state="missed", closed_ts=now, note=why)
            run._save(trade)
            audit(action=BOT_AUDIT_ACTION_TRADE, outcome="missed", order_id=entry_id, reason=why,
                  inputs=run._summary(trade))
            out.append({"venue": old, "symbol": trade["symbol"], "order_id": entry_id, "by": "bot", "ok": True,
                        "text": f"Nova's bot's buy of {trade['symbol']} on {old} was cancelled: the desk moved to {new}"})
        else:
            out.append({"venue": old, "symbol": trade["symbol"], "order_id": entry_id, "by": "bot", "ok": False,
                        "text": f"Nova's bot's buy of {trade['symbol']} on {old} could not be cancelled "
                                f"({orders.receipt_error(receipt)}) -- it may still fill there"})
    for item in list(row.get("working") or []):
        if str(item.get("side") or "").upper() != "BUY" or item.get("venue") not in (old,) \
                or int(item.get("order_id") or 0) in (0, entry_id):
            continue
        oid = int(item["order_id"])
        receipt = await orders.cancel({"venue": old, "setup_id": "api", "symbol": item.get("symbol")}, oid)
        if receipt.ok:
            drop_working(oid)
            audit(action="ttl_cancel", outcome="ok", order_id=oid, reason=f"the desk left {old}", inputs=item)
        out.append({"venue": old, "symbol": item.get("symbol"), "order_id": oid, "by": "bot", "ok": bool(receipt.ok),
                    "text": (f"the bot API's buy of {item.get('symbol')} on {old} was cancelled: the desk moved to {new}"
                             if receipt.ok else f"the bot API's buy of {item.get('symbol')} on {old} could not be "
                             f"cancelled ({orders.receipt_error(receipt)})")})
    return out
