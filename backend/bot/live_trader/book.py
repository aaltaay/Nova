"""What the Live Trader bot holds on Paper: its positions, their orders in flight, and today's closed ones.

Persisted: ``live-trader-book.json`` in the operator cache (``LT_BOOK_FILE``). Owner: this module -- read once, written
through a temp file and a rename after every change, so a restart resumes managing what the bot holds.
Invalidation: the desk's day (04:00 ET): positions from another day are sold at once (never overnight) and today's
closed list starts empty; a ``schema_version`` other than ``LT_BOOK_SCHEMA_VERSION``, or a file that cannot be read,
is refused loud -- the bot then opens nothing (``error``) and the file is never overwritten.

A position is one host, side and stock (``feed_rows.position_id``): the shares the bot's own fills hold, what they
cost, its steps, the order in flight (an entry, an add or a close) and a short's buy stops. The shares are the bot's
alone: the operator's own Paper shares in the same stock are never counted or sold. Shapes:
architecture/schema/bot.md ("The Live Trader bot").
"""
from __future__ import annotations

import copy
import json
import logging
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

from bot.live_trader.constants_live_trader import LT_BOOK_FILE, LT_BOOK_SCHEMA_VERSION, LT_CLOSED_KEEP

logger = logging.getLogger(__name__)
EPS = 1e-9
NO_REENTRY_KINDS = ("outside", "stop")     # sold by someone else, or its buy stop: never bought back today

_lock = threading.RLock()
_book: dict[str, Any] | None = None
_error: str | None = None


def reset_for_tests() -> None:
    global _book, _error
    with _lock:
        _book, _error = None, None


def _path() -> Path:
    from paths import cache_dir

    return cache_dir() / LT_BOOK_FILE


def _empty(day: str | None) -> dict[str, Any]:
    return {"day": day, "positions": {}, "closed": []}


def _load_locked() -> dict[str, Any]:
    global _book, _error
    if _book is not None:
        return _book
    _book, _error = _empty(None), None
    path = _path()
    if not path.exists():
        return _book
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        _error = f"{path.name} could not be read ({type(exc).__name__}): the Live Trader bot opens nothing"
        logger.exception("Live Trader bot: %s", _error)
        return _book
    if not isinstance(raw, dict) or raw.get("schema_version") != LT_BOOK_SCHEMA_VERSION:
        version = raw.get("schema_version") if isinstance(raw, dict) else None
        _error = (f"{path.name} has schema_version {version!r}, not {LT_BOOK_SCHEMA_VERSION}: refused, not "
                  "overwritten -- the Live Trader bot opens nothing")
        logger.error("Live Trader bot: %s", _error)
        return _book
    positions = {p["id"]: p for p in raw.get("positions") or [] if isinstance(p, dict) and p.get("id")}
    _book = {"day": raw.get("day"), "positions": positions,
             "closed": [c for c in raw.get("closed") or [] if isinstance(c, dict)][-LT_CLOSED_KEEP:]}
    return _book


def _save_locked() -> None:
    if _error is not None or _book is None:
        return
    path = _path()
    payload = {"schema_version": LT_BOOK_SCHEMA_VERSION, "day": _book["day"],
               "positions": list(_book["positions"].values()), "closed": _book["closed"][-LT_CLOSED_KEEP:]}
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f)
        os.replace(tmp, path)
    except OSError:
        logger.exception("Live Trader bot: %s was not written -- what the bot holds is in memory only", path)


def error() -> str | None:
    with _lock:
        _load_locked()
        return _error


def positions() -> dict[str, dict[str, Any]]:
    with _lock:
        return copy.deepcopy(_load_locked()["positions"])


def get(pos_id: str) -> dict[str, Any] | None:
    with _lock:
        pos = _load_locked()["positions"].get(pos_id)
        return copy.deepcopy(pos) if pos else None


def closed_today() -> list[dict[str, Any]]:
    with _lock:
        return copy.deepcopy(_load_locked()["closed"])


