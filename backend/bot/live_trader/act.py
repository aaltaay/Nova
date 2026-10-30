"""What the Live Trader watcher does with a decision, and with the orders it has in flight (ADR 055).

Every send goes through ``orders`` (the execution door), every step and skip is a ``live_trader`` line on the bot's
audit stream (``bot.audit``) and the stock's last event on its Trader tab (``stock_mode.store``), and the book
(``book``) follows: a step's order to its fill, its TTL or its refusal; a close to its fill or its next try; shares
that left Paper some other way -- the operator, the loss limit's Auto sell, a short's buy stop, Nova's day cover -- out of the
position, said once. A skip is written once per trade, step and code. Shapes: architecture/schema/bot.md.

maintainer: one-concern every order the Live Trader bot has in flight, followed to its end, and each line it writes
"""
from __future__ import annotations

import logging
from collections import OrderedDict
from typing import Any

from bot import fill_progress
from bot.live_trader import book, market, orders
from bot.live_trader.constants_live_trader import (
    LT_AUDIT_ACTION,
    LT_CLOSE_MAX_TRIES,
    LT_CLOSE_RETRY_SEC,
    LT_NOT_FILLED,
    LT_SKIPS_REMEMBERED,
    LT_VENUE,
    LT_WAIT_SEC,
)
from bot.live_trader.rules import price_text

logger = logging.getLogger(__name__)
EPS = 1e-9
STALE_BORROW = ("SHORT_STALE_BORROW", "SHORT_NO_BORROW", "SHORT_BORROW_UNKNOWN")

_written: OrderedDict[tuple, None] = OrderedDict()
_borrow_waits: dict[tuple, float] = {}               # a short step waiting on IBKR's borrow read: since when


def reset_for_tests() -> None:
    _written.clear()
    _borrow_waits.clear()


def _verb(side: str, close: bool = False) -> str:
    if close:
        return "covered" if side == "short" else "sold"
    return "shorted" if side == "short" else "bought"


def audit(outcome: str, a: dict[str, Any], *, why: str | None = None, now: float, **extra: Any) -> None:
    """One ``live_trader`` line on the bot's audit stream."""
    from bot.audit import record

    change = a.get("change") or {}
    late = round(now - change["ts"], 1) if change.get("ts") is not None else None
    inputs = {"host": a.get("host"), "row_id": a.get("row_id"), "symbol": a.get("symbol"), "side": a.get("side"),
              "step": a.get("step"), "qty": a.get("qty"), "limit": a.get("limit"), "stop": a.get("stop"),
              "code": a.get("code"), "why": why if why is not None else a.get("why"), "change": change or None,
              "late_sec": late, "venue": LT_VENUE, **extra}
    fill = inputs.pop("fill", None)
    try:
        record(action=LT_AUDIT_ACTION, outcome=outcome, reason=inputs["why"], order_id=extra.get("order_id"),
               inputs=inputs, fill=fill)
    except Exception:
        logger.exception("Live Trader bot: the audit line (%s %s) was not written", outcome, a.get("symbol"))


def tell(symbol: str | None, now: float, tone: str, text: str) -> None:
    """The bot's word on a stock is that stock's last event on its Trader tab."""
    if not symbol:
        return
    try:
        from stock_mode import store

        store.note_event(symbol.upper(), now, tone, text)
    except Exception:
        logger.warning("Live Trader bot: %s's last event was not noted", symbol, exc_info=True)


def once(*key: Any) -> bool:
    """True the first time ``key`` is seen (a skip is written once per trade, step and code)."""
    if key in _written:
        return False
    _written[key] = None
    while len(_written) > LT_SKIPS_REMEMBERED:
        _written.popitem(last=False)
    return True


# -- decisions -------------------------------------------------------------------------------------
def skip(a: dict[str, Any], now: float, **extra: Any) -> None:
    if not once(a.get("row_id"), a.get("step"), a.get("code")):
        return
    audit("skipped", a, now=now, **extra)
    tell(a.get("symbol"), now, "warn", f"Live Trader ({a.get('host')}): did not {_step_words(a)} -- {a.get('why')}")


