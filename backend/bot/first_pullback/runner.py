"""Nova's own bot's loop and its trade (ADR 030; every setup at Strategy since ADR 042).

Every ``BOT_FP_POLL_SEC``:

1. **Never Live.** An active bot on Live (a session from another build, a venue that
   could not be read) is deactivated, on the timeline.
2. **Playing?** The master at Strategy, Activate on, a setup at effective Strategy, on
   Paper or Sim at its live edge. While it plays, the bot holds the L2 session as brain
   ``nova-first-pullback`` (the id kept from ADR 030, so a running session keeps its
   claim) and heartbeats; when it stops playing it lets go.
3. **Triggers** the setup scanner announced (``submit``) on this venue's bot stocks are
   traded -- the first go trigger wins, one trade at a time, then the shared daily cap
   (``admit.for_bot``: every rule) -- or skipped with every reason, on the timeline and as
   the stock's last event (``stock_mode``). Triggers on other stocks are Auto-entry's or
   the scanner's own record.
4. **The trade** on is managed. The entry is a practice bracket: a BUY limit at the entry,
   a SELL limit at target 1 and a SELL stop at the stop, the exits resting at the broker
   once the entry fills -- so Paper's exits fill while the desk shows another venue. The
   entry fills, or is cancelled (its exits with it) after the sleeve's working TTL (a
   miss). The time stop, the template's flush exit (``flush.py``: a tightened stop is a
   replace of the stop leg) and a stop leg that is gone (the bot then watches the stop on
   the last price) cancel both legs and sell at the bid; a close that cannot be sent or
   does not fill ends in the protective flatten. The bot manages its trade until the
   position is closed, whatever the level or Activate say: Deactivate stops new entries only.

Owner: the ``trade`` key of the bot session (``bot.persist``); a restart resumes managing
it. States: ``entering`` -> ``open`` -> ``exiting`` -> ``closed``, or ``entering`` ->
``missed``, or ``open`` -> ``handed`` when the operator takes over the exit
(``handover.hand_over``, ADR 037).

maintainer: one-concern the bot's trade state machine and the loop that drives it
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from typing import Any, Callable

from bot.arming import is_desk_active
from bot.audit import record as audit
from bot.errors import BotError
from bot.first_pullback import admit, flush, orders
# The operator takes over the exit, and the desk leaves a venue (ADR 037, 042): re-exported.
from bot.first_pullback.handover import hand_over, leave_venue
from bot.persist import load_session, save_session
from constants_bot import (
    BOT_AUDIT_ACTION_TRADE,
    BOT_FP_CANCEL_WAIT_SEC,
    BOT_FP_CLOSE_ATTEMPTS,
    BOT_FP_HEARTBEAT_SEC,
    BOT_FP_POLL_SEC,
    BOT_FP_TIME_STOP_MIN,
    BOT_KIND_SETUP_ENTRY,
    BOT_LEVEL_STRATEGY,
    BOT_RUNNER_BRAIN_ID,
    BOT_SETUP_FIRST_PULLBACK,
)

logger = logging.getLogger(__name__)

LIVE_STATES = admit.LIVE_STATES
_EPS = 1e-9
_inbox: deque[dict[str, Any]] = deque(maxlen=50)
_clock: Callable[[], float] = time.time
_last_beat = 0.0
_warned: set[str] = set()


def submit(event: dict[str, Any]) -> None:
    """The setup scanner's trigger listener: enqueue only (it runs on the scanner's tick)."""
    _inbox.append(event)


def label(setup: str | None) -> str:
    return admit.name(setup)


# -- is the bot playing? --------------------------------------------------------
def playing(row: dict[str, Any], venue: tuple[str | None, bool, bool] | None = None) -> tuple[bool, str | None]:
    """Whether the bot plays now, and when not, why (the Bots page says it)."""
    from bot import activation
    from bot.setup_levels import at_strategy

    if int(row.get("level") or 0) < BOT_LEVEL_STRATEGY:
        return False, "the master level is not Strategy"
    if not is_desk_active(row):
        return False, "the bot is not active: turn the Bot switch on"
    if not at_strategy(row):
        return False, "no setup is at Strategy"
    blocked = activation.venue_block(*(venue or activation.venue_state()))
    if blocked is not None:
        return False, blocked[1]
    return True, None


def status(row: dict[str, Any]) -> dict[str, Any]:
    on, why = playing(row)
    held = (row.get("brain_session_id") or "").strip()
    if on and held and held != BOT_RUNNER_BRAIN_ID:
        on, why = False, f"another bot ({held}) holds Strategy"
    return {"brain_id": BOT_RUNNER_BRAIN_ID, "playing": on, "reason": why}


def waiting_text(trade: dict[str, Any], venue: str | None) -> str | None:
    """What a live trade on another venue than the desk's waits on (the Bots page and the Trader say it)."""
    if trade.get("state") not in LIVE_STATES or trade.get("venue") in (None, venue):
        return None
    where = trade.get("venue")
    if where == "sim":
        return ("the trade is on Sim: Sim fills only at its live edge, so it waits until the desk is back on Sim "
                "following the wall clock")
    return (f"the trade is on {where}: its stop and target rest at the broker and still fill; the time stop and the "
            f"flush exit wait until the desk is back on {where}")


