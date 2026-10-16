"""The Live Trader bot's watcher: a background task of the backend, like the feed's keeper (ADR 055 decision 6).

Idle -- only the day's host names asked of the feed, so each host's card and key show (``_feed_names``) -- while no
host's key is on, the bot holds nothing and no ask waits (every ``LT_IDLE_SEC``); otherwise every ``LT_POLL_SEC``,
and at once when the operator acts on the Bots page (``Wake``):

1. the desk's day (04:00 ET): a position held from another day is sold at once (``book.roll_day``);
2. the orders in flight to their ends (a step past the Paper sleeve's TTL is cancelled) and Paper's shares checked
   against the bot's (``act.reconcile``);
3. one read of the feed (``answer.read``, on a worker thread) and one decision (``decide``), carried out by ``act``:
   closes first, then re-keys, steps, asks and the lines said;
4. its Level 1 lines on every stock it holds or waits to enter (``lines``), the market caps it waits on
   (``market.want_caps``), and its heartbeat (``status``) for the Bots page.

It keeps the last decision's snapshot -- the hosts' open rows and what was decided for each -- in memory, a few KB,
never growing past the day's trades; what it holds is ``book``'s. Every order goes through the execution door, so the
kill switch (Freeze all orders), the padlock and the daily loss limit's No new buys stop it as they stop any bot.
With a key off -- the Bot switch, the LiveTrader Bots key or the host's own -- it places no order, not even a sell
(``keys``; operator decision 2026-10-15): what it holds waits, said once, until the keys are back on or the operator
sells it. It still takes back its own orders (a step past its TTL, the stops of a position that holds nothing).
"""
from __future__ import annotations

import asyncio
import logging
import threading
import time
from typing import Any

from bot.live_trader import act, answer, book, decide, lines, market, orders, settings
from bot.live_trader.constants_live_trader import (
    LT_BOT_OFF,
    LT_FAMILY_OFF,
    LT_LOSS_LIMIT,
    LT_FROZEN,
    LT_IDLE_SEC,
    LT_KEY_OFF,
    LT_NO_QUOTE,
    LT_POLL_SEC,
    LT_VENUE,
    LT_VENUE_CODE,
)
from bot.wake import Wake

logger = logging.getLogger(__name__)
VENUE_WORDS = {"live": "Live", "paper": "Paper", "sim": "Sim"}

_lock = threading.Lock()
_wake = Wake()
_snapshot: dict[str, Any] | None = None
_answers: dict[str, bool] = {}
_stale_said: set[str] = set()           # "pos id|opened_ts|outcome": an earlier day's position, said once per outcome
_status: dict[str, Any] = {"running": False, "pass_ts": None, "answer": None, "waits": {}, "can_open": None,
                           "idle": True, "names": [], "names_day": None}


def reset_for_tests() -> None:
    global _snapshot, _answers, _status
    with _lock:
        _snapshot = None
        _answers = {}
        _stale_said.clear()
        _status = {"running": False, "pass_ts": None, "answer": None, "waits": {}, "can_open": None, "idle": True,
                   "names": [], "names_day": None}
    act.reset_for_tests()
    answer.reset_for_tests()


# -- what the routes ask ------------------------------------------------------------------------------
def wake() -> None:
    """A key or a setting changed on the desk: the next pass now."""
    _wake.set()


def answer_ask(ask_id: str, approve: bool) -> bool:
    """The operator's answer to an ask; False when the ask is gone (expired, answered, withdrawn)."""
    with _lock:
        asks = (_snapshot or {}).get("asks") or {}
        if ask_id not in asks or ask_id in _answers or asks[ask_id].get("approved"):
            return False
        _answers[ask_id] = bool(approve)
    _wake.set()
    return True


def asks() -> list[dict[str, Any]]:
    with _lock:
        return [dict(a, answered=_answers.get(i)) for i, a in ((_snapshot or {}).get("asks") or {}).items()]


def status() -> dict[str, Any]:
    with _lock:
        return {**_status, "hosts_state": dict(((_snapshot or {}).get("hosts") or {}))}