def note(a: dict[str, Any], now: float, outcome: str = "note") -> None:
    if not once(a.get("row_id"), a.get("step"), a["kind"], (a.get("change") or {}).get("kind")):
        return
    audit(outcome, a, now=now)
    tell(a.get("symbol"), now, "info", f"Live Trader ({a.get('host')}): {a.get('why')}")


def _step_words(a: dict[str, Any]) -> str:
    sym, side = a.get("symbol"), a.get("side")
    if a.get("step") == "add":
        return f"add to {sym}"
    return f"{'short' if side == 'short' else 'buy'} {sym}"


async def step(a: dict[str, Any], now: float, *, short_blocks: Any) -> str | None:
    """Send one step; ``"wait"`` when a short's borrow is being read (the caller waits on it), else None."""
    if a["side"] == "short":
        found = short_blocks(a)
        waiting = (a["row_id"], a["step"], (a.get("change") or {}).get("ts"))     # one per add, too
        if found:
            code, why = found[0]
            began = _borrow_waits.setdefault(waiting, now)
            if code in STALE_BORROW and now - began < LT_WAIT_SEC:
                market.prewarm_borrow({a["symbol"]})
                return "wait"                      # IBKR's borrow is being read: the step (an add too) waits for it
            _borrow_waits.pop(waiting, None)
            skip({**a, "code": code, "why": why}, now)
            return None
        _borrow_waits.pop(waiting, None)
    held = book.get(a["pos_id"])
    n = (held["adds_followed"] + 1) if (held and a["step"] == "add") else ""
    try:
        receipt = await orders.send_step(a, n, now)
    except Exception as exc:
        logger.exception("Live Trader bot: the %s step on %s did not go out", a["step"], a["symbol"])
        audit("error", a, why=f"the order did not go out: {type(exc).__name__}: {exc}", now=now)
        return None
    if not receipt.ok:
        why = orders.receipt_error(receipt)
        audit("refused", a, why=f"refused: {why}", now=now, code=receipt.reason_code)
        tell(a["symbol"], now, "warn", f"Live Trader ({a['host']}): the {_step_words(a)} order was refused ({why})")
        return None
    order_id, stop_id = orders.receipt_ids(receipt)
    book.step_sent(a, order_id=order_id, stop_id=stop_id, now=now)
    stop = f", buy stop {price_text(a.get('stop'))}" if a.get("stop") else ""
    did = f"added (average {price_text(a['their_price'])})" if a["step"] == "add" else _change_words(a)
    said = (f"{'buy' if a['side'] == 'long' else 'short'} {a['qty']:g} {a['symbol']} at {price_text(a['limit'])}"
            f"{stop} -- {a['host']} {did}")
    audit("order", a, why=said, now=now, order_id=order_id, stop_order_id=stop_id, approved=a.get("approved"))
    tell(a["symbol"], now, "info", f"Live Trader ({a['host']}): {said}")
    follow_step(a["pos_id"], now)
    return None


def _change_words(a: dict[str, Any]) -> str:
    price = price_text((a.get("change") or {}).get("price"))
    if (a.get("change") or {}).get("kind") == "already_open":
        return f"already held it at {price} when watching began"
    return f"{_verb(a['side'])} it at {price}"


