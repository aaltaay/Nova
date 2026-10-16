"""``GET /api/bot/live-traders``: each host's card on Bots > LiveTrader Bots (ADR 055).
Reads memory and the operator cache.

One card per host the feed read on the last pass, then every host with settings, positions or closed trades today:
its key and Entry / Exit, what it holds and makes, its allowance, its asks and its newest audit lines -- each a
step, a skip with its reason or a word from the watcher. Shapes: architecture/schema/bot.md ("The Live Trader bot").
"""
from __future__ import annotations

import logging
import time
from typing import Any

from bot.live_trader import book, market, settings, watcher
from bot.live_trader.constants_live_trader import (
    LT_AUDIT_ACTION,
    LT_AUDIT_TAIL_BYTES,
    LT_EVENTS_SHOWN,
    LT_SCHEMA_VERSION,
    LT_VENUE,
)
from bot.live_trader.decide_closes import hms
from bot.live_trader.rules import used_by_host
from stock_mode.model import mode_of

logger = logging.getLogger(__name__)
TONES = {"order": "ok", "partial": "ok", "filled": "ok", "closed": "ok", "skipped": "warn", "refused": "bad", "error": "bad",
         "asked": "warn", "answered": "plain", "note": "plain", "settings": "plain"}
FACE_PATH = "/api/followed-traders/faces/{date}/{name}.jpg"


_events_cache: dict[str, Any] = {"sig": None, "out": {}}


def _events() -> dict[str, list[dict[str, Any]]]:
    """Each host's ``live_trader`` lines, newest first, from the audit file's last ``LT_AUDIT_TAIL_BYTES`` -- read
    again only when the file changed (the whole file is months of every bot's lines)."""
    from bot.persist import audit_signature, read_audit_tail

    sig = audit_signature()
    if sig is not None and sig == _events_cache["sig"]:
        return _events_cache["out"]
    out: dict[str, list[dict[str, Any]]] = {}
    try:
        lines, _whole = read_audit_tail(LT_AUDIT_TAIL_BYTES)
    except Exception:
        logger.warning("Live Trader bot: the audit stream could not be read for the cards", exc_info=True)
        return out
    for line in lines:
        if line.get("action") != LT_AUDIT_ACTION:
            continue
        inputs = line.get("inputs") or {}
        host = inputs.get("host")
        if not host:
            continue
        out.setdefault(host, []).append({"ts": line.get("timestamp"), "tone": TONES.get(line.get("outcome"), "plain"),
                                         "outcome": line.get("outcome"), "symbol": inputs.get("symbol"),
                                         "text": line.get("reason") or inputs.get("why"), "code": inputs.get("code"),
                                         "late_sec": inputs.get("late_sec")})
    for rows in out.values():
        rows.sort(key=lambda r: r["ts"] or 0, reverse=True)
    _events_cache.update(sig=sig, out=out)
    return out


def _position(pos: dict[str, Any], their: dict[str, float]) -> dict[str, Any]:
    q = market.quote(pos["symbol"]) or {}
    now = q.get("last")
    qty = pos["qty"]
    avg = round(pos["cost_usd"] / qty, 4) if qty else None
    pl = None
    if now is not None and avg is not None:
        pl = round((now - avg) * qty if pos["side"] == "long" else (avg - now) * qty, 2)
    order = pos.get("order") or {}
    note = None
    if pos["state"] == "entering":
        note = f"{order.get('step', 'step')} working at {order.get('limit')}"
    elif pos["state"] == "closing":
        note = (pos.get("close") or {}).get("why")
    elif (pos.get("close") or {}).get("error"):
        note = f"the close was refused: {pos['close']['error']}"
    return {"id": pos["id"], "row_id": pos["row_id"], "symbol": pos["symbol"], "side": pos["side"], "qty": qty,
            "avg_cost": avg, "their_avg": their.get(pos["row_id"], (pos.get("feed") or {}).get("price")),
            "now": now, "pl_usd": pl, "steps": pos["steps"], "adds_followed": pos["adds_followed"],
            "opened_ts": pos["opened_ts"], "state": pos["state"], "order_id": order.get("id"), "note": note}


def _today(name: str, positions: list[dict[str, Any]], closed: list[dict[str, Any]],
           events: list[dict[str, Any]]) -> dict[str, Any]:
    mine = sorted((c for c in closed if c["host"] == name), key=lambda c: c.get("closed_ts") or 0)
    realized = round(sum(c.get("pl_usd") or 0.0 for c in mine), 2)
    unrealized = round(sum(p["pl_usd"] or 0.0 for p in positions), 2)
    series, run = [], 0.0
    for c in mine:
        run += c.get("pl_usd") or 0.0
        series.append([c.get("closed_ts"), round(run, 2)])
    if positions:
        series.append([round(time.time(), 3), round(run + unrealized, 2)])
    return {"pl_usd": round(realized + unrealized, 2), "realized_usd": realized, "unrealized_usd": unrealized,
            "trades": len(mine) + len(positions),
            "skipped": sum(1 for e in events if e["outcome"] == "skipped"), "series": series}