# -- the loop --------------------------------------------------------------------------------------
async def run() -> None:
    """The backend's loop (``app_runtime_tasks``)."""
    _wake.bind()
    with _lock:
        _status["running"] = True
    try:
        while True:
            busy = False
            try:
                busy = await tick()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 -- the watcher must outlive any one bad pass
                logger.exception("Live Trader bot: a pass failed")
            await _wake.sleep(LT_POLL_SEC if busy else LT_IDLE_SEC)
    finally:
        with _lock:
            _status["running"] = False


def _desk_day(now: float) -> str:
    from followed_traders.routes import desk_day

    return desk_day(now)[0]


def _paper_ttl() -> float:
    from bot.persist import load_session
    from bot.sleeve import by_venue

    return float(by_venue(load_session())[LT_VENUE]["working_ttl_sec"])


async def manage(now: float) -> None:
    """Orders in flight to their ends; a step working past the Paper sleeve's TTL is cancelled."""
    book.retry_save()
    ttl = _paper_ttl()
    for pos in book.positions().values():
        if pos.get("order"):
            if act.follow_step(pos["id"], now, ttl=ttl) == "cancel":
                try:
                    await orders.cancel(pos["order"]["id"], pos["symbol"], pos["host"])
                except Exception:
                    logger.exception("Live Trader bot: the late step on %s was not cancelled", pos["symbol"])
                act.follow_step(pos["id"], now)
        elif pos["state"] == "closing":
            act.follow_close(pos["id"], now)
    await act.reconcile(now)
    await act.clear_stops(now)


def _no(code: str, why: str) -> dict[str, Any]:
    return {"ok": False, "code": code, "why": why}


def keys() -> dict[str, Any]:
    """Whether the hosts' bots may send any order now -- the desk on Paper, the Bot switch and the LiveTrader Bots
    key on -- else the first that is not. With one off they place nothing, not even a sell (operator decision
    2026-10-15); each host's own key is the third (``keys_hold``)."""
    from bot import family_keys
    from constants_bot import BOT_FAMILY_LIVE_TRADER, BOT_SKIP_FAMILY_OFF
    from sim.mode import venue

    desk = venue()
    if desk != LT_VENUE:
        return _no(LT_VENUE_CODE, f"the desk is on {VENUE_WORDS.get(desk, desk)}: the Live Trader bot trades Paper "
                                  "only")
    held = family_keys.hold(BOT_FAMILY_LIVE_TRADER, LT_VENUE)
    if held is not None:
        return _no(LT_FAMILY_OFF if held[0] == BOT_SKIP_FAMILY_OFF else LT_BOT_OFF, held[1])
    return {"ok": True, "code": None, "why": None}


def keys_hold(acts: dict[str, Any], settings_of: Any = None) -> Any:
    """``hold(host)``: ``(code, why)`` while that host's bot may place no order -- ``acts`` (``keys``) not ok, or
    its own key off -- else None. ``decide`` reads it before every close."""
    read = settings_of or settings.of

    def hold(host: str) -> tuple[str, str] | None:
        if not acts["ok"]:
            return acts["code"], acts["why"]
        if not read(host)["key"]:
            return LT_KEY_OFF, f"{host}'s Bot key is off: its bot places no order, not even a sell"
        return None
    return hold


def can_open() -> dict[str, Any]:
    """Whether the bot may open or add now, else the first reason (``decide``'s ``can_open``)."""
    import kill_switch
    from ibkr import client

    acts = keys()
    if not acts["ok"]:
        return acts
    if book.error():
        return _no(LT_BOT_OFF, str(book.error()))
    if kill_switch.is_tripped():
        return _no(LT_FROZEN, "Freeze all orders is on: no new orders")
    from loss_limit.gate import buy_refusal

    lock = buy_refusal("BUY", "bot", LT_VENUE)
    if lock is not None:
        return _no(LT_LOSS_LIMIT, str(lock["text"]))
    if not client.is_ready():
        return _no(LT_NO_QUOTE, "IBKR is not connected: Paper fills on IBKR's live feed")
    return {"ok": True, "code": None, "why": None}