def no_reentry() -> set[str]:
    """Rows the bot must not enter again today: sold by someone else, or stopped out."""
    with _lock:
        return {c["row_id"] for c in _load_locked()["closed"] if c.get("kind") in NO_REENTRY_KINDS}


def roll_day(today: str) -> list[dict[str, Any]]:
    """Start ``today``'s book; the positions still held from another day, to be sold at once."""
    with _lock:
        book = _load_locked()
        if _error is not None or book["day"] == today:
            return []
        stale = [copy.deepcopy(p) for p in book["positions"].values()] if book["day"] is not None else []
        book["day"], book["closed"] = today, []
        _save_locked()
        return stale


# -- steps -----------------------------------------------------------------------------------------
def step_sent(action: dict[str, Any], *, order_id: int | None, stop_id: int | None, now: float) -> None:
    """A step went out: its position (made when it is the first), the order in flight, a short's buy stop."""
    with _lock:
        book = _load_locked()
        pos = book["positions"].get(action["pos_id"])
        if pos is None:
            pos = book["positions"][action["pos_id"]] = {
                "id": action["pos_id"], "host": action["host"], "row_id": action["row_id"],
                "symbol": action["symbol"], "side": action["side"], "venue": "paper", "qty": 0.0, "cost_usd": 0.0,
                "steps": 0, "adds_followed": 0, "opened_ts": now, "state": "entering", "order": None,
                "stop_order_ids": [], "fills": [], "exit_fills": [], "close": None,
                "feed": {"ts": action["change"]["ts"], "price": action["change"]["price"]}}
        if action["step"] == "add":
            pos["adds_followed"] += 1
        pos["state"] = "entering"
        pos["order"] = {"id": order_id, "step": action["step"], "sent_ts": now, "qty": action["qty"],
                        "limit": action["limit"], "stop": action.get("stop"), "change": action["change"]}
        if stop_id is not None:
            pos["stop_order_ids"].append(int(stop_id))
        _save_locked()


def step_refused(pos_id: str) -> None:
    """A step the door refused: a new position is forgotten, an add leaves the position as it was."""
    with _lock:
        book = _load_locked()
        pos = book["positions"].get(pos_id)
        if pos is None:
            return
        if pos["qty"] <= EPS:
            del book["positions"][pos_id]
        else:
            pos.update(state="open", order=None)
            if pos["adds_followed"] > 0:
                pos["adds_followed"] -= 1
        _save_locked()


def step_done(pos_id: str, *, filled: float, price: float | None, ts: float | None, basis: str | None) -> None:
    """The step's order ended: its shares (any) join the position; unfilled, a new position is forgotten."""
    with _lock:
        book = _load_locked()
        pos = book["positions"].get(pos_id)
        if pos is None or pos["order"] is None:
            return
        order = pos["order"]
        if filled > EPS and price is not None:
            pos["qty"] += filled
            pos["cost_usd"] = round(pos["cost_usd"] + filled * price, 4)
            pos["steps"] += 1
            pos["fills"].append({"step": order["step"], "qty": filled, "price": price, "ts": ts,
                                 "order_id": order["id"], "basis": basis, "change": order.get("change")})
        elif order["step"] == "add" and pos["adds_followed"] > 0:
            pos["adds_followed"] -= 1
        pos.update(state="open", order=None)
        if pos["qty"] <= EPS and not pos["fills"]:
            del book["positions"][pos_id]
        _save_locked()


def rekey(pos_id: str, row_id: str) -> None:
    with _lock:
        pos = _load_locked()["positions"].get(pos_id)
        if pos is not None:
            pos["row_id"] = row_id
            _save_locked()


