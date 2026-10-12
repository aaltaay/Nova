"""Nova takes the exit of a stock you bought (ADR 037 amendment 2026-10-01). Paper, and Sim -- at the live edge, or
on a loaded replay (ADR 052 amendment, #815: the trade is the replay's, its minutes the replay's candles at the
playhead, and it goes back with a rewind like the runner's other trades).

Operator ask: "I can instruct Nova to sell it for me when I have a trade"; mockup v4b, "1 go". You hand
Nova the sell of the shares the venue holds: a SELL stop at your stop, through the execution door (source
``manual``, origin ``nova_exit``). Nova keeps a trade of kind ``exit`` (``stock_mode.store``) and, every
runner tick:

- the stop that fills closes the trade;
- a position that is gone closes it (``outside``), and a stop cancelled outside Nova hands the exit back
  to you (``handed``) -- Nova never keeps a trade it holds no order for;
- with ``trail``, once per closed minute, a round number a 1-minute candle closed over since the trade
  began raises the stop by a replace of the stop order -- ``stock_read.held``'s rule: 5c under a half
  dollar, only over the stop and under the price, never down.

**Nova takes the cover** (ADR 048 step 3): on a short you hold, the mirror -- a BUY stop over the price at
your buy stop for every share short, lowered (``stock_read.held_short``: 5c over a half dollar a candle
closed under, only under the stop and over the price, never up). The trade carries ``side: "short"``; its
moves are kept in ``raised`` as a long's are.

Nothing here runs on Live: the take refuses it, and the runner only manages a trade on the desk's venue.

**Targets beside the stop** (#681): with a ``target`` -- and a ``target2`` for the second half (#845) -- Nova
rests them beside its stop as one exit-only pair through the door (``exit_orders.place_pair``, committed
once): target 1 sells ``target1_fraction`` of the shares (half by default), target 2 the rest, and a target's
fill shrinks the stop to the shares left at the broker. The stop stays where it is -- never moved to the
average -- and the trail still moves only the stop, a replace that keeps the pair whole. Each sale is
booked in ``halves`` (``bot.first_pullback.halves``): which half sold where, and the trade's money over
every share. No target: the stop alone, as before.
"""
from __future__ import annotations

import logging
from typing import Any

from bot.audit import record as audit
from constants_stock_mode import (
    STOCK_MODE_AUDIT_ACTION,
    STOCK_MODE_EXIT,
    STOCK_MODE_HELD,
    STOCK_MODE_INVALID,
    STOCK_MODE_LIVE,
    STOCK_MODE_NOTHING_HELD,
    STOCK_MODE_SEND,
    STOCK_MODE_SIDE_NOVA,
    STOCK_MODE_SIDE_YOU,
    STOCK_MODE_TRADE_CLOSED,
    STOCK_MODE_TRADE_ENTERING,
    STOCK_MODE_TRADE_HANDED,
    STOCK_MODE_TRADE_HOLDING,
    STOCK_MODE_WHY_LIVE_EXIT,
)
from bot.first_pullback import halves
from stock_mode import exit_legs, exit_orders, exit_targets, gates, model, orders, store
from stock_mode.errors import StockModeError

logger = logging.getLogger(__name__)
KIND_EXIT = STOCK_MODE_EXIT
MIN = 60
_EPS = 1e-9


# -- reads ------------------------------------------------------------------------------
def avg_cost(symbol: str, short: bool = False) -> float | None:
    """The venue position's average cost (a short's: what it was sold at); None when it cannot be read or has none."""
    from ibkr import account

    try:
        rows = [p for p in account.get_positions() if str(p.get("symbol") or "").upper() == symbol
                and (float(p.get("qty") or 0) < 0 if short else float(p.get("qty") or 0) > 0)]
    except Exception as exc:
        raise orders.ReadError(f"position unreadable: {exc}") from exc
    for p in rows:
        try:
            cost = float(p.get("avg_cost"))
        except (TypeError, ValueError):
            continue
        if cost > 0:
            return cost
    return None