def sell_all_ts(now: float) -> float | None:
    """Today's sell-all moment: ``sell_all_at`` ET, or the early close's day cover when that comes first."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    et = datetime.fromtimestamp(now, ZoneInfo("America/New_York"))
    hh, mm = (int(x) for x in settings.sell_all_at().split(":"))
    at = et.replace(hour=hh, minute=mm, second=0, microsecond=0).timestamp()
    cover = market.cover_ts(now)
    return min(at, cover) if cover is not None else at


def _short_blocks(a: dict[str, Any]) -> list[tuple[str, str]]:
    """The one short check's failures for this short step, read as the door would (``short_side``)."""
    from bot.first_pullback import short_side

    facts, error = short_side.gather(a["symbol"], LT_VENUE)
    if facts is None:
        return [("SHORT_CHECK_UNREAD", f"{error}: no short")]
    priced = short_side.Priced(a["limit"], False, "unknown", None)
    found, why = short_side.verdicts(a["symbol"], a["qty"], priced, {"stop": a["stop"]}, facts, LT_VENUE)
    if why:
        return [("SHORT_CHECK_UNREAD", why)]
    return [(str(v.get("code") or "SHORT_REFUSED"), f"{v.get('label')}: {v.get('text')}") for v in found
            if not v.get("ok")]


def _context(now: float) -> dict[str, Any]:
    with _lock:
        answers = dict(_answers)
        _answers.clear()
    return {"now": now, "settings": settings.of, "can_open": can_open(), "sell_all_ts": sell_all_ts(now),
            "keys_hold": keys_hold(keys()), "quote": market.quote, "cap": market.cap, "ssr": market.ssr, "range_since": market.range_since, "held": orders.held,
            "short_closed": market.short_closed, "answers": answers, "no_reentry": book.no_reentry()}


async def tick(now: float | None = None) -> bool:
    """One pass; True while the bot is busy (a key on, a position held, an ask waiting)."""
    global _snapshot
    now = time.time() if now is None else now
    await _sell_earlier_days(now)
    await manage(now)
    positions = book.positions()
    waiting = bool((_snapshot or {}).get("asks"))
    if not (settings.hosts_on() or positions or waiting):
        lines.want([], now)
        day, names, down = await asyncio.to_thread(_feed_names, now)
        with _lock:
            if names is None:                  # a read that failed keeps the names last read that day
                names = _status["names"] if _status.get("names_day") == day else []
            _status.update(idle=True, pass_ts=now, answer=None if down is None else summary(down), waits={},
                           names=names, names_day=day)
        can = can_open()                       # idle too: the cards say what would stop a key turned on
        with _lock:
            _status["can_open"] = can
        return False
    got = await asyncio.to_thread(answer.read, now)
    market.note_prices({p["symbol"] for p in positions.values()}, now)
    ctx = _context(now)
    out = decide.decide(_snapshot, got, positions, ctx)
    with _lock:
        _snapshot = out["snapshot"]
    rewait = await _carry_out(out, now)
    if rewait:
        _rewait(rewait, now)
    held = {p["symbol"] for p in book.positions().values()}
    lines.want(out["symbols"] | held, now)
    market.want_caps(out["caps"])
    with _lock:
        _status.update(idle=False, pass_ts=now, answer=summary(got), waits=dict(out["waits"]),
                       can_open=ctx["can_open"])
    return True


