"""Claude's seat, twice a second (ADR 068 decisions 2, 3, 8, 9, 11). Registered as ``agent_trader`` in
``app_runtime_tasks``.

Each pass, in order:
1. **15:55 ET** -- Claude's shares are sold and its orders cancelled on Paper, seat on or off (the day cover's
   time); **16:00 ET** the seat turns off.
2. **A lapsed lease** -- no check-in for ``AGENT_LEASE_SEC``: the same close, then the seat off and its line freed.
3. **The line** -- while the seat reserves one and names a stock, take it if a depth line is free; with all 3 held,
   an auto-record line is given up for it first (``room``, never the operator's); a seat given up or off lets its
   lines go.
4. **Breaks** -- a resting break whose trigger a print reached sends its bracket at the break's top price, after
   its confirm (buyers leading, ``reflexes.confirmed``) and Claude's limits are checked again; one past its time is
   dropped.
5. **Reflexes** -- each armed reflex on the seat's stock is judged on the live book and the last prints; one that
   holds does its action at once (``reflexes``).
6. **Fills** -- every new fill of Claude's is said once (an event the desk toasts and speaks).
7. **The guard** -- while Claude holds shares, Nova sells them the moment sellers lead, the bids leave or the bid
   falls under entry (``guard``, decision 13), and a pop exit's stop moves to entry once its first half sells.
8. **The eye** -- while the seat is on, every symbol the scanner follows is scanned once a second, so a spike between
   Claude's looks is still listed (``eye``).
Every outcome is an event the desk shows.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any

from agent_trader import clock, guard_pass
from agent_trader.constants_agent_trader import (
    AGENT_CLOSE_ET,
    AGENT_OFF_ET,
    AGENT_TICK_SEC,
    AGENT_WAKE_MIN_SEC,
)

logger = logging.getLogger(__name__)

_line_why: str | None = None
_cursor: dict[str, float] = {}
_closed_day: str | None = None
_primed: set[str] = set()              # bid_pulled reflexes that have seen the size they guard
_waited: dict[str, float] = {}         # break id -> when "buyers do not lead" was last said
_seen_fills: set[int] | None = None    # Claude's fills already said (None until the first pass reads them)
_pass_lock = asyncio.Lock()


def reset_for_tests() -> None:
    global _line_why, _closed_day, _seen_fills
    _line_why, _closed_day, _seen_fills = None, None, None
    _cursor.clear()
    _primed.clear()
    _waited.clear()


def line_why() -> str | None:
    """Why the seat has no line yet (the depth door's words), or None."""
    return _line_why


def _et(t: float) -> datetime:
    from market import ET

    return datetime.fromtimestamp(t, tz=ET)


async def end_seat(reason: str, now: float | None = None) -> list[str]:
    """Cancel Claude's orders, sell its shares, turn the seat off and free its line; return what failed."""
    from agent_trader import lines, orders, seat

    _note_exits("stand_down", reason)
    problems = await orders.stand_down(reason)
    seat.turn_off(reason if not problems else f"{reason} (not everything closed: {'; '.join(problems)})", now)
    await lines.release(at_once=True)
    _cursor.clear()
    return problems


def _note_exits(reason: str, detail: str) -> None:
    """Tell the journal why every stock Claude holds is about to be sold."""
    from agent_trader import journal, ledger

    try:
        for sym in ledger.positions():
            journal.note_exit(sym, reason, detail)
    except ledger.ReadError:
        logger.warning("AGENT journal: Paper could not be read before %s", reason, exc_info=True)


async def _day_close(t: float) -> None:
    global _closed_day
    from agent_trader import ledger, orders, seat
    from market import session_key_for_ts

    day = session_key_for_ts(t)
    if _closed_day == day:
        return
    try:
        busy = bool(ledger.working() or ledger.positions())
    except ledger.ReadError as exc:
        logger.warning("AGENT 15:55: Paper could not be read (%s); trying again", exc)
        return
    if busy:
        _note_exits("day_close", "15:55 ET: Nova sells Claude's shares (the day cover's time)")
        problems = await orders.stand_down("15:55 ET")
        seat.event("day_close", "15:55 ET: Nova sold Claude's shares and cancelled its orders" +
                   (f" (not everything closed: {'; '.join(problems)})" if problems else ""), t)
        if problems:
            return  # tried again next pass
    for row in seat.breaks():
        seat.drop_break(row["id"], None, t)
    _closed_day = day


async def _line(t: float) -> None:
    global _line_why
    from agent_trader import lines, seat

    sym = seat.symbol()
    if not seat.reserves_line() or not sym:
        _line_why = None
        if lines.held_symbol() and (not seat.is_on() or seat.is_yielded()):
            await lines.release(at_once=True)
        return
    if lines.holds_depth(sym) and lines.holds_tape(sym):
        _line_why = None
        return
    if not lines.holds_depth(sym):
        from agent_trader import room

        if taken := await room.make_room(sym, t):
            seat.event("line_taken", f"took {taken}'s auto-record line for {sym}: all 3 Level 2 lines were held", t)
    why = await lines.acquire(sym)
    if why != _line_why and why:
        seat.event("line_wait", f"waiting for a Level 2 line on {sym}: {why}", t)
    elif _line_why and not why:
        seat.event("line", f"holding Level 2 and Time & Sales on {sym}", t)
    _line_why = why


async def _recent_prints(symbol: str, t: float) -> list[dict[str, Any]]:
    """The stock's prints in the last ``reflexes.SECONDS_MAX`` seconds (with bid / ask): the live ring when it reaches
    back that far (``wake``), else Nova's tape archive."""
    from agent_trader import reflexes, wake
    from l2 import tape

    live = wake.prints(symbol, t - reflexes.SECONDS_MAX)
    if live is not None:
        return live
    try:
        return await asyncio.to_thread(tape.get_trades_in_range, symbol, t - reflexes.SECONDS_MAX, t)
    except Exception:
        logger.warning("AGENT watcher: %s's prints could not be read; judged on none", symbol, exc_info=True)
        return []


async def _breaks(t: float) -> None:
    from agent_trader import orders, reflexes, rules, seat, wake
    from practice.reference import LiveReference

    rows = seat.breaks()
    if not rows:
        return
    ref = LiveReference()
    for row in rows:
        bid = row["id"]
        if t >= float(row["expires_at"]):
            seat.drop_break(bid, f"break on {row['symbol']} at {row['trigger']:g} expired untouched", t)
            _cursor.pop(bid, None)
            continue
        after = _cursor.get(bid, float(row["created_at"]))
        prints = await asyncio.to_thread(ref.prints_between, row["symbol"], after, t)
        prints = sorted({*prints, *wake.price_prints(row["symbol"], after)})
        if prints:
            _cursor[bid] = prints[-1][0]
        if not any(px >= float(row["trigger"]) for _, px in prints):
            continue
        if row.get("confirm"):
            ok, words = reflexes.confirmed(row["confirm"], await _recent_prints(row["symbol"], t), t)
            if not ok:
                if t - _waited.get(bid, 0.0) >= 30.0:
                    seat.event("break_wait", f"break on {row['symbol']} reached {row['trigger']:g}, but buyers do not "
                               f"lead ({words}): still waiting", t)
                    _waited[bid] = t
                continue
        order = {**row, "entry": row["top"]}
        if refused := rules.entry_refusal(order):
            seat.drop_break(bid, f"break on {row['symbol']} reached {row['trigger']:g} but was not sent: {refused[1]}", t)
            _cursor.pop(bid, None)
            continue
        receipt = await orders.send_entry(order, tag=f"break:{bid}")
        why = orders.receipt_error(receipt)
        text = (f"break on {row['symbol']} reached {row['trigger']:g}: sent buy {row['qty']:g} up to {row['top']:g}, "
                f"stop {row['stop']:g}" if not why else
                f"break on {row['symbol']} reached {row['trigger']:g} but the door refused it: {why}")
        seat.drop_break(bid, text, t)
        _cursor.pop(bid, None)


async def _reflexes(t: float) -> None:
    from agent_trader import ledger, reflexes, seat
    from ibkr import depth

    rows = seat.reflexes()
    if not rows:
        return
    sym = seat.symbol()
    try:
        held = ledger.positions()
        buying = {str(r["symbol"]).upper() for r in ledger.working()
                  if str(r.get("side") or "").upper() == "BUY" and r.get("leg_role") in (None, "parent")}
    except ledger.ReadError:
        logger.warning("AGENT reflexes: Paper could not be read; judged next pass", exc_info=True)
        return
    buying |= {str(b["symbol"]).upper() for b in seat.breaks()}
    book, prints = None, None
    for row in rows:
        rid, rsym = row["id"], str(row["symbol"]).upper()
        if t >= float(row["expires_at"]) or rsym != sym:
            seat.drop_reflex(rid, f"reflex on {rsym} ended: {reflexes.text(row)}", now=t)
            _primed.discard(rid)
            continue
        live = rsym in held if row["action"] == "sell_all" else rsym in buying
        if not live:
            continue                     # armed for later: shares to protect, or a buy to call off
        if book is None:
            book = depth.current_book(rsym)
        if row["kind"] in ("sellers", "last_below") and prints is None:
            prints = await _recent_prints(rsym, t)
        if rid not in _primed and reflexes.primes(row, book):
            _primed.add(rid)
        why = reflexes.fired(row, book=book, prints=prints or [], now=t, primed=rid in _primed)
        if why is None:
            continue
        if row["action"] == "sell_all":
            from agent_trader import journal

            journal.note_exit(rsym, "reflex", f"{reflexes.text(row)}: {why}")
        done = await _act(row, rsym, held.get(rsym, 0.0))
        seat.drop_reflex(rid, f"Reflex fired on {rsym}: {why} -- {done}", kind="reflex_fired", now=t)
        _primed.discard(rid)


async def _act(row: dict[str, Any], sym: str, qty: float) -> str:
    """Do a fired reflex's action; say what was done."""
    from agent_trader import ledger, orders, seat

    try:
        mine = [r for r in ledger.working() if str(r["symbol"]).upper() == sym]
    except ledger.ReadError:
        logger.warning("AGENT reflex: Paper could not be read before acting", exc_info=True)
        mine = []
    if row["action"] == "cancel_buy":
        for r in mine:
            if str(r.get("side") or "").upper() == "BUY" and r.get("leg_role") in (None, "parent"):
                await orders.cancel(int(r["order_id"]), sym)
        for b in seat.breaks():
            if str(b["symbol"]).upper() == sym:
                seat.drop_break(b["id"], None)
        return "Claude's buy was called off"
    for r in mine:
        await orders.cancel(int(r["order_id"]), sym)
    if qty <= 0:
        return "no shares were left to sell"
    receipt = await orders.close(sym, qty)
    why = orders.receipt_error(receipt)
    return f"sold {qty:g} {sym} at market" if not why else f"the sale was refused: {why}"


async def _fills(t: float) -> None:
    """Say each new fill of Claude's once: the desk toasts and speaks ``fill`` events."""
    global _seen_fills
    from agent_trader import ledger, seat

    try:
        rows = ledger.fills_today()
    except ledger.ReadError:
        return
    ids = {int(r["order_id"]) for r in rows}
    if _seen_fills is None:
        _seen_fills = ids                # a restart says nothing it said before
        return
    for r in rows:
        oid = int(r["order_id"])
        if oid in _seen_fills:
            continue
        _seen_fills.add(oid)
        side = "bought" if str(r.get("side") or "").upper() == "BUY" else "sold"
        how = {"target": " (target)", "target2": " (target)", "stop": " (stop)"}.get(str(r.get("leg_role") or ""), "")
        if not how and r.get("order_source") == "flatten":
            how = " (close)"
        seat.event("fill", f"Claude {side} {float(r.get('filled_qty') or 0):g} {r['symbol']} at "
                   f"{float(r.get('avg_fill_price') or 0):.2f}{how}", t)


async def run_pass(now: float | None = None) -> None:
    from agent_trader import seat

    t = clock.now() if now is None else now
    async with _pass_lock:
        et = _et(t)
        hm = (et.hour, et.minute)
        if et.weekday() < 5 and hm >= AGENT_CLOSE_ET:
            await _day_close(t)
        if seat.is_on() and (hm >= AGENT_OFF_ET or et.weekday() >= 5):
            await end_seat("the trading day ended", t)
            return
        if seat.is_on() and seat.lapsed(t):
            await end_seat("Claude went quiet for 10 minutes: Nova cancelled its orders, sold its shares and freed "
                           "its line", t)
            return
        await _line(t)
        if seat.is_on() and not seat.is_yielded():
            await _breaks(t)
        if seat.is_on():
            await _reflexes(t)
            try:
                await guard_pass.run(t)
            except Exception:
                logger.exception("AGENT guard: a pass failed; judged again next pass")
        await _fills(t)
        await _journal(t)
        if seat.is_on():
            await _eye(t)


async def _journal(t: float) -> None:
    from agent_trader import journal

    try:
        await journal.run(t)
    except Exception:
        logger.exception("AGENT journal: a pass failed; written next pass")


async def _eye(t: float) -> None:
    from agent_trader import eye

    if eye.scan_due(t):
        try:
            await asyncio.to_thread(eye.scan, t)
        except Exception:
            logger.exception("AGENT eye: a scan failed")


def _watch_set() -> set[str]:
    """The stocks whose prints and books wake the seat: its stock, its breaks' and the ones it holds shares in."""
    from agent_trader import ledger, seat

    if not seat.is_on():
        return set()
    out = {s for s in [seat.symbol(), *(b["symbol"] for b in seat.breaks())] if s}
    try:
        out |= set(ledger.positions())
    except ledger.ReadError:
        logger.warning("AGENT watcher: Paper could not be read for the wake set", exc_info=True)
    return {s.upper() for s in out}


async def run() -> None:
    """The runtime task: a pass every ``AGENT_TICK_SEC``, and at once on a print or book of a stock the seat watches
    (``wake``), never two at once and never closer than ``AGENT_WAKE_MIN_SEC``; a failed pass is logged and the next
    one runs."""
    from agent_trader import wake

    woken = wake.bind(asyncio.get_running_loop())
    while True:
        started = asyncio.get_running_loop().time()
        woken.clear()
        try:
            await run_pass()
            wake.watch(_watch_set())
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("AGENT watcher: a pass failed")
        try:
            await asyncio.wait_for(woken.wait(), AGENT_TICK_SEC)
        except asyncio.TimeoutError:  # maintainer: allow-swallow the tick ends the wait
            continue
        rest = AGENT_WAKE_MIN_SEC - (asyncio.get_running_loop().time() - started)
        if rest > 0:
            await asyncio.sleep(rest)


def describe() -> dict[str, Any]:
    return {"line_why": _line_why, "breaks_watched": len(_cursor), "closed_day": _closed_day}