# -- the loop -------------------------------------------------------------------
async def run() -> None:
    """Background task (``app_runtime_tasks``): listen to the setup scanner, tick forever."""
    from bot.activation import note_start
    from setup_scanner.engine import get_engine

    note_start()                  # a restart cleared Activate: on the timeline (ADR 042 B)
    engine = get_engine()
    engine.add_trigger_listener(submit)
    try:
        while True:
            try:
                await tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Nova's bot: tick failed")
            await asyncio.sleep(BOT_FP_POLL_SEC)
    finally:
        engine.remove_trigger_listener(submit)


async def tick(now: float | None = None) -> None:
    now = _clock() if now is None else now
    row = load_session()
    _never_live(row)
    on, _why = playing(row)
    _hold_session(row, on, now)
    while _inbox:
        await _on_trigger(_inbox.popleft(), now)
    trade = load_session().get("trade")
    if isinstance(trade, dict) and trade.get("state") in LIVE_STATES:
        await _manage(dict(trade), now)


def _never_live(row: dict[str, Any]) -> None:
    """An active bot where Nova's bot cannot trade (Live, an unreadable venue) is deactivated, said so."""
    from bot import activation
    from constants_sim import DESK_PRACTICE_VENUES

    venue, _edge, readable = activation.venue_state()
    if not is_desk_active(row) or (readable and venue in DESK_PRACTICE_VENUES):
        return
    activation.deactivate_now("venue", f"the desk is on {venue or 'a venue Nova cannot read'}: Nova's bot "
                                       "trades Paper and Sim only")


def _hold_session(row: dict[str, Any], on: bool, now: float) -> None:
    """Claim the L2 session and heartbeat while playing; let go of it when not."""
    global _last_beat
    held = (row.get("brain_session_id") or "").strip()
    if not on:
        if held == BOT_RUNNER_BRAIN_ID:
            row.update(brain_session_id=None, claim_arm_token=None, brain_heartbeat_ts=None)
            save_session(row)
        return
    if held and held != BOT_RUNNER_BRAIN_ID:
        return                                  # an external brain holds Strategy; triggers say so
    if held and now - _last_beat < BOT_FP_HEARTBEAT_SEC:
        return
    from bot.arming import record_heartbeat
    from bot.session import require_l2_brain

    try:
        require_l2_brain(BOT_RUNNER_BRAIN_ID, claim=True)
        record_heartbeat(BOT_RUNNER_BRAIN_ID)
        _last_beat = now
    except BotError as exc:
        _warn_once("claim", "Nova's bot: could not hold the L2 session -- %s", exc.message)


# -- a trigger ----------------------------------------------------------------
async def _on_trigger(event: dict[str, Any], now: float) -> None:
    from bot.eligibility import normalize_symbols

    row = load_session()
    if str(event.get("symbol") or "").upper() not in normalize_symbols(row.get("symbol_allowlist")):
        return                                  # not one of the bot's stocks: Auto-entry's or the scanner's record
    found, sized = admit.for_bot(event, row, now=now)
    if found:
        _skip(event, found)
        return
    trade = admit.trade(event, row, qty=int((sized or {})["qty"]), size_text=(sized or {}).get("text"))
    await _enter(trade, now)