def _closed_bars(symbol: str, now: float) -> list[dict[str, Any]]:
    """Today's closed 1-minute candles, oldest first (the stock read's own reader)."""
    from constants_stock_read import STOCK_READ_BARS_LIMIT
    from sensors.feeds import get_bars
    from stock_read.indicators import session_of

    bars, _source = get_bars(symbol, "1Min", STOCK_READ_BARS_LIMIT)
    return session_of([b for b in bars if float(b["t"]) + MIN <= now])


def _closed_replay_bars(symbol: str, now: float) -> list[dict[str, Any]]:
    """On a Sim replay: the Sim chart's candles completed by the playhead (``stock_read.replay_read.bars``), never a
    minute after it."""
    from constants_stock_read import STOCK_READ_BARS_LIMIT
    from stock_read.indicators import session_of
    from stock_read.replay_read import bars as replay_bars

    return session_of(replay_bars(symbol, "1Min", STOCK_READ_BARS_LIMIT, now))


# -- reads of the trade --------------------------------------------------------------------
_short = exit_orders.short
_LEGS = exit_legs.LEGS


def _held(trade: dict[str, Any]) -> float:
    """The shares the trade's side still holds on the venue."""
    return orders.short_held_qty(trade["symbol"]) if _short(trade) else orders.held_qty(trade["symbol"])


