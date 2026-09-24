"""Nova's own bot's loop and its trade (ADR 030; the chosen setup since ADR 031).

Every ``BOT_FP_POLL_SEC``:

1. **Live keeps its gate.** A Strategy bot left active where the read-out
   still applies (Live) and has not passed is deactivated, on the timeline.
2. **Playing?** Strategy, Activate on, a setup with a scanner chosen, on Paper
   or Sim. While it plays, the bot holds the L2 session as brain
   ``nova-first-pullback`` (the id kept from ADR 030, so a running session keeps
   its claim) and heartbeats; when it stops playing it lets go.
3. **Triggers** the setup scanner announced (``submit``) for the chosen setup
   on the bot's own names (its allowlist) are traded -- the first of that setup
   on the symbol that day, the tape at go, every bot gate -- or skipped with the
   reason on the timeline. Other names' and other setups' triggers are left to
   the scanner's own record.
4. **The trade** on is managed. The entry fills, or is cancelled after the
   sleeve's working TTL (a miss). After the fill a SELL limit rests at target 1
   and the bot watches the stop on the last price -- practice venues take no
   brackets, and the door refuses a second SELL of the same shares. A print at
   or under the stop, or the time stop, cancels the target and sells at the
   bid; a close that cannot be sent or does not fill ends in the protective
   flatten. The bot manages its trade until the position is closed, whatever
   the level or Activate say: Deactivate stops new entries only. The
   template's flush exit (ADR 034, ``flush.py``) may move the watched stop up
   or close on a flush on the tape; off, it does nothing.

Owner: the ``trade`` key of the bot session (``bot.persist``); a restart
resumes managing it. States: ``entering`` -> ``open`` -> ``exiting`` ->
``closed``, or ``entering`` -> ``missed``.

maintainer: one-concern the bot's trade state machine and the loop that drives it
"""
from __future__ import annotations

import asyncio
import logging
import math
import time
from collections import deque
from typing import Any, Callable

from bot.arming import clear_arm_fields, is_desk_active
from bot.audit import record as audit
from bot.errors import BotError
from bot.first_pullback import flush, orders
from bot.persist import load_session, save_session
from constants_bot import (
    BOT_AUDIT_ACTION_TRADE,
    BOT_FP_CANCEL_WAIT_SEC,
    BOT_FP_CLOSE_ATTEMPTS,
    BOT_FP_HEARTBEAT_SEC,
    BOT_FP_POLL_SEC,
    BOT_FP_TIME_STOP_MIN,
    BOT_FP_TRIGGER_MAX_AGE_SEC,
    BOT_KIND_SETUP_ENTRY,
    BOT_LEVEL_STRATEGY,
    BOT_REASON_BP_BUDGET,
    BOT_REASON_DAY_LOCK,
    BOT_RUNNER_BRAIN_ID,
    BOT_SETUP_DEFAULT,
    BOT_SETUP_FIRST_PULLBACK,
    BOT_SETUPS_WITH_SCANNER,
)
from constants_setups import SETUP_KIND_FIRST_PULLBACK, SETUPS_READOUT_KINDS, TAPE_VERDICT_GO

logger = logging.getLogger(__name__)

LIVE_STATES = frozenset({"entering", "open", "exiting"})
_EPS = 1e-9
_inbox: deque[dict[str, Any]] = deque(maxlen=50)
_clock: Callable[[], float] = time.time
_last_beat = 0.0
_warned: set[str] = set()


def submit(event: dict[str, Any]) -> None:
    """The setup scanner's trigger listener: enqueue only (it runs on the scanner's tick)."""
    _inbox.append(event)


def chosen(row: dict[str, Any]) -> str:
    return str(row.get("setup") or BOT_SETUP_DEFAULT)


def label(setup: str) -> str:
    return setup.replace("_", " ")


def adjective(setup: str) -> str:
    """``first-pullback`` read-out, ``bull-flag`` read-out."""
    return setup.replace("_", "-")