async def _enter(trade: dict[str, Any], now: float) -> None:
    from bot.risk import remember_working

    receipt = await orders.place_entry(trade)
    inputs = {"symbol": trade["symbol"], "qty": trade["qty"], "limit": trade["entry_planned"],
              "venue_day": trade["venue_day"], "setup_id": trade["setup_id"], "template_id": trade["template_id"],
              "setup_type": trade.get("setup_type"), "size": trade.get("size_text")}
    entry_id, target_id, stop_id = orders.leg_ids(receipt)
    if not receipt.ok or entry_id is None:
        why = orders.receipt_error(receipt)
        audit(action=BOT_KIND_SETUP_ENTRY, outcome="failed", reason=why, inputs=inputs)
        _tell(trade["symbol"], now, "warn", f"Nova's bot did not buy: the order was refused ({why})")
        return
    trade.update(entry_order_id=entry_id, target_order_id=target_id, stop_order_id=stop_id, entry_sent_ts=now)
    _save(trade)
    remember_working(order_id=entry_id, symbol=trade["symbol"], side="BUY", qty=trade["qty"],
                     price=trade["entry_planned"], kind=BOT_KIND_SETUP_ENTRY, ttl_sec=None)
    said = (f"{label(trade.get('setup_type'))} over {trade['trigger']} with the tape at go -- buy {trade['qty']:g} "
            f"at {trade['entry_planned']} with target {trade['target1']} and stop {trade['stop']} (one bracket)")
    audit(action=BOT_KIND_SETUP_ENTRY, outcome="ok", order_id=entry_id, inputs=inputs, reason=said)
    _tell(trade["symbol"], now, "info", f"Nova's bot is buying: {said}")


def _skip(event: dict[str, Any], found: list[tuple[str, str]]) -> None:
    reason = admit.text(found)
    audit(action=BOT_AUDIT_ACTION_TRADE, outcome="skipped", reason=reason,
          inputs={"symbol": event.get("symbol"), "setup_id": event.get("setup_id"),
                  "setup_type": event.get("setup_type"), "template_id": event.get("template_id"),
                  "code": found[0][0], "codes": [c for c, _w in found], "reasons": [w for _c, w in found]})
    _tell(str(event.get("symbol") or ""), _clock(), "warn",
          f"Nova's bot did not buy the {label(event.get('setup_type'))}: {reason}")


def _tell(symbol: str, now: float, tone: str, text: str) -> None:
    """The bot's word on a stock is that stock's last event in the Trader (``stock_mode``)."""
    if not symbol:
        return
    try:
        from stock_mode import store

        store.note_event(symbol.upper(), now, tone, text)
    except Exception:
        logger.warning("Nova's bot: the stock's last event was not noted", exc_info=True)


# -- the trade on -------------------------------------------------------------------
async def _manage(trade: dict[str, Any], now: float) -> None:
    from bot.gates import current_venue

    if current_venue() != trade.get("venue"):
        _warn_once(f"venue:{trade['setup_id']}", "Nova's bot: the desk left %s -- %s waits there",
                   trade.get("venue"), trade["symbol"])
        return
    state = trade["state"]
    try:
        if state == "entering":
            await _manage_entry(trade, now)
        elif state == "open":
            await _manage_open(trade, now)
        elif state == "exiting":
            await _manage_exit(trade, now)
    except orders.ReadError as exc:
        _warn_once(f"read:{trade['setup_id']}:{state}", "Nova's bot: %s -- %s not managed this tick",
                   exc, trade["symbol"])


