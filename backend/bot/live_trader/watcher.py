"""The Live Trader bot's watcher: a background task of the backend, like the feed's keeper (ADR 055 decision 6).

Idle -- nothing asked of the feed -- while no host's key is on, the bot holds nothing and no ask waits (every
``LT_IDLE_SEC``); otherwise every ``LT_POLL_SEC``, and at once when the operator acts on the Bots page (``Wake``):

1. the desk's day (04:00 ET): a position held from another day is sold at once (``book.roll_day``);
2. the orders in flight to their ends (a step past the Paper sleeve's TTL is cancelled) and Paper's shares checked
   against the bot's (``act.reconcile``);
3. one read of the feed (``answer.read``, on a worker thread) and one decision (``decide``), carried out by ``act``:
   closes first, then re-keys, steps, asks and the lines said;
4. its Level 1 lines on every stock it holds or waits to enter (``lines``), the market caps it waits on
   (``market.want_caps``), and its heartbeat (``status``) for the Bots page.

It keeps the last decision's snapshot -- the hosts' open rows and what was decided for each -- in memory, a few KB,
never growing past the day's trades; what it holds is ``book``'s. Every order goes through the execution door, so the
kill switch (Freeze all orders), the padlock and the day lock stop it as they stop any bot.
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
    LT_DAY_LOCK,
    LT_FROZEN,
    LT_IDLE_SEC,
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
_requests: dict[str, Any] = {"sell_hosts": {}, "sell_all": None}
_answers: dict[str, bool] = {}
_status: dict[str, Any] = {"running": False, "pass_ts": None, "answer": None, "waits": {}, "can_open": None,
                           "idle": True}


def reset_for_tests() -> None:
    global _snapshot, _requests, _answers, _status
    with _lock:
        _snapshot = None
        _requests = {"sell_hosts": {}, "sell_all": None}
        _answers = {}
        _status = {"running": False, "pass_ts": None, "answer": None, "waits": {}, "can_open": None, "idle": True}
    act.reset_for_tests()
    answer.reset_for_tests()


# -- what the routes and the Bot switch ask ----------------------------------------------------------
def request_sell_host(name: str) -> None:
    """A host's key turned off: its positions are sold on the next pass."""
    with _lock:
        _requests["sell_hosts"][name] = "key_off"
    _wake.set()


def request_sell_all(reason: str = "bot_off") -> None:
    """The operator turned the Bot switch off: every position is sold on the next pass."""
    with _lock:
        _requests["sell_all"] = reason
    _wake.set()


def cancel_sell_all() -> None:
    with _lock:
        _requests["sell_all"] = None


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


def holds_positions() -> bool:
    return bool(book.positions())


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


def can_open() -> dict[str, Any]:
    """Whether the bot may open or add now, else the first reason (``decide``'s ``can_open``)."""
    import kill_switch
    from bot import switch
    from bot.buy_lock import buy_refusal
    from bot.persist import load_session
    from ibkr import client
    from sim.mode import venue

    def no(code: str, why: str) -> dict[str, Any]:
        return {"ok": False, "code": code, "why": why}

    desk = venue()
    if desk != LT_VENUE:
        return no(LT_VENUE_CODE, f"the desk is on {VENUE_WORDS.get(desk, desk)}: the Live Trader bot trades Paper only")
    if book.error():
        return no(LT_BOT_OFF, str(book.error()))
    if not switch.is_on(load_session()):
        return no(LT_BOT_OFF, "the Bot switch is off: turn it on to let the hosts' bots trade")
    if kill_switch.is_tripped():
        return no(LT_FROZEN, "Freeze all orders is on: no new orders")
    lock = buy_refusal("BUY", "bot", LT_VENUE)
    if lock is not None:
        return no(LT_DAY_LOCK, str(lock["text"]))
    if not client.is_ready():
        return no(LT_NO_QUOTE, "IBKR is not connected: Paper fills on IBKR's live feed")
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


def _context(now: float, positions: dict[str, dict[str, Any]]) -> dict[str, Any]:
    with _lock:
        holders = {p["host"] for p in positions.values()}
        _requests["sell_hosts"] = {h: r for h, r in _requests["sell_hosts"].items() if h in holders}
        if not positions:
            _requests["sell_all"] = None
        requests = {"sell_hosts": dict(_requests["sell_hosts"]), "sell_all": _requests["sell_all"]}
        answers = dict(_answers)
        _answers.clear()
    return {"now": now, "settings": settings.of, "can_open": can_open(), "sell_all_ts": sell_all_ts(now),
            "requests": requests, "quote": market.quote, "cap": market.cap, "held": orders.held,
            "short_closed": market.short_closed, "answers": answers, "no_reentry": book.no_reentry()}


async def tick(now: float | None = None) -> bool:
    """One pass; True while the bot is busy (a key on, a position held, an ask waiting)."""
    global _snapshot
    now = time.time() if now is None else now
    for pos in book.roll_day(_desk_day(now)):
        act.note({"kind": "stale_day", "host": pos["host"], "row_id": pos["row_id"], "symbol": pos["symbol"],
                  "side": pos["side"], "step": "stale_day",
                  "why": "held from an earlier day: sold at once, the bot never holds overnight"}, now)
        await act.close({"kind": "close", "host": pos["host"], "pos_id": pos["id"], "row_id": pos["row_id"],
                         "symbol": pos["symbol"], "side": pos["side"], "qty": pos["qty"],
                         "why": "held from an earlier day: never overnight",
                         "change": {"kind": "stale_day", "ts": now, "price": None}}, now)
    await manage(now)
    positions = book.positions()
    waiting = bool((_snapshot or {}).get("asks"))
    if not (settings.hosts_on() or positions or waiting):
        lines.want([], now)
        with _lock:
            _status.update(idle=True, pass_ts=now, answer=None, waits={}, can_open=None)
        return False
    got = await asyncio.to_thread(answer.read, now)
    ctx = _context(now, positions)
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