# -- is the bot playing? --------------------------------------------------------
def playing(row: dict[str, Any], venue: str | None = None) -> tuple[bool, str | None]:
    """Whether the bot plays now, and when not, why (the Bots page says it)."""
    from bot.gates import current_venue
    from constants_sim import DESK_PRACTICE_VENUES

    if int(row.get("level") or 0) < BOT_LEVEL_STRATEGY:
        return False, "the level is not Strategy"
    if not is_desk_active(row):
        return False, "the bot is not active"
    if chosen(row) not in BOT_SETUPS_WITH_SCANNER:
        return False, f"the {label(chosen(row))} has no scanner yet -- nothing for the bot to trade"
    current = venue if venue is not None else current_venue()
    if current not in DESK_PRACTICE_VENUES:
        return False, "Nova's bot trades Paper and Sim only -- Live waits on the read-out and 100 Paper trades"
    return True, None


def status(row: dict[str, Any]) -> dict[str, Any]:
    on, why = playing(row)
    held = (row.get("brain_session_id") or "").strip()
    if on and held and held != BOT_RUNNER_BRAIN_ID:
        on, why = False, f"another bot ({held}) holds Strategy"
    return {"brain_id": BOT_RUNNER_BRAIN_ID, "playing": on, "reason": why}


# -- the loop -------------------------------------------------------------------
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
                logger.exception("first-pullback bot: tick failed")
            await asyncio.sleep(BOT_FP_POLL_SEC)
    finally:
        engine.remove_trigger_listener(submit)


async def tick(now: float | None = None) -> None:
    now = _clock() if now is None else now
    row = load_session()
    _enforce_live_readout(row)
    on, _why = playing(row)
    _hold_session(row, on, now)
    while _inbox:
        await _on_trigger(_inbox.popleft(), now)
    trade = load_session().get("trade")
    if isinstance(trade, dict) and trade.get("state") in LIVE_STATES:
        await _manage(dict(trade), now)


def _enforce_live_readout(row: dict[str, Any]) -> None:
    """A Strategy bot activated on Paper does not stay active on Live with the read-out closed."""
    from bot.gates import readout_open

    if int(row.get("level") or 0) < BOT_LEVEL_STRATEGY or not is_desk_active(row) or readout_open():
        return
    clear_arm_fields(row)
    save_session(row)
    audit(action="deactivate", outcome="ok",
          reason=f"Live waits on the {adjective(chosen(row))} read-out -- the bot stopped")


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
        _warn_once("claim", "first-pullback bot: could not hold the L2 session -- %s", exc.message)


# -- a trigger ----------------------------------------------------------------
async def _on_trigger(event: dict[str, Any], now: float) -> None:
    row = load_session()
    if not playing(row)[0]:
        return                                  # the scanner's own record keeps the trigger
    from bot.eligibility import normalize_symbols

    if str(event.get("symbol") or "").upper() not in normalize_symbols(row.get("symbol_allowlist")):
        return                                  # not one of the bot's names: the scanner's record keeps it
    playing_setup = chosen(row)
    if str(event.get("setup_type") or BOT_SETUP_FIRST_PULLBACK) != playing_setup:
        return                                  # another setup's trigger: the scanner's record keeps it
    setup = event.get("setup") or {}
    at = float(setup.get("triggered_at") or event.get("ts") or 0)
    if now - at > BOT_FP_TRIGGER_MAX_AGE_SEC:
        logger.info("first-pullback bot: %s triggered %.1fs ago -- not traded", event.get("setup_id"), now - at)
        return
    first_kind = SETUPS_READOUT_KINDS.get(playing_setup, SETUP_KIND_FIRST_PULLBACK)
    if setup.get("kind") != first_kind:
        kind = str(setup.get("kind") or "a later setup").replace("_", " ")
        _skip(event, f"a {kind} on {event.get('symbol')} -- the bot plays the first of the day only")
        return
    verdict = (event.get("tape") or {}).get("verdict")
    if verdict != TAPE_VERDICT_GO:
        _skip(event, f"the tape read {verdict or 'nothing'} at the trigger -- the bot enters on go")
        return
    current = row.get("trade")
    if isinstance(current, dict) and current.get("state") in LIVE_STATES:
        _skip(event, f"already in {current.get('symbol')} -- one trade at a time")
        return
    try:
        trade = _admit(event, at)
    except BotError as exc:
        _skip(event, exc.message, code=exc.reason)
        return
    await _enter(trade, now)