# -- take the exit ------------------------------------------------------------------------
async def take(symbol: str, *, stop: Any, trail: bool = True, now: float | None = None, target: Any = None,
               target2: Any = None, target1_fraction: Any = None) -> dict[str, Any]:
    """Hand Nova the exit of every share the venue holds -- the cover, when it holds them short -- with its
    targets beside the stop when the sheet chose them (#681). Refusals: ``STOCK_MODE_LIVE`` / ``_REPLAY``,
    ``STOCK_MODE_HELD`` (Nova already has a trade on it), ``STOCK_MODE_NOTHING_HELD``, ``STOCK_MODE_INVALID``
    (a stop or target that would fill at once, a target past the stop, a target 2 not beyond target 1) and
    ``STOCK_MODE_SEND``."""
    from stock_mode import view
    from stock_mode.runner import clock, venue_day

    now = clock() if now is None else now
    sym = model.symbol(symbol)
    venue, replay = gates.venue_state()
    key = gates.replay_key()
    blocked = gates.venue_block(venue, replay, loaded=key is not None)
    if blocked is not None:
        code, why = blocked
        raise StockModeError(code, STOCK_MODE_WHY_LIVE_EXIT if code == STOCK_MODE_LIVE else why, field="sell")
    live = store.trade(venue, sym, key)
    if live and live.get("state") in (STOCK_MODE_TRADE_ENTERING, STOCK_MODE_TRADE_HOLDING)             and live.get("exits") == STOCK_MODE_SIDE_NOVA:
        raise StockModeError(STOCK_MODE_HELD, f"Nova already holds an order on {sym}: take it back first", field="sell")
    try:
        stop_px = float(stop)
    except (TypeError, ValueError) as exc:
        raise StockModeError(STOCK_MODE_INVALID, "the stop is a price", status=400, field="stop") from exc
    if not stop_px > 0:
        raise StockModeError(STOCK_MODE_INVALID, "the stop is a price over zero", status=400, field="stop")
    try:
        qty = orders.held_qty(sym)
        short = qty <= _EPS and orders.short_held_qty(sym) > _EPS
        if short:
            qty = orders.short_held_qty(sym)
        cost = avg_cost(sym, short)
    except orders.ReadError as exc:
        raise StockModeError(STOCK_MODE_NOTHING_HELD, f"Nova cannot read your {sym} position ({exc}): nothing was "
                             "placed", field="sell") from exc
    if qty <= _EPS:
        raise StockModeError(STOCK_MODE_NOTHING_HELD, f"The venue holds no {sym}: nothing to sell or cover")
    last = orders.last_price(sym)
    if last is not None and short and stop_px <= last + _EPS:
        raise StockModeError(STOCK_MODE_INVALID, f"The buy stop {stop_px:.2f} is at or under the last price "
                             f"{last:.2f}: it would cover at once. Cover it yourself, or set a higher stop.",
                             field="stop")
    if last is not None and not short and stop_px >= last - _EPS:
        raise StockModeError(STOCK_MODE_INVALID, f"The stop {stop_px:.2f} is at or over the last price {last:.2f}: "
                             "it would sell at once. Sell it yourself, or set a lower stop.", field="stop")
    t1, t2 = exit_targets.price(target, "target"), exit_targets.price(target2, "target2")
    refused = exit_targets.refusal(short, stop_px, last, t1, t2)
    if refused is not None:
        raise refused
    trade = {
        "kind": KIND_EXIT, "side": "short" if short else "long", "state": STOCK_MODE_TRADE_HOLDING, "venue": venue,
        "venue_day": venue_day(now),
        "symbol": sym, "setup_id": None, "setup_type": None, "attempt": f"{int(now * 1000)}", "qty": int(qty),
        "entry": cost, "stop": round(stop_px, 4), "trail": bool(trail), "raised": [],
        "trail_checked_at": None, "entry_order_id": None, "target_order_id": None, "target2_order_id": None,
        "stop_order_id": None, "halves": [],
        "sent_at": now, "ttl_sec": None, "cancel_sent_at": None, "fill_price": cost, "filled_at": now,
        "exit_price": None, "exit_reason": None, "closed_at": None, "exits": STOCK_MODE_SIDE_NOVA, "note": None,
        "replay_key": key,     # the Sim replay it was taken on (ADR 052 amendment), else None
    }
    exit_targets.apply(trade, t1, t2, target1_fraction)
    if t1 is None:
        receipt = await exit_orders.place_stop(trade, stop_px)
    else:
        receipt = await exit_orders.place_pair(trade, stop_px)
    if not getattr(receipt, "ok", False):
        what = "The stop and its targets were" if t1 is not None else "The stop was"
        raise StockModeError(STOCK_MODE_SEND, f"{what} not placed: {orders.receipt_error(receipt)}")
    trade.update(stop_order_id=exit_orders.order_id(receipt, "stop_order_id") or exit_orders.order_id(receipt),
                 target_order_id=exit_orders.order_id(receipt, "target_order_id"),
                 target2_order_id=exit_orders.order_id(receipt, "target2_order_id"))
    store.set_trade(trade)
    what, stop_word = ("the cover", "buy stop") if short else ("the exit", "stop")
    moving = (", lowered" if short else ", raised") + " as round numbers break" if trail else ""
    aims = f"; {exit_targets.words(trade)}" if t1 is not None else ""
    store.note_event(sym, now, "info", f"Nova took {what}: {stop_word} {stop_px:.2f}{moving}{aims}")
    audit(action=STOCK_MODE_AUDIT_ACTION, outcome="sent",
          reason=f"{sym}: Nova took {what} of {int(qty)} shares -- {stop_word} {stop_px:.2f}{moving}{aims}",
          inputs=_summary(trade))
    return view.build(sym, now=now)


async def take_back(trade: dict[str, Any], now: float) -> None:
    """Cancel Nova's stop and targets; the exit is yours again (``handed``). A refused cancel keeps the trade."""
    sym = trade["symbol"]
    refused = []
    for leg in exit_legs.resting(trade):
        receipt = await orders.cancel(trade, int(trade[leg]), source="manual")
        if getattr(receipt, "ok", False):
            trade[leg] = None
        else:
            refused.append(f"the {leg.split('_')[0]} ({orders.receipt_error(receipt)})")
    if refused:
        store.set_trade(trade)
        raise StockModeError(STOCK_MODE_SEND, f"{', '.join(refused)} could not be cancelled and still rests: Nova "
                             "keeps the exit -- try again, or flatten")
    trade.update(state=STOCK_MODE_TRADE_HANDED, exits=STOCK_MODE_SIDE_YOU, closed_at=now,
                 note="you took the exit back", exit_reason="handed")
    store.set_trade(trade)
    store.note_event(sym, now, "info", "You took the exit back: Nova's stop was cancelled")
    audit(action=STOCK_MODE_AUDIT_ACTION, outcome="handed", reason=f"{sym}: you took the exit back",
          inputs=_summary(trade))