async def close(a: dict[str, Any], now: float) -> None:
    """Sell (or cover) the bot's whole position: its order in flight and a short's buy stops cancelled first.
    A trim (``a["trim"]``, a long only) sells ``a["qty"]`` of it, once: the host sold part (``decide_steps.trim``)."""
    pos = book.get(a["pos_id"])
    if pos is None or pos["state"] == "closing":
        return
    failed_at = (pos.get("close") or {}).get("failed_ts")
    if failed_at is not None and now - failed_at < LT_CLOSE_RETRY_SEC:
        return
    cover = market.cover_ts(now)
    if pos["side"] == "short" and cover is not None and now >= cover:
        book.close_sent(pos["id"], order_id=None, kind="day_cover", why=a["why"], now=now, qty=pos["qty"])
        note({**a, "kind": "day_cover", "why": f"{a['why']}: Nova's day cover covers every Paper short at this "
                                              "time, this one with them"}, now)
        return
    cancels = ([pos["order"]["id"]] if pos.get("order") and pos["order"].get("id") else []) + pos["stop_order_ids"]
    for oid in cancels:
        try:
            if orders.order_state(orders.order_row(oid)) == "working":
                await orders.cancel(oid, pos["symbol"], pos["host"])
        except orders.ReadError:
            logger.warning("Live Trader bot: order %s unreadable before the close of %s", oid, pos["symbol"])
    if pos.get("order"):
        follow_step(pos["id"], now)
        pos = book.get(a["pos_id"])
        if pos is None:
            return
    held = orders.held(pos["symbol"], pos["side"])
    if held is None:
        audit("error", a, why="Paper's positions could not be read: the close was not sent (tried again)", now=now)
        return
    qty = min(float(a["qty"]) if a.get("trim") else pos["qty"], held)
    if a.get("trim") and (pos["side"] != "long" or pos.get("trimmed") or qty >= pos["qty"] - EPS):
        return                                 # a trim is half a long, once: never a whole close, never a short
    if qty <= EPS:
        kind, how, price, oid = _left_how(pos, pos["qty"], now)
        done = book.reduce(pos["id"], pos["qty"], kind=kind, why=f"already gone from Paper before the close: {how}",
                           ts=now, price=price, order_id=oid)
        if done is not None:
            note({**a, "why": f"{a['why']}: the shares were already gone from Paper ({how})"}, now)
        return
    tries = int((pos.get("close") or {}).get("tries") or 0) + 1
    try:
        receipt = await orders.close(pos, qty, tries=tries, now=now)
    except Exception as exc:
        logger.exception("Live Trader bot: the close of %s did not go out", pos["symbol"])
        receipt, error = None, f"{type(exc).__name__}: {exc}"
    else:
        error = None if receipt.ok else orders.receipt_error(receipt)
    if error is not None:
        book.close_sent(pos["id"], order_id=None, kind=a["change"]["kind"], why=a["why"], now=now, qty=qty)
        n = book.close_failed(pos["id"], now=now, error=error)
        loud = n >= LT_CLOSE_MAX_TRIES
        audit("error" if loud else "refused", a, now=now, why=(
            f"the close of {qty:g} {pos['symbol']} was refused ({error})"
            + (f" {n} times -- close it yourself; Nova keeps trying every {LT_CLOSE_RETRY_SEC:.0f} s" if loud else
               f"; tried again in {LT_CLOSE_RETRY_SEC:.0f} s")))
        return
    order_id, _stop = orders.receipt_ids(receipt)
    book.close_sent(pos["id"], order_id=order_id, kind=a["change"]["kind"], why=a["why"], now=now, qty=qty)
    said = f"{'covered' if pos['side'] == 'short' else 'sold'} {qty:g} {pos['symbol']} -- {a['why']}"
    audit("closed", {**a, "qty": qty}, why=said, now=now, order_id=order_id)
    tell(pos["symbol"], now, "info", f"Live Trader ({pos['host']}): {said}")
    follow_close(pos["id"], now)


def rekey(a: dict[str, Any], now: float) -> None:
    book.rekey(a["pos_id"], a["row_id"])
    note({**a, "kind": "rekey", "step": "rekey",
          "why": a.get("why") or f"the feed reopened {a['host']}'s {a['symbol']}: the same position, nothing sent"},
         now)


def market_now(symbol: str) -> dict[str, Any] | None:
    """IBKR's last print and quote as the fill was read: what the report holds the fill against."""
    q = market.quote(symbol)
    if not q:
        return None
    return {"last": q.get("last"), "last_ts": q.get("last_ts"), "bid": q.get("bid"), "ask": q.get("ask")}