def _admit(event: dict[str, Any], at: float) -> dict[str, Any]:
    """Every gate the bot API meets (ADR 027, 030), then the trade to send; BotError says which one refused."""
    from bot.autonomy import assert_can_fire
    from bot.buy_lock import day_lock_active
    from bot.eligibility import assert_symbol_can_fire
    from bot.entry_rules import assert_entry_allowed, venue_day
    from bot.gates import current_venue
    from bot.risk import assert_bp_budget, assert_no_working_buy
    from bot.session import require_l2_brain

    row = assert_can_fire()                     # level, read-out (Live), Activate, padlock, heartbeat
    require_l2_brain(BOT_RUNNER_BRAIN_ID, claim=True)
    symbol = assert_symbol_can_fire(str(event.get("symbol") or ""), row)   # allowlist + a held depth line
    if day_lock_active():
        raise BotError("-$200 day lock -- buys locked until next ET midnight", 409, BOT_REASON_DAY_LOCK)
    assert_entry_allowed(BOT_KIND_SETUP_ENTRY)  # the template's window and daily cap
    assert_no_working_buy(BOT_KIND_SETUP_ENTRY, row)
    setup = event["setup"]
    entry = float(setup["entry"])
    qty = _size(row, entry)
    assert_bp_budget(BOT_KIND_SETUP_ENTRY, symbol, qty, entry, row)
    caps = row.get("caps") or {}
    return {
        "setup_id": str(event.get("setup_id") or ""), "setup_type": str(event.get("setup_type") or BOT_SETUP_FIRST_PULLBACK),
        "symbol": symbol, "venue": current_venue(),
        "venue_day": venue_day(), "template_id": event.get("template_id"),
        "template_rev": event.get("template_rev"), "template_name": event.get("template_name"),
        "state": "entering", "qty": float(qty), "trigger": setup.get("trigger"),
        "trigger_price": setup.get("trigger_price"), "triggered_at": at, "entry_planned": entry,
        "stop": float(setup["stop"]), "target1": float(setup["target1"]), "risk": float(setup["risk"]),
        "entry_order_id": None, "entry_sent_ts": None, "entry_ttl_sec": int(caps.get("working_ttl_sec") or 3),
        "entry_cancel_ts": None, "entry_fill_price": None, "entry_filled_ts": None,
        "target_order_id": None, "exit_order_id": None, "exit_attempt": 0, "exit_sent_ts": None,
        "exit_limit": None, "exit_protective": False, "exit_why": None, "exit_price": None,
        "exit_reason": None, "closed_ts": None, "slippage": None, "r": None, "note": None,
    }


def _size(row: dict[str, Any], entry: float) -> int:
    """The sleeve's max shares, cut to what its dollar budget still buys at the entry."""
    from bot.risk import open_plus_working_usd

    caps = row.get("caps") or {}
    shares = int(caps.get("max_shares") or 1)
    budget = float(caps.get("bp_budget_usd") or 0)
    room = budget - open_plus_working_usd(row)
    qty = min(shares, math.floor((room + _EPS) / entry)) if entry > 0 else 0
    if qty < 1:
        raise BotError(f"the ${budget:.2f} budget buys no share at {entry:.2f}", 409, BOT_REASON_BP_BUDGET)
    return qty