# -- the runner's tick ----------------------------------------------------------------------
async def manage(trade: dict[str, Any], now: float) -> None:
    """One tick: the stop's fill -- or the target that sold the last shares -- closes the trade, a first half
    that filled is booked (the stop rests on for the rest, shrunk at the broker), a gone position or stop
    hands it back, and ``trail`` moves the stop (up under a long, down over a short)."""
    sold_now, done = exit_legs.book_fills(trade, now)
    for name, sold, price, left in sold_now:
        _half(trade, now, name, sold, price, left)
    if done is not None:
        await _close(trade, now, *done)
        return
    if _held(trade) <= _EPS:
        await _close(trade, now, "outside", None)
        return
    stop_row = orders.order_row(trade.get("stop_order_id"))
    if orders.order_state(stop_row) in ("dead", "gone"):
        await _hand_back(trade, now, "Nova's stop was cancelled outside Nova (the ticket, KILL or a reset): the exit "
                         "is yours again")
        return
    if trade.get("trail"):
        await _trail(trade, now)


async def _trail(trade: dict[str, Any], now: float) -> None:
    """Once per closed minute: raise the stop to the round a candle closed over since the trade began --
    for a short, lower the buy stop to the round a candle closed under."""
    from stock_read import held, held_short, rounds

    minute = int(now // MIN) * MIN
    if trade.get("trail_checked_at") is not None and float(trade["trail_checked_at"]) >= minute:
        return
    trade["trail_checked_at"] = minute
    sym = trade["symbol"]
    last = orders.last_price(sym)
    try:
        bars = (_closed_replay_bars if trade.get("replay_key") else _closed_bars)(sym, now)
    except Exception:
        logger.warning("stock mode: %s's 1-minute bars could not be read -- no raise this minute", sym, exc_info=True)
        store.set_trade(trade)
        return
    rnd = rounds.of(last)
    side = held_short if _short(trade) else held
    broke, _through = side.crosses(bars, rnd, float(trade["sent_at"]), last)
    move = (held_short.lower_for if _short(trade) else held.raise_for)(broke, rnd, float(trade["stop"]), last)
    if move is None:
        store.set_trade(trade)
        return
    receipt = await exit_orders.replace_stop(trade, move["to"])     # the stop alone: the targets stay as they are
    if not getattr(receipt, "ok", False):
        logger.warning("stock mode: moving %s's stop to %.2f was refused -- %s", sym, move["to"],
                       orders.receipt_error(receipt))
        store.set_trade(trade)
        return
    was = float(trade["stop"])
    trade["stop"] = move["to"]
    trade.setdefault("raised", []).append({"at": now, "from": was, "to": move["to"], "round": move["round"]})
    store.set_trade(trade)
    verb, stop_word, where, outcome = (("lowered", "buy stop", "under", "lowered") if _short(trade)
                                       else ("raised", "stop", "over", "raised"))
    store.note_event(sym, now, "ok", f"Nova {verb} the {stop_word} {was:.2f} -> {move['to']:.2f}: a candle closed "
                                     f"{where} ${move['round']:.2f}")
    audit(action=STOCK_MODE_AUDIT_ACTION, outcome=outcome,
          reason=f"{sym}: {stop_word} {was:.2f} -> {move['to']:.2f}, a candle closed {where} ${move['round']:.2f}",
          inputs=_summary(trade))


async def _cancel_rest(trade: dict[str, Any], keep: str | None = None) -> list[str]:
    """Cancel the legs still resting (all but ``keep``); the reasons any cancel was refused."""
    refused = []
    for leg, _reason, _name in _LEGS:
        if leg == keep or not trade.get(leg):
            continue
        row = orders.order_row(trade[leg])
        if orders.order_state(row) != "working":
            continue
        receipt = await orders.cancel(trade, int(trade[leg]), source="manual")
        if not getattr(receipt, "ok", False):
            refused.append(f"the {leg.split('_')[0]} ({orders.receipt_error(receipt)})")
    return refused


def _half(trade: dict[str, Any], now: float, name: str, sold: float, price: float, left: float) -> None:
    """The first half sold (a short: covered) at its target; the stop stays where it is for the rest."""
    sym = trade["symbol"]
    store.set_trade(trade)
    verb, stop_word = ("covered", "buy stop") if _short(trade) else ("sold", "stop")
    said = (f"Nova {verb} {sold:g} at {name.replace('target', 'target ')} {price:.2f}; the {stop_word} "
            f"{float(trade['stop']):.2f} stays for the other {left:g}")
    store.note_event(sym, now, "ok", said)
    audit(action=STOCK_MODE_AUDIT_ACTION, outcome="half", reason=f"{sym}: {said}", inputs=_summary(trade))


async def _close(trade: dict[str, Any], now: float, reason: str, price: float | None) -> None:
    """The trade is done: the legs still resting are cancelled, and the money counts every share sold
    (``halves.result``); a position closed outside Nova sold its rest at a price Nova does not know."""
    sym = trade["symbol"]
    refused = await _cancel_rest(trade)
    left = float(trade["qty"]) - halves.sold(trade)
    if reason not in ("stop", "target") and left > _EPS:
        halves.book(trade, reason, left, price, now)
    exit_price, _r, pnl = halves.result(trade, trade.get("fill_price"))
    trade.update(state=STOCK_MODE_TRADE_CLOSED, exit_reason=reason, exit_price=exit_price, closed_at=now,
                 note=f"{', '.join(refused)} could not be cancelled -- check the Trader" if refused else None)
    store.set_trade(trade)
    last = (halves.rows(trade) or [{}])[-1].get("leg")
    target = trade.get("target2") if last == "target2" else trade.get("target")
    said = {"stop": f"Nova's {'buy stop' if _short(trade) else 'stop'} {float(trade['stop']):.2f} filled",
            "target": f"Nova's target {'2 ' if last == 'target2' else ''}{float(target or 0):.2f} filled",
            "outside": "the position was closed"}.get(reason, reason)
    parts = f" ({halves.words(trade)})" if len(halves.rows(trade)) > 1 else ""
    money = f" · {'+' if pnl >= 0 else '-'}${abs(pnl):.2f}" if pnl is not None else ""
    tone = "ok" if reason == "target" else ("bad" if reason == "stop" else "info")
    store.note_event(sym, now, tone, f"Closed: {said}" + (f" at {price:.2f}" if price is not None else "")
                     + parts + money)
    audit(action=STOCK_MODE_AUDIT_ACTION, outcome="closed", reason=f"{sym}: {said}{parts}{money}",
          inputs=_summary(trade))


async def _hand_back(trade: dict[str, Any], now: float, why: str) -> None:
    refused = await _cancel_rest(trade)
    trade.update(state=STOCK_MODE_TRADE_HANDED, exits=STOCK_MODE_SIDE_YOU, closed_at=now, exit_reason="handed",
                 note=why + (f"; {', '.join(refused)} could not be cancelled" if refused else ""))
    store.set_trade(trade)
    store.note_event(trade["symbol"], now, "warn", why)
    audit(action=STOCK_MODE_AUDIT_ACTION, outcome="handed", reason=f"{trade['symbol']}: {why}", inputs=_summary(trade))


def _summary(trade: dict[str, Any]) -> dict[str, Any]:
    keys = ("symbol", "kind", "side", "venue", "qty", "entry", "stop", "target", "trail", "stop_order_id",
            "target_order_id", "exit_price", "exit_reason", "raised",
            "target2", "target1_qty", "target2_qty", "target2_order_id", "halves")
    return {k: trade.get(k) for k in keys}