# -- orders in flight ------------------------------------------------------------------------------
def follow_step(pos_id: str, now: float, *, ttl: float | None = None) -> str | None:
    """The step in flight to its end: ``"cancel"`` when it has worked past ``ttl`` (the caller cancels it)."""
    pos = book.get(pos_id)
    if pos is None or not pos.get("order"):
        return None
    order = pos["order"]
    try:
        row = orders.order_row(order["id"])
    except orders.ReadError as exc:
        logger.warning("Live Trader bot: %s", exc)
        return None
    state = orders.order_state(row)
    a = {"host": pos["host"], "row_id": pos["row_id"], "symbol": pos["symbol"], "side": pos["side"],
         "step": order["step"], "qty": order["qty"], "limit": order["limit"], "change": order.get("change")}
    if state == "working":
        _partial(a, row, "entry", order["step"], order["id"], _verb(pos["side"]), now)
        return "cancel" if ttl is not None and now - order["sent_ts"] >= ttl else None
    fill_progress.forget(order["id"])
    filled = float((row or {}).get("filled_qty") or 0.0)
    price = (row or {}).get("avg_fill_price")
    book.step_done(pos_id, filled=filled, price=None if price is None else float(price),
                   ts=(row or {}).get("fill_ts"), basis=(row or {}).get("fill_basis"))
    if filled > EPS:
        audit("filled", a, now=now, order_id=order["id"], fill_price=price, fill_basis=(row or {}).get("fill_basis"),
              fill=fill_progress.block(row, phase="entry", leg=order["step"], order_id=order["id"]),
              fill_ts=(row or {}).get("fill_ts"), ibkr=market_now(pos["symbol"]),
              why=f"{_verb(pos['side'])} {filled:g} {pos['symbol']} at {price_text(price)}")
    elif state == "dead" and order.get("timed_out_ts") is not None and not (row or {}).get("error"):
        # A trade the bot meant to copy and did not: a skip on the card, never only a line in the log.
        skip({**a, "code": LT_NOT_FILLED, "why": _unfilled_words(pos["side"], order)}, now, order_id=order["id"])
    else:
        why = (row or {}).get("error") or ("not filled in time" if state == "dead" else "Paper has no such order")
        audit("note", a, now=now, order_id=order["id"], why=f"not filled: {why}")
    return None


def _unfilled_words(side: str, order: dict[str, Any]) -> str:
    worked = max(0.0, float(order["timed_out_ts"]) - float(order["sent_ts"]))
    what = "add" if order.get("step") == "add" else "short" if side == "short" else "buy"
    said = f"the {what} at {price_text(order.get('limit'))} was not taken in {worked:.0f} s"
    if side == "short" and order.get("ssr") == "on":
        return f"{said}: SSR is on, so a short may sell only above the bid"
    if side == "short" and order.get("ssr") == "unknown":
        return f"{said}: its SSR could not be read, so it was offered above the bid, as if SSR were on"
    return said


def follow_close(pos_id: str, now: float) -> None:
    pos = book.get(pos_id)
    close_ = (pos or {}).get("close") or {}
    if pos is None or pos["state"] != "closing" or close_.get("order_id") is None:
        return
    try:
        row = orders.order_row(close_["order_id"])
    except orders.ReadError as exc:
        logger.warning("Live Trader bot: %s", exc)
        return
    state = orders.order_state(row)
    a = {"host": pos["host"], "row_id": pos["row_id"], "symbol": pos["symbol"], "side": pos["side"], "step": "close",
         "change": {"kind": close_.get("kind"), "ts": close_.get("sent_ts"), "price": None}}
    if state == "working":
        _partial({**a, "qty": close_.get("qty")}, row, "exit", "close", close_["order_id"],
                 _verb(pos["side"], close=True), now)
        return
    fill_progress.forget(close_["order_id"])
    if state == "filled":
        price = (row or {}).get("avg_fill_price")
        qty = float((row or {}).get("filled_qty") or close_.get("qty") or 0.0)
        done = book.close_filled(pos_id, qty=qty, price=None if price is None else float(price),
                                 ts=(row or {}).get("fill_ts"), order_id=close_["order_id"],
                                 kind=close_.get("kind") or "close", why=close_.get("why") or "")
        pl = f" (P/L {done['pl_usd']:+.2f})" if done and done.get("pl_usd") is not None else ""
        audit("filled", {**a, "qty": qty}, now=now, order_id=close_["order_id"], fill_price=price,
              fill=fill_progress.block(row, phase="exit", leg="close", order_id=close_["order_id"]),
              fill_basis=(row or {}).get("fill_basis"), fill_ts=(row or {}).get("fill_ts"),
              ibkr=market_now(pos["symbol"]),
              why=f"{_verb(pos['side'], close=True)} {qty:g} {pos['symbol']} at {price_text(price)}{pl}")
        return
    error = (row or {}).get("error") or "Paper has no such order"
    book.close_failed(pos_id, now=now, error=error)
    audit("refused", a, now=now, order_id=close_["order_id"],
          why=f"the close did not fill ({error}); tried again in {LT_CLOSE_RETRY_SEC:.0f} s")