async def _manage_entry(trade: dict[str, Any], now: float) -> None:
    from bot.risk import drop_working

    row = orders.order_row(trade["entry_order_id"])
    state = orders.order_state(row)
    filled = float((row or {}).get("filled_qty") or 0)
    if state == "filled" or (state in ("dead", "gone") and filled > _EPS):
        await _filled(trade, row or {}, now)
        return
    if state in ("dead", "gone"):
        if trade.get("entry_cancel_ts"):
            why = f"not filled in {trade['entry_ttl_sec']}s -- the price ran past {trade['entry_planned']}"
        elif state == "dead":
            why = "the entry was cancelled outside the bot"
        else:
            why = "the entry is gone from the ledger (a Sim rewind or an account reset)"
        drop_working(int(trade["entry_order_id"]))
        trade.update(state="missed", closed_ts=now, note=why)
        _save(trade)
        audit(action=BOT_AUDIT_ACTION_TRADE, outcome="missed", order_id=trade["entry_order_id"], reason=why,
              inputs=_summary(trade))
        _tell(trade["symbol"], now, "warn", f"Nova's bot missed: {why}")
        return
    if trade.get("entry_cancel_ts") is None:
        if now >= float(trade["entry_sent_ts"]) + float(trade["entry_ttl_sec"]):
            receipt = await orders.cancel(trade, int(trade["entry_order_id"]))
            trade["entry_cancel_ts"] = now
            _save(trade)
            if not receipt.ok:
                logger.warning("Nova's bot: cancelling entry %s refused -- %s",
                               trade["entry_order_id"], orders.receipt_error(receipt))
    elif now - float(trade["entry_cancel_ts"]) > BOT_FP_CANCEL_WAIT_SEC:
        _warn_once(f"entry-cancel:{trade['setup_id']}", "Nova's bot: entry %s still working %.0fs after its cancel",
                   trade["entry_order_id"], now - float(trade["entry_cancel_ts"]))


async def _filled(trade: dict[str, Any], row: dict[str, Any], now: float) -> None:
    from bot.risk import adjust_bot_qty, drop_working

    fill = _num(row.get("avg_fill_price")) or float(trade["entry_planned"])
    qty = float(row.get("filled_qty") or trade["qty"])
    trade.update(state="open", qty=qty, entry_fill_price=fill, entry_filled_ts=now,
                 slippage=round(fill - float(trade["entry_planned"]), 4),
                 stop_leg_at=float(trade["stop"]) if trade.get("stop_order_id") else None)
    drop_working(int(trade["entry_order_id"]))
    adjust_bot_qty(trade["symbol"], qty)
    legs = [f"target {trade['target1']}" if trade.get("target_order_id") else None,
            f"stop {trade['stop']}" if trade.get("stop_order_id") else None]
    rest = " and ".join(x for x in legs if x)
    plan = f"{rest} resting at the broker" if rest else "no exit rests at the broker: the bot watches the stop"
    if not trade.get("stop_order_id"):
        trade["note"] = "the stop leg is missing: the bot watches the stop on the last price"
    _save(trade)
    audit(action=BOT_AUDIT_ACTION_TRADE, outcome="filled", order_id=trade["entry_order_id"], inputs=_summary(trade),
          reason=f"bought {qty:g} at {fill} (planned {trade['entry_planned']}); {plan}")
    _tell(trade["symbol"], now, "ok", f"Nova's bot bought {qty:g} {trade['symbol']} at {fill}; {plan}")


def _leg_fill(trade: dict[str, Any]) -> tuple[str, float | None, str] | None:
    """``(reason, price, leg)`` when a resting exit filled (its sibling then cancelled by one-cancels-other);
    else clears a leg that is gone, said on the timeline."""
    legs = (("target_order_id", "target", "target1"), ("stop_order_id", "stop", "stop"))
    rows = {leg: orders.order_row(trade[leg]) for leg, _r, _f in legs if trade.get(leg)}
    for leg, reason, fallback in legs:
        if leg in rows and orders.order_state(rows[leg]) == "filled":
            return reason, _num((rows[leg] or {}).get("avg_fill_price")) or float(trade[fallback]), leg
    for leg, reason, _fallback in legs:
        if leg in rows and orders.order_state(rows[leg]) in ("dead", "gone"):
            trade[leg] = None
            trade["note"] = (f"the {reason} order was cancelled outside the bot -- "
                             + ("the time stop holds" if reason == "target" else "the bot watches the stop itself"))
            _save(trade)
            audit(action=BOT_AUDIT_ACTION_TRADE, outcome="note", reason=trade["note"], inputs=_summary(trade))
    return None