async def _enter(trade: dict[str, Any], now: float) -> None:
    from bot.risk import remember_working

    receipt = await orders.place_entry(trade)
    inputs = {"symbol": trade["symbol"], "qty": trade["qty"], "limit": trade["entry_planned"],
              "venue_day": trade["venue_day"], "setup_id": trade["setup_id"], "template_id": trade["template_id"],
              "setup_type": trade.get("setup_type")}
    if not receipt.ok or receipt.order_id is None:
        audit(action=BOT_KIND_SETUP_ENTRY, outcome="failed", reason=orders.receipt_error(receipt), inputs=inputs)
        return
    trade.update(entry_order_id=int(receipt.order_id), entry_sent_ts=now)
    _save(trade)
    remember_working(order_id=int(receipt.order_id), symbol=trade["symbol"], side="BUY", qty=trade["qty"],
                     price=trade["entry_planned"], kind=BOT_KIND_SETUP_ENTRY, ttl_sec=None)
    audit(action=BOT_KIND_SETUP_ENTRY, outcome="ok", order_id=int(receipt.order_id), inputs=inputs,
          reason=f"{label(str(trade.get('setup_type') or BOT_SETUP_FIRST_PULLBACK))} over {trade['trigger']} "
                 f"with the tape at go -- limit {trade['entry_planned']}")


def _skip(event: dict[str, Any], reason: str, *, code: str | None = None) -> None:
    audit(action=BOT_AUDIT_ACTION_TRADE, outcome="skipped", reason=reason,
          inputs={"symbol": event.get("symbol"), "setup_id": event.get("setup_id"),
                  "setup_type": event.get("setup_type"), "template_id": event.get("template_id"), "code": code})