def _partial(a: dict[str, Any], row: dict[str, Any] | None, phase: str, leg: str, order_id: Any, verb: str,
             now: float) -> None:
    """A working step or close that filled more shares: a ``partial`` line (operator ask 2026-10-16)."""
    fill = fill_progress.partial(row, phase=phase, leg=leg, order_id=order_id)
    if fill is not None:
        audit("partial", a, now=now, order_id=order_id, fill=fill,
              why=fill_progress.words(fill, a.get("symbol") or "", verb))


async def reconcile(now: float) -> None:
    """Shares the bot holds that Paper no longer holds -- sold by the operator, the loss limit's Auto sell or KILL, a short's buy
    stop, Nova's day cover -- leave the position (the newest first), said once. A short that lost shares that way
    has its buy stops retired (``_retire_stops``)."""
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    retire: list[tuple[dict[str, Any], str]] = []
    for pos in book.positions().values():
        waiting_cover = pos["state"] == "closing" and (pos.get("close") or {}).get("order_id") is None
        if pos.get("order") or (pos["state"] == "closing" and not waiting_cover) or pos["qty"] <= EPS:
            continue
        groups.setdefault((pos["symbol"], pos["side"]), []).append(pos)
    for (symbol, side), held_by_bot in groups.items():
        held = orders.held(symbol, side)
        if held is None:
            continue
        excess = sum(p["qty"] for p in held_by_bot) - held
        for pos in sorted(held_by_bot, key=lambda p: p.get("opened_ts") or 0, reverse=True):
            if excess <= EPS:
                break
            take = min(pos["qty"], excess)
            excess -= take
            kind, why, price, oid = _left_how(pos, take, now)
            book.reduce(pos["id"], take, kind=kind, why=why, ts=now, price=price, order_id=oid)
            note({"kind": "reconcile", "host": pos["host"], "row_id": pos["row_id"], "symbol": symbol, "side": side,
                  "step": kind, "qty": take, "why": f"{take:g} of the bot's {symbol} left Paper: {why}"}, now)
            if side == "short" and pos["stop_order_ids"]:
                retire.append((pos, why))
    for pos, why in retire:
        await _retire_stops(pos, why, now)


async def _retire_stops(pos: dict[str, Any], why: str, now: float) -> None:
    """A short's buy stops were sized for what it held: once shares leave it some other way they no longer match.
    What the bot still holds of it is covered; once it holds nothing, its stops wait on ``book.retiring`` until
    Paper shows them cancelled (``clear_stops``) -- a stale stop never covers a later short (review, PR #981)."""
    left = book.get(pos["id"])
    if left is not None and left["qty"] > EPS:
        await close({"kind": "close", "host": pos["host"], "pos_id": pos["id"], "row_id": pos["row_id"],
                     "symbol": pos["symbol"], "side": "short", "qty": left["qty"],
                     "why": f"{why}: its buy stop no longer matches what it holds, so the bot covers the rest",
                     "change": {"kind": "outside", "ts": now, "price": None}}, now)