async def _manage_open(trade: dict[str, Any], now: float) -> None:
    symbol = trade["symbol"]
    done = _leg_fill(trade)
    if done is not None:
        trade["exit_order_id"] = trade.get(done[2])          # the resting exit that filled
        _close(trade, now, done[0], done[1])
        return
    held = orders.held_qty(symbol)
    if held <= _EPS:
        await _cancel_legs(trade)
        _close(trade, now, "outside", None)
        return
    if held + _EPS < float(trade["qty"]):
        trade["qty"] = held                     # someone sold part of it: the bot closes what is left
        _save(trade)
    last = orders.last_price(symbol)
    if _watches_stop(trade) and last is not None and last <= float(trade["stop"]) + _EPS:
        await _start_exit(trade, now, "stop", f"{last:g} printed at or under the {trade['stop']:g} stop")
        return
    act = flush.decide(trade, now, last=last)
    if act is not None and act["action"] == "exit":
        await _start_exit(trade, now, "flush", act["why"])
        return
    if act is not None:
        await _tighten(trade, float(act["stop"]), act["why"])
    if now >= float(trade["entry_filled_ts"]) + BOT_FP_TIME_STOP_MIN * 60:
        await _start_exit(trade, now, "time", f"{BOT_FP_TIME_STOP_MIN} minutes without the target or the stop")


def _watches_stop(trade: dict[str, Any]) -> bool:
    """The bot watches the stop on the last price itself when no stop leg rests at it (gone, or left
    lower by a tighten the broker refused)."""
    at = trade.get("stop_leg_at")
    return not trade.get("stop_order_id") or at is None or float(trade["stop"]) > float(at) + _EPS


async def _tighten(trade: dict[str, Any], stop: float, why: str) -> None:
    """Move the stop up: a replace of the resting stop leg; refused, the bot watches the new stop itself."""
    note = why
    if trade.get("stop_order_id"):
        receipt = await orders.replace_stop(trade, int(trade["stop_order_id"]), stop)
        if receipt.ok:
            trade["stop_leg_at"] = float(stop)
        else:
            note = (f"{why} -- the stop leg could not be moved ({orders.receipt_error(receipt)}): it stays at "
                    f"{float(trade.get('stop_leg_at') or trade['stop']):g} and the bot watches {stop:g} itself")
    trade["stop"] = float(stop)
    _save(trade)
    audit(action=BOT_AUDIT_ACTION_TRADE, outcome="note", reason=note, inputs=_summary(trade))


async def _cancel_legs(trade: dict[str, Any]) -> list[tuple[str, Any]]:
    """Cancel the resting target and stop; ``[(leg, receipt)]`` for each refusal."""
    refused: list[tuple[str, Any]] = []
    for leg in ("target_order_id", "stop_order_id"):
        if not trade.get(leg):
            continue
        receipt = await orders.cancel(trade, int(trade[leg]))
        if receipt.ok:
            trade[leg] = None
        else:
            refused.append((leg, receipt))
    _save(trade)
    return refused


async def _start_exit(trade: dict[str, Any], now: float, why: str, detail: str) -> None:
    for leg, receipt in await _cancel_legs(trade):
        row = orders.order_row(trade[leg])
        if orders.order_state(row) == "filled":   # it filled as the bot reached for it
            reason = "target" if leg == "target_order_id" else "stop"
            _close(trade, now, reason, _num((row or {}).get("avg_fill_price"))
                   or float(trade["target1" if reason == "target" else "stop"]))
            return
        logger.warning("Nova's bot: cancelling the %s %s refused -- %s; closing anyway", leg, trade[leg],
                       orders.receipt_error(receipt))
        audit(action=BOT_AUDIT_ACTION_TRADE, outcome="note", inputs=_summary(trade),
              reason=f"the {leg.split('_')[0]} order {trade[leg]} could not be cancelled "
                     f"({orders.receipt_error(receipt)}) -- it still rests; the bot closes anyway")
    trade.update(state="exiting", exit_why=why)
    _save(trade)
    audit(action=BOT_AUDIT_ACTION_TRADE, outcome="closing", reason=detail, inputs=_summary(trade))
    await _send_close(trade, now)


