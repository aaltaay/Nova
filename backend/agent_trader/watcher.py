"""Claude's seat, once a second (ADR 068 decisions 2, 3, 8, 9). Registered as ``agent_trader`` in
``app_runtime_tasks``.

Each pass, in order:
1. **15:55 ET** -- Claude's shares are sold and its orders cancelled on Paper, seat on or off (the day cover's
   time); **16:00 ET** the seat turns off.
2. **A lapsed lease** -- no check-in for ``AGENT_LEASE_SEC``: the same close, then the seat off and its line freed.
3. **The line** -- while the seat reserves one and names a stock, take it if a depth line is free (never from the
   operator); a seat given up or off lets its lines go.
4. **Breaks** -- a resting break whose trigger a print reached sends its bracket at the break's top price, after
   Claude's limits are checked again; one past its time is dropped. Every outcome is an event the desk shows.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any

from agent_trader import clock
from agent_trader.constants_agent_trader import AGENT_CLOSE_ET, AGENT_OFF_ET, AGENT_TICK_SEC

logger = logging.getLogger(__name__)

_line_why: str | None = None
_cursor: dict[str, float] = {}
_closed_day: str | None = None
_pass_lock = asyncio.Lock()


def reset_for_tests() -> None:
    global _line_why, _closed_day
    _line_why, _closed_day = None, None
    _cursor.clear()


def line_why() -> str | None:
    """Why the seat has no line yet (the depth door's words), or None."""
    return _line_why


def _et(t: float) -> datetime:
    from market import ET

    return datetime.fromtimestamp(t, tz=ET)


async def end_seat(reason: str, now: float | None = None) -> list[str]:
    """Cancel Claude's orders, sell its shares, turn the seat off and free its line; return what failed."""
    from agent_trader import lines, orders, seat

    problems = await orders.stand_down(reason)
    seat.turn_off(reason if not problems else f"{reason} (not everything closed: {'; '.join(problems)})", now)
    await lines.release(at_once=True)
    _cursor.clear()
    return problems


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
    why = await lines.acquire(sym)
    if why != _line_why and why:
        seat.event("line_wait", f"waiting for a Level 2 line on {sym}: {why}", t)
    elif _line_why and not why:
        seat.event("line", f"holding Level 2 and Time & Sales on {sym}", t)
    _line_why = why


async def _breaks(t: float) -> None:
    from agent_trader import orders, rules, seat
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
        if prints:
            _cursor[bid] = prints[-1][0]
        if not any(px >= float(row["trigger"]) for _, px in prints):
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


async def run() -> None:
    """The runtime task: one pass a second, never two at once; a failed pass is logged and the next one runs."""
    while True:
        try:
            await run_pass()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("AGENT watcher: a pass failed")
        await asyncio.sleep(AGENT_TICK_SEC)


def describe() -> dict[str, Any]:
    return {"line_why": _line_why, "breaks_watched": len(_cursor), "closed_day": _closed_day}