async def clear_stops(now: float) -> None:
    """Every buy stop of a position that holds nothing any more is cancelled until Paper shows it is not working.
    A cancel refused or not read stays on the list (persisted: a restart keeps it) and is tried again next pass,
    said once on the card -- a stale stop never buys past flat or covers a later short (review, PR #982)."""
    for r in book.retiring():
        oid, a = r["order_id"], {"host": r.get("host"), "symbol": r.get("symbol"), "side": "short", "step": "stop"}
        try:
            state = orders.order_state(orders.order_row(oid))
            if state == "working":
                receipt = await orders.cancel(oid, r["symbol"], r["host"])
                if receipt is None or not receipt.ok:
                    _stop_left(a, oid, f"its cancel was refused ({orders.receipt_error(receipt)})", now)
                    continue
                state = orders.order_state(orders.order_row(oid))
        except orders.ReadError as exc:
            _stop_left(a, oid, f"Paper could not be read ({exc})", now)
            continue
        except Exception as exc:
            logger.exception("Live Trader bot: %s's buy stop %s was not cancelled", r.get("symbol"), oid)
            _stop_left(a, oid, f"{type(exc).__name__}: {exc}", now)
            continue
        if state == "working":
            _stop_left(a, oid, "Paper still lists it working after the cancel", now)
            continue
        book.retired(oid)


def _stop_left(a: dict[str, Any], oid: int, why: str, now: float) -> None:
    logger.warning("Live Trader bot: %s's buy stop %s is still working: %s -- tried again next pass",
                   a.get("symbol"), oid, why)
    if once("stop_left", oid, why):
        audit("error", a, now=now, order_id=oid,
              why=f"the buy stop {oid} on {a.get('symbol')} is still working ({why}): the bot holds none of it, "
                  "so Nova cancels it every pass until Paper shows it gone -- cancel it yourself if it stays")


def _left_how(pos: dict[str, Any], take: float, now: float) -> tuple[str, str, float | None, int | None]:
    """``(kind, why, price, order_id)`` for ``take`` shares that left ``pos`` some other way. The price is Paper's
    own fill, so the card's P/L counts the position (before 2026-10-30 a day cover or a sale outside the bot booked
    it with no price, $0 on the card)."""
    for oid in pos["stop_order_ids"]:
        try:
            row = orders.order_row(oid)
        except orders.ReadError:
            continue
        if orders.order_state(row) == "filled":
            price = (row or {}).get("avg_fill_price")
            return "stop", f"its buy stop filled at {price_text(price)}", price, oid
    if (pos.get("close") or {}).get("kind") == "day_cover":
        kind, why = "day_cover", "Nova's day cover covered it"
    else:
        kind, why = "outside", "sold outside the bot (by you, the loss limit or KILL)"
    price, oid = _outside_fill(pos, take)
    if kind != "day_cover":
        oid = None               # your order (or KILL's) is not the bot's: priced, but its fee stays off the card
    return kind, (why if price is None else f"{why} at {price_text(price)}"), price, oid


def _outside_fill(pos: dict[str, Any], take: float) -> tuple[float | None, int | None]:
    """What Paper got for ``take`` of the position's shares: the closing fills of its stock and side since the
    position's own last fill, none the bot's (``orders.closed_by_others``), the newest first, averaged over the
    shares. The order's id only when one order closed exactly these shares (the day cover's then counts on the card
    as the bot's close). ``(None, None)`` when Paper cannot be read or shows fewer closing shares: the P/L stays
    unknown, never a guess."""
    mine = [*(pos.get("fills") or ()), *(pos.get("exit_fills") or ())]
    own = {int(f["order_id"]) for f in mine if f.get("order_id") is not None}
    since = max((float(f["ts"]) for f in mine if f.get("ts") is not None), default=float(pos.get("opened_ts") or 0.0))
    try:
        rows = orders.closed_by_others(pos["symbol"], pos["side"], since, not_ids=own)
    except orders.ReadError as exc:
        logger.warning("Live Trader bot: %s", exc)
        return None, None
    left, got, used = float(take), 0.0, []
    for r in rows:
        qty = min(left, float(r.get("filled_qty") or 0.0))
        if qty <= EPS or r.get("avg_fill_price") is None:
            continue
        got += qty * float(r["avg_fill_price"])
        left -= qty
        used.append(r)
        if left <= EPS:
            break
    if left > EPS or not used:
        return None, None
    alone = len(used) == 1 and abs(float(used[0].get("filled_qty") or 0.0) - float(take)) <= EPS
    return round(got / float(take), 4), (int(used[0]["order_id"]) if alone else None)