async def _send_close(trade: dict[str, Any], now: float) -> None:
    """A limit under the bid, twice; then the protective flatten."""
    attempt = int(trade.get("exit_attempt") or 0) + 1
    trade["exit_attempt"] = attempt
    if attempt <= BOT_FP_CLOSE_ATTEMPTS and not trade.get("exit_protective"):
        receipt, limit = await orders.close_at_bid(trade, attempt)
        if receipt is not None and receipt.ok and receipt.order_id is not None:
            trade.update(exit_order_id=int(receipt.order_id), exit_sent_ts=now, exit_limit=limit)
            _save(trade)
            return
        logger.warning("Nova's bot: closing %s at the bid failed -- %s; using the protective flatten",
                       trade["symbol"], "no bid on the book" if receipt is None else orders.receipt_error(receipt))
    out = await orders.protective_close(trade, float(trade["qty"]))
    trade.update(exit_order_id=out.get("order_id"), exit_sent_ts=now, exit_limit=None, exit_protective=True)
    _save(trade)
    if not out.get("ok"):
        _warn_once(f"close:{trade['setup_id']}", "Nova's bot: protective close of %s refused -- %s",
                   trade["symbol"], out.get("error"))
        audit(action=BOT_AUDIT_ACTION_TRADE, outcome="error", inputs=_summary(trade),
              reason=f"could not close {trade['symbol']}: {out.get('error')} -- flatten it from the desk")


async def _manage_exit(trade: dict[str, Any], now: float) -> None:
    row = orders.order_row(trade.get("exit_order_id")) if trade.get("exit_order_id") else None
    state = orders.order_state(row)
    if state == "filled":
        _close(trade, now, str(trade.get("exit_why") or "time"), _num((row or {}).get("avg_fill_price")))
        return
    held = orders.held_qty(trade["symbol"])
    if held <= _EPS:
        _close(trade, now, "outside" if state != "working" else str(trade.get("exit_why")), None)
        return
    sent = float(trade.get("exit_sent_ts") or now)
    if state == "working":
        if now >= sent + float(trade["entry_ttl_sec"]):
            await orders.cancel(trade, int(trade["exit_order_id"]))
        return
    if trade.get("exit_protective") and now - sent < BOT_FP_CANCEL_WAIT_SEC:
        return                                  # the protective close gets a moment before a retry
    await _send_close(trade, now)


def _close(trade: dict[str, Any], now: float, reason: str, price: float | None) -> None:
    from bot.risk import adjust_bot_qty

    fill, risk = trade.get("entry_fill_price"), float(trade.get("risk") or 0)
    r = round((price - float(fill)) / risk, 3) if price is not None and fill is not None and risk > 0 else None
    trade.update(state="closed", exit_reason=reason, exit_price=price, closed_ts=now, r=r)
    adjust_bot_qty(trade["symbol"], -float(trade["qty"]))
    _save(trade)
    said = {"target": f"target {trade['target1']:g} filled", "stop": f"stopped out under {trade['stop']:g}",
            "time": f"{BOT_FP_TIME_STOP_MIN}-minute time stop", "flush": "out on a flush on the tape",
            "outside": "the position was closed outside the bot"}.get(reason, reason)
    at = f" at {price:g}" if price is not None else ""
    text = f"{said}{at}" + (f" · {r:+.2f}R" if r is not None else "")
    audit(action=BOT_AUDIT_ACTION_TRADE, outcome="closed", order_id=trade.get("exit_order_id"),
          reason=text, inputs=_summary(trade))
    _tell(trade["symbol"], now, "ok" if reason == "target" else ("bad" if reason == "stop" else "info"),
          f"Nova's bot closed {trade['symbol']}: {text}")


# -- helpers ---------------------------------------------------------------------
def _save(trade: dict[str, Any]) -> None:
    row = load_session()
    row["trade"] = dict(trade)
    save_session(row)


def _summary(trade: dict[str, Any]) -> dict[str, Any]:
    keys = ("symbol", "setup_id", "setup_type", "template_id", "venue", "venue_day", "qty", "entry_planned",
            "entry_fill_price", "stop", "target1", "risk", "exit_price", "exit_reason", "slippage", "r",
            "entry_order_id", "target_order_id", "stop_order_id")
    return {k: trade.get(k) for k in keys}


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


def now() -> float:
    return _clock()


def reset_for_tests(clock: Callable[[], float] | None = None) -> None:
    global _clock, _last_beat
    _inbox.clear()
    _warned.clear()
    _last_beat = 0.0
    _clock = clock or time.time


__all__ = ["BOT_SETUP_FIRST_PULLBACK", "hand_over", "leave_venue", "playing", "status", "submit", "tick",
           "waiting_text"]