def _state(name: str, st: dict[str, Any], status: dict[str, Any], on_air: bool | None,
           left_ts: float | None, held: int = 0) -> dict[str, str]:
    if settings.error():
        return {"tone": "bad", "text": str(settings.error())}
    if not st["key"]:
        if held:
            return {"tone": "warn", "text": f"Key off · no orders: {held} held, not sold until it is on"}
        return {"tone": "off", "text": "Key off"}
    got = status.get("answer") or {}
    if got.get("state") not in (None, "ok"):
        return {"tone": "bad", "text": f"The feed is not answering ({got.get('error') or got.get('state')})"}
    if on_air is False:
        return {"tone": "warn", "text": f"Off air since {hms(left_ts)} ET"}
    can = status.get("can_open") or {}
    if can and not can.get("ok"):
        return {"tone": "warn", "text": str(can.get("why"))}
    age = got.get("read_age_sec")
    read = f"read {age:.0f} s ago" if isinstance(age, (int, float)) else "waiting for the feed"
    return {"tone": "ok", "text": f"On air · {read}" if on_air else f"Watching · {read}"}


def build() -> dict[str, Any]:
    now = time.time()
    status = watcher.status()
    got = status.get("answer") or {}
    hosts_state = status.get("hosts_state") or {}
    positions = book.positions()
    closed = book.closed_today()
    events = _events()
    used = used_by_host(positions)
    asks = watcher.asks()
    names = list(dict.fromkeys([*(got.get("order") or []), *(status.get("names") or []), *settings.named(),
                                *(p["host"] for p in positions.values()), *(c["host"] for c in closed)]))
    their = got.get("prices") or {}
    lefts = got.get("left") or {}
    faces = set(got.get("faces") or [])
    cards = []
    for name in names:
        st = settings.of(name)
        mine = [_position(p, their) for p in positions.values() if p["host"] == name]
        hs = hosts_state.get(name) or {}
        on_air = hs.get("on_air")
        ev = events.get(name, [])
        cards.append({
            "name": name,
            "face": FACE_PATH.format(date=got.get("date"), name=name) if name in faces and got.get("date") else None,
            "on_air": on_air, "left_ts": lefts.get(name),
            "settings": {**st, "mode": mode_of(st["entry"], st["exit"])},
            "state": _state(name, st, status, on_air, lefts.get(name), len(mine)),
            "allowance": {"used_usd": round(used.get(name, 0.0), 2), "of_usd": st["allowance_usd"]},
            "today": _today(name, mine, closed, ev),
            "positions": mine,
            "asks": [_ask(a, now) for a in asks if a["host"] == name],
            "events": ev[:LT_EVENTS_SHOWN],
        })
    can = status.get("can_open")
    from sim.mode import venue

    return {"schema_version": LT_SCHEMA_VERSION, "generated_at": round(now, 3), "enabled": _enabled(),
            "venue": LT_VENUE, "desk_venue": venue(), "can_trade": can or {"ok": False, "code": None,
                                                                           "why": "the watcher has not run yet"},
            "sell_all_at": settings.sell_all_at(), "sell_all_ts": watcher.sell_all_ts(now),
            "watcher": {"running": bool(status.get("running")), "pass_ts": status.get("pass_ts"),
                        "idle": bool(status.get("idle")), "feed": _feed(got), "text": _watcher_text(status, got)},
            "settings_error": settings.error(), "book_error": book.error(),
            "hosts": cards, "defaults": settings.defaults(), "bounds": settings.bounds()}


def asks_now() -> dict[str, Any]:
    """``GET /api/bot/live-traders/asks``: the asks waiting on the operator and what the bot holds, cheap."""
    now = time.time()
    held = [{"host": p["host"], "symbol": p["symbol"], "side": p["side"], "qty": p["qty"], "state": p["state"]}
            for p in book.positions().values()]
    return {"schema_version": LT_SCHEMA_VERSION, "generated_at": round(now, 3),
            "asks": [{**_ask(a, now), "host": a["host"]} for a in watcher.asks()], "held": held}


def _ask(a: dict[str, Any], now: float) -> dict[str, Any]:
    keep = ("id", "row_id", "symbol", "side", "step", "their_price", "qty", "limit", "stop", "created_ts",
            "expires_ts", "text", "approved", "answered")
    return {**{k: a.get(k) for k in keep}, "seconds_left": max(0, round(a["expires_ts"] - now))}


def _feed(got: dict[str, Any]) -> dict[str, Any]:
    return {"state": got.get("state") or ("off" if not _enabled() else None), "error": got.get("error"),
            "read_age_sec": got.get("read_age_sec"), "behind_sec": got.get("behind_sec"),
            "bar_visible": got.get("bar_visible"), "live": got.get("live")}


def _watcher_text(status: dict[str, Any], got: dict[str, Any]) -> str:
    if not status.get("running"):
        return "The watcher is not running"
    if status.get("idle"):
        if got.get("state") not in (None, "ok"):
            why = got.get("error") or got.get("state")
            return f"Idle: no host's key is on -- the TraderTV feed is not answering ({why})"
        return "Idle: no host's key is on"
    if got.get("state") != "ok":
        return f"The TraderTV feed is not answering ({got.get('error') or got.get('state')})"
    age = got.get("read_age_sec")
    return f"Watching the bar, read {age:.0f} s ago" if isinstance(age, (int, float)) else "Watching the bar"


def _enabled() -> bool:
    from followed_traders import config

    return config.enabled()