# -- the trade on -------------------------------------------------------------------
async def _manage(trade: dict[str, Any], now: float) -> None:
    from bot.gates import current_venue

    if current_venue() != trade.get("venue"):
        _warn_once(f"venue:{trade['setup_id']}", "first-pullback bot: the desk left %s -- %s waits there",
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
        _warn_once(f"read:{trade['setup_id']}:{state}", "first-pullback bot: %s -- %s not managed this tick",
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
        return
    if trade.get("entry_cancel_ts") is None:
        if now >= float(trade["entry_sent_ts"]) + float(trade["entry_ttl_sec"]):
            receipt = await orders.cancel(trade, int(trade["entry_order_id"]))
            trade["entry_cancel_ts"] = now
            _save(trade)
            if not receipt.ok:
                logger.warning("first-pullback bot: cancelling entry %s refused -- %s",
                               trade["entry_order_id"], orders.receipt_error(receipt))
    elif now - float(trade["entry_cancel_ts"]) > BOT_FP_CANCEL_WAIT_SEC:
        _warn_once(f"entry-cancel:{trade['setup_id']}", "first-pullback bot: entry %s still working %.0fs after its cancel",
                   trade["entry_order_id"], now - float(trade["entry_cancel_ts"]))


async def _filled(trade: dict[str, Any], row: dict[str, Any], now: float) -> None:
    from bot.risk import adjust_bot_qty, drop_working

    fill = _num(row.get("avg_fill_price")) or float(trade["entry_planned"])
    qty = float(row.get("filled_qty") or trade["qty"])
    trade.update(state="open", qty=qty, entry_fill_price=fill, entry_filled_ts=now,
                 slippage=round(fill - float(trade["entry_planned"]), 4))
    drop_working(int(trade["entry_order_id"]))
    adjust_bot_qty(trade["symbol"], qty)
    _save(trade)
    receipt = await orders.place_target(trade)
    if receipt.ok and receipt.order_id is not None:
        trade["target_order_id"] = int(receipt.order_id)
        plan = f"target {trade['target1']} resting, stop {trade['stop']} watched"
    else:
        trade["note"] = f"the target was refused ({orders.receipt_error(receipt)}) -- the stop and the time stop hold"
        plan = trade["note"]
    _save(trade)
    audit(action=BOT_AUDIT_ACTION_TRADE, outcome="filled", order_id=trade["entry_order_id"], inputs=_summary(trade),
          reason=f"bought {qty:g} at {fill} (planned {trade['entry_planned']}); {plan}")


async def _manage_open(trade: dict[str, Any], now: float) -> None:
    symbol = trade["symbol"]
    if trade.get("target_order_id"):
        row = orders.order_row(trade["target_order_id"])
        state = orders.order_state(row)
        if state == "filled":
            _close(trade, now, "target", _num((row or {}).get("avg_fill_price")) or float(trade["target1"]))
            return
        if state in ("dead", "gone"):
            trade.update(target_order_id=None,
                         note="the target was cancelled outside the bot -- the stop and the time stop hold")
            _save(trade)
            audit(action=BOT_AUDIT_ACTION_TRADE, outcome="note", reason=trade["note"], inputs=_summary(trade))
    held = orders.held_qty(symbol)
    if held <= _EPS:
        if trade.get("target_order_id"):
            await orders.cancel(trade, int(trade["target_order_id"]))
        _close(trade, now, "outside", None)
        return
    if held + _EPS < float(trade["qty"]):
        trade["qty"] = held                     # someone sold part of it: the bot closes what is left
        _save(trade)
    last = orders.last_price(symbol)
    if last is not None and last <= float(trade["stop"]) + _EPS:
        await _start_exit(trade, now, "stop", f"{last:g} printed at or under the {trade['stop']:g} stop")
        return
    act = flush.decide(trade, now, last=last)
    if act is not None and act["action"] == "exit":
        await _start_exit(trade, now, "flush", act["why"])
        return
    if act is not None:
        trade["stop"] = float(act["stop"])
        _save(trade)
        audit(action=BOT_AUDIT_ACTION_TRADE, outcome="note", reason=act["why"], inputs=_summary(trade))
    if now >= float(trade["entry_filled_ts"]) + BOT_FP_TIME_STOP_MIN * 60:
        await _start_exit(trade, now, "time", f"{BOT_FP_TIME_STOP_MIN} minutes without the target or the stop")


async def _start_exit(trade: dict[str, Any], now: float, why: str, detail: str) -> None:
    if trade.get("target_order_id"):
        receipt = await orders.cancel(trade, int(trade["target_order_id"]))
        if not receipt.ok:
            row = orders.order_row(trade["target_order_id"])
            if orders.order_state(row) == "filled":   # it filled as the bot reached for it
                _close(trade, now, "target", _num((row or {}).get("avg_fill_price")) or float(trade["target1"]))
                return
            logger.warning("first-pullback bot: cancelling target %s refused -- %s; closing anyway",
                           trade["target_order_id"], orders.receipt_error(receipt))
        else:
            trade["target_order_id"] = None
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
        logger.warning("first-pullback bot: closing %s at the bid failed -- %s; using the protective flatten",
                       trade["symbol"], "no bid on the book" if receipt is None else orders.receipt_error(receipt))
    out = await orders.protective_close(trade, float(trade["qty"]))
    trade.update(exit_order_id=out.get("order_id"), exit_sent_ts=now, exit_limit=None, exit_protective=True)
    _save(trade)
    if not out.get("ok"):
        _warn_once(f"close:{trade['setup_id']}", "first-pullback bot: protective close of %s refused -- %s",
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
    audit(action=BOT_AUDIT_ACTION_TRADE, outcome="closed", order_id=trade.get("exit_order_id"),
          reason=f"{said}{at}" + (f" · {r:+.2f}R" if r is not None else ""), inputs=_summary(trade))


# -- helpers ---------------------------------------------------------------------
def _save(trade: dict[str, Any]) -> None:
    row = load_session()
    row["trade"] = dict(trade)
    save_session(row)


def _summary(trade: dict[str, Any]) -> dict[str, Any]:
    keys = ("symbol", "setup_id", "setup_type", "template_id", "venue", "venue_day", "qty", "entry_planned",
            "entry_fill_price", "stop", "target1", "risk", "exit_price", "exit_reason", "slippage", "r")
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


def reset_for_tests(clock: Callable[[], float] | None = None) -> None:
    global _clock, _last_beat
    _inbox.clear()
    _warned.clear()
    _last_beat = 0.0
    _clock = clock or time.time