# -- closes ----------------------------------------------------------------------------------------
def close_sent(pos_id: str, *, order_id: int | None, kind: str, why: str, now: float, qty: float) -> None:
    with _lock:
        pos = _load_locked()["positions"].get(pos_id)
        if pos is None:
            return
        tries = int((pos.get("close") or {}).get("tries") or 0) + 1
        pos["state"] = "closing"
        pos["close"] = {"order_id": order_id, "kind": kind, "why": why, "sent_ts": now, "qty": qty, "tries": tries}
        _save_locked()


def close_failed(pos_id: str, *, now: float, error: str) -> int:
    """A close that did not fill or was refused: the position is open again (its reason closes it again);
    returns the tries so far."""
    with _lock:
        pos = _load_locked()["positions"].get(pos_id)
        if pos is None:
            return 0
        close = dict(pos.get("close") or {})
        close.update(order_id=None, error=error, failed_ts=now)
        pos.update(state="open", close=close)
        _save_locked()
        return int(close.get("tries") or 0)


def close_filled(pos_id: str, *, qty: float, price: float | None, ts: float | None, order_id: int | None,
                 kind: str, why: str) -> dict[str, Any] | None:
    """Shares the bot's close sold (or covered): the closed record when none are left."""
    with _lock:
        book = _load_locked()
        pos = book["positions"].get(pos_id)
        if pos is None:
            return None
        pos["exit_fills"].append({"qty": qty, "price": price, "ts": ts, "order_id": order_id, "kind": kind})
        return _reduce_locked(book, pos, qty, kind=kind, why=why, ts=ts)


def reduce(pos_id: str, qty: float, *, kind: str, why: str, ts: float | None,
           price: float | None = None, order_id: int | None = None) -> dict[str, Any] | None:
    """Shares that left the position some other way (sold outside the bot, a buy stop, the day cover)."""
    with _lock:
        book = _load_locked()
        pos = book["positions"].get(pos_id)
        if pos is None:
            return None
        pos["exit_fills"].append({"qty": qty, "price": price, "ts": ts, "order_id": order_id, "kind": kind})
        return _reduce_locked(book, pos, qty, kind=kind, why=why, ts=ts)


def forget(pos_id: str, *, kind: str, why: str, ts: float | None) -> dict[str, Any] | None:
    """A position whose shares are gone already: closed as it stands."""
    with _lock:
        book = _load_locked()
        pos = book["positions"].get(pos_id)
        if pos is None:
            return None
        return _reduce_locked(book, pos, pos["qty"], kind=kind, why=why, ts=ts)


def _reduce_locked(book: dict[str, Any], pos: dict[str, Any], qty: float, *, kind: str, why: str,
                   ts: float | None) -> dict[str, Any] | None:
    held = pos["qty"]
    sold = min(max(qty, 0.0), held)
    if held > EPS:
        pos["cost_usd"] = round(pos["cost_usd"] * (held - sold) / held, 4)
    pos["qty"] = round(held - sold, 6)
    if pos["qty"] > EPS:
        pos.update(state="open", close=None)
        _save_locked()
        return None
    done = {**copy.deepcopy(pos), "state": "closed", "closed_ts": ts, "kind": kind, "why": why,
            "pl_usd": realized(pos)}
    del book["positions"][pos["id"]]
    book["closed"] = (book["closed"] + [done])[-LT_CLOSED_KEEP:]
    _save_locked()
    return done


def realized(pos: dict[str, Any]) -> float | None:
    """The position's closed shares' P/L from the bot's own fills: what the exits got less what those shares cost
    (a short the other way); None when an exit's price is unknown."""
    bought = sum(f["qty"] for f in pos.get("fills") or [])
    cost = sum(f["qty"] * f["price"] for f in pos.get("fills") or [])
    exits = pos.get("exit_fills") or []
    if not bought or not exits or any(e.get("price") is None for e in exits):
        return None if exits and any(e.get("price") is None for e in exits) else 0.0
    sold = sum(e["qty"] for e in exits)
    got = sum(e["qty"] * e["price"] for e in exits)
    basis = cost / bought * sold
    pl = got - basis if pos["side"] == "long" else basis - got
    return round(pl, 2)