async def _sell_earlier_days(now: float) -> None:
    """Every position held from an earlier desk day (04:00 ET) is sold at once: the bot never holds overnight. Judged
    from each position's own open time on every pass, so one a key held back is sold the pass the keys are back on
    (Codex review, PR #1006); each is said once per outcome."""
    today = _desk_day(now)
    book.roll_day(today)
    hold = keys_hold(keys())
    positions = list(book.positions().values())
    # One instance per position: a stock the host trades again on a later day is said again; a closed one forgotten.
    live = {f"{p['id']}|{p.get('opened_ts')}" for p in positions}
    for said in [k for k in _stale_said if k.rsplit("|", 1)[0] not in live]:
        _stale_said.discard(said)
    for pos in positions:
        if pos["state"] == "closing" or _desk_day(float(pos.get("opened_ts") or now)) >= today:
            continue
        held = hold(pos["host"])
        said = f"{pos['id']}|{pos.get('opened_ts')}|{held[0] if held else 'sell'}"
        if said not in _stale_said:
            _stale_said.add(said)
            act.note({"kind": "stale_day", "host": pos["host"], "row_id": pos["row_id"], "symbol": pos["symbol"],
                      "side": pos["side"], "step": "stale_day",
                      "why": "held from an earlier day: sold at once, the bot never holds overnight" if held is None
                      else f"held from an earlier day: not sold -- {held[1]}"}, now)
        if held is not None:
            continue
        await act.close({"kind": "close", "host": pos["host"], "pos_id": pos["id"], "row_id": pos["row_id"],
                         "symbol": pos["symbol"], "side": pos["side"], "qty": pos["qty"],
                         "why": "held from an earlier day: never overnight",
                         "change": {"kind": "stale_day", "ts": now, "price": None}}, now)


def _feed_names(now: float) -> tuple[str, list[str] | None, dict[str, Any] | None]:
    """``(the desk's day, the hosts the feed read that day in its order, None)``, asked while the bot is idle so each
    host's card -- and its key -- shows before any key is on (``view.build``). No feed set up, or a read that fails:
    ``(day, None, the feed's state as an answer)``, so the card says why and the names last read that day stay."""
    from followed_traders import config, feed
    from followed_traders.routes import desk_day

    today = desk_day(now)[0]
    base = config.feed_url()
    if base is None:
        return today, None, answer.down("off", "NOVA_FOLLOW_FEED_URL is not set: there is no TraderTV feed to read")
    try:
        day = feed.fetch_day(base, today)
    except feed.FeedError as exc:
        logger.info("Live Trader bot: the feed's hosts were not read while idle (%s)", exc.message)
        return today, None, answer.down(exc.state, exc.message)
    status = day.get("status") or {}
    names = [t["trader"] for t in day["trades"]]
    names += [*(status.get("traders") or []), *(p["trader"] for p in status.get("positions") or [])]
    return today, list(dict.fromkeys(names)), None


def summary(got: dict[str, Any]) -> dict[str, Any]:
    """The answer as the cards read it: the feed's health, each host's off-air time and open rows' averages."""
    hosts = got.get("hosts") or {}
    return {**{k: v for k, v in got.items() if k not in ("hosts", "faces", "previous")},
            "faces": sorted(got.get("faces") or ()),
            "left": {n: h.get("left_ts") for n, h in hosts.items()},
            "prices": {r["id"]: r["price"] for h in hosts.values() for r in h.get("rows") or []
                       if r["status"] == "open"}}


async def _carry_out(out: dict[str, Any], now: float) -> list[dict[str, Any]]:
    """The decision's actions in order: closes, re-keys, steps; the lines said as they come."""
    order = {"close": 0, "rekey": 1, "step": 2}
    rewait = []
    for a in sorted(out["actions"], key=lambda x: order.get(x["kind"], 3)):
        kind = a["kind"]
        if kind == "close":
            await act.close(a, now)
        elif kind == "rekey":
            act.rekey(a, now)
        elif kind == "step":
            if await act.step(a, now, short_blocks=_short_blocks) == "wait":
                rewait.append(a)
        elif kind == "skip":
            act.skip(a, now)
        elif kind == "ask":
            ask = a["ask"]
            act.note({**ask, "kind": "ask", "why": ask["text"]}, now, outcome="asked")
        elif kind == "drop_ask":
            act.audit("answered", {"host": a["host"], "step": "ask"}, why=f"ask {a['ask_id']}: {a['why']}", now=now)
        elif kind in ("note", "tell"):
            act.note(a, now)
    return rewait


def _rewait(steps: list[dict[str, Any]], now: float) -> None:
    """A short whose borrow is being read waits for it, as a quote line does (``LT_WAIT_SEC``)."""
    with _lock:
        for a in steps:
            rows = (((_snapshot or {}).get("hosts") or {}).get(a["host"]) or {}).get("rows") or {}
            rs = rows.get(a["row_id"])
            if rs is not None:
                rs["fate"], rs["since"] = "waiting", rs.get("since") or now
