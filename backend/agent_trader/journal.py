"""Claude's trade journal (ADR 068 decision 15): each trade's why, the book and tape at entry and exit, how it ended,
and its P&L -- so the seat's forward trial can be read back trade by trade.

A trade opens on the first watcher pass that sees Claude hold shares in a stock and closes on the first that sees it
flat. Its why is the note Claude sent with its order (``note_why``); how it ended is the closing fill's leg (``stop``,
``target``) or the reason the closer gave first (``note_exit``: the guard, a reflex, Claude's close, the day's close,
a quiet lease, Stop Claude), else ``nova`` when shares Nova sold under another origin (the loss limit's Auto sell,
KILL) ended it, else ``unknown``. P&L is Claude's fills in the trade, fees included, plus shares Nova sold for it at
the price those closes got.

Owner: ``backend/.cache/agent-journal/<YYYY-MM-DD>.json`` (``schema_version`` 1, the trades closed that trading day,
written whole and atomically) and the open trades (in memory; a restart opens a held position again from the book it
finds, its entry snapshot then taken late and said so with ``entry.late``).
"""
from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any

from agent_trader.constants_agent_trader import (
    AGENT_JOURNAL_BOOK_ROWS,
    AGENT_JOURNAL_DIR,
    AGENT_JOURNAL_PRINTS_MAX,
    AGENT_JOURNAL_PRINTS_SEC,
    AGENT_SCHEMA_VERSION,
)

logger = logging.getLogger(__name__)
_PRINT_KEYS = ("ts", "price", "size", "bid", "ask")
_lock = threading.Lock()
_open: dict[str, dict[str, Any]] = {}
_whys: dict[str, str] = {}
_exits: dict[str, tuple[str, str]] = {}
_written: set[tuple[str, float]] | None = None   # (symbol, opened_at) of trades written today (read back at start)
_started = False                   # the first pass after a start marks held positions late


def reset_for_tests() -> None:
    global _started, _written
    with _lock:
        _open.clear()
        _whys.clear()
        _exits.clear()
        _started, _written = False, None


def folder() -> Path:
    from paths import cache_dir

    return cache_dir() / AGENT_JOURNAL_DIR


def path_for(day: str) -> Path:
    return folder() / f"{day}.json"


def note_why(symbol: str, why: str) -> None:
    """The one line Claude sent with the order that may open a trade in ``symbol``."""
    with _lock:
        _whys[symbol.upper()] = str(why)


def note_exit(symbol: str, reason: str, detail: str) -> None:
    """Why a close of ``symbol`` was sent (the first reason given wins until the trade is written)."""
    with _lock:
        _exits.setdefault(symbol.upper(), (reason, detail))


def snapshot(book: dict[str, Any] | None, prints: list[dict[str, Any]], at: float) -> dict[str, Any]:
    """The book's top rows and the last prints, as the trade saw them."""
    rows = AGENT_JOURNAL_BOOK_ROWS
    recent = [{k: p.get(k) for k in _PRINT_KEYS} for p in prints if float(p.get("ts") or 0.0) >= at - AGENT_JOURNAL_PRINTS_SEC]
    return {"at": at, "bids": list((book or {}).get("bids") or [])[:rows], "asks": list((book or {}).get("asks") or [])[:rows],
            "l1_fallback": bool((book or {}).get("l1_fallback")), "prints": recent[-AGENT_JOURNAL_PRINTS_MAX:]}


def _side(row: dict[str, Any]) -> str:
    return str(row.get("side") or "").upper()


def _mine(fills: list[dict[str, Any]], sym: str, since: float) -> list[dict[str, Any]]:
    return [r for r in fills if str(r.get("symbol") or "").upper() == sym and float(r.get("fill_ts") or 0.0) >= since]


def open_trade(sym: str, fills: list[dict[str, Any]], snap: dict[str, Any], now: float, *, late: bool) -> None:
    from agent_trader import guard

    entry, opened = guard.entry_of(fills, sym)
    with _lock:
        _open[sym] = {"symbol": sym, "opened_at": opened or now, "entry_price": entry, "why": _whys.pop(sym, None),
                      "entry": {**snap, "late": late}}
        _exits.pop(sym, None)


def cycles(fills: list[dict[str, Any]], sym: str) -> list[tuple[float, float | None]]:
    """``(opened, closed)`` of each of Claude's positions in ``sym`` from its own fills (time order), flat to flat;
    ``closed`` is None while it is open."""
    out: list[tuple[float, float | None]] = []
    qty, opened = 0.0, None
    mine = [r for r in fills if str(r.get("symbol") or "").upper() == sym]
    for r in sorted(mine, key=lambda r: (float(r.get("fill_ts") or 0.0), _side(r) != "BUY")):   # a tie: the buy first
        n, ts = float(r.get("filled_qty") or 0.0), float(r.get("fill_ts") or 0.0)
        if _side(r) == "BUY":
            if qty <= 1e-9:
                opened = ts
            qty += n
        else:
            qty = max(0.0, qty - n)
            if qty <= 1e-9 and opened is not None:
                out.append((opened, ts))
                opened = None
    if opened is not None:
        out.append((opened, None))
    return out


def close_trade(sym: str, fills: list[dict[str, Any]], snap: dict[str, Any], now: float,
                nova_sold: tuple[float, float | None] | None = None, *, opened: float | None = None,
                closed: float | None = None) -> dict[str, Any] | None:
    """Write the trade: its fills, how it ended and its P&L. ``nova_sold``: (shares, price) Nova sold for Claude.

    ``opened`` / ``closed``: a cycle the fills show complete. One no pass saw held (it opened and closed between two
    passes, or the guard closed it on the pass that first saw it) is written too, with no entry snapshot."""
    with _lock:
        mine = _open.get(sym)
        if mine is not None and (opened is None or float(mine["opened_at"]) == float(opened)):
            trade = _open.pop(sym)
        elif opened is not None:
            trade = {"symbol": sym, "opened_at": opened, "entry_price": None, "why": _whys.pop(sym, None),
                     "entry": None}
        else:
            return None
        given = _exits.pop(sym, None)
    end = float("inf") if closed is None else float(closed)
    rows = [r for r in _mine(fills, sym, float(trade["opened_at"])) if float(r.get("fill_ts") or 0.0) <= end]
    if trade.get("entry_price") is None:
        buys = [r for r in rows if _side(r) == "BUY"]
        n = sum(float(r.get("filled_qty") or 0.0) for r in buys)
        trade["entry_price"] = (sum(float(r.get("filled_qty") or 0.0) * float(r.get("avg_fill_price") or 0.0)
                                    for r in buys) / n) if n else None
    bought = sum(float(r.get("filled_qty") or 0.0) for r in rows if _side(r) == "BUY")
    sells = [r for r in rows if _side(r) != "BUY"]
    sold = sum(float(r.get("filled_qty") or 0.0) for r in sells)
    cash = fees = 0.0
    for r in rows:
        n, px = float(r.get("filled_qty") or 0.0), float(r.get("avg_fill_price") or 0.0)
        fee = float(((r.get("fees") or {}).get("total")) or 0.0)
        cash += (-n * px if _side(r) == "BUY" else n * px) - fee
        fees += fee
    if nova_sold and nova_sold[0] > 0:
        cash += nova_sold[0] * float(nova_sold[1] or 0.0)
    last = sells[-1] if sells else None
    leg = str((last or {}).get("leg_role") or "")
    if leg in ("stop", "target", "target2"):
        reason, detail = ("stop" if leg == "stop" else "target"), f"the bracket's {leg} filled"
    elif given:
        reason, detail = given
    elif nova_sold and nova_sold[0] > 0:
        reason, detail = "nova", "Nova sold Claude's shares under another origin (the loss limit, KILL or a margin call)"
    else:
        reason, detail = "unknown", "no close reason was given"
    exit_px = (sum(float(r.get("filled_qty") or 0.0) * float(r.get("avg_fill_price") or 0.0) for r in sells) / sold
               if sold else (nova_sold[1] if nova_sold else None))
    done = {**trade, "closed_at": closed if closed is not None else now, "shares": bought, "exit_price": exit_px, "exit_reason": reason,
            "exit_detail": detail, "exit": snap, "pnl": cash, "fees": fees, "fills": len(rows)}
    _append(done, now)
    with _lock:
        _seen().add((sym, float(trade["opened_at"])))
    return done


def _seen() -> set[tuple[str, float]]:
    """The trades written today, read back from the day's file once (caller holds the lock)."""
    global _written
    if _written is None:
        from agent_trader import clock
        from market import session_key_for_ts

        try:
            rows = read_day(session_key_for_ts(clock.now()))["trades"]
        except (OSError, ValueError):
            rows = []
        _written = {(str(r.get("symbol") or "").upper(), float(r.get("opened_at") or 0.0)) for r in rows}
    return _written


def _append(trade: dict[str, Any], now: float) -> None:
    from capture.manifest_io import write_json_atomic
    from market import session_key_for_ts

    day = session_key_for_ts(now)
    target = path_for(day)
    try:
        doc = read_day(day)
        doc["trades"].append(trade)
        target.parent.mkdir(parents=True, exist_ok=True)
        write_json_atomic(target, doc)
    except (OSError, ValueError):
        logger.exception("AGENT journal: could not write %s; the trade on %s is in this log line: %s", target,
                         trade.get("symbol"), json.dumps(trade, default=str)[:2000])


def read_day(day: str) -> dict[str, Any]:
    """The day's written trades; a missing file is an empty day, a file of another schema is refused (logged)."""
    target = path_for(day)
    blank = {"schema_version": AGENT_SCHEMA_VERSION, "day": day, "trades": []}
    if not target.exists():
        return blank
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        logger.exception("AGENT journal: %s could not be read", target)
        raise
    if not isinstance(raw, dict) or raw.get("schema_version") != AGENT_SCHEMA_VERSION:
        raise ValueError(f"{target.name} has schema {raw.get('schema_version') if isinstance(raw, dict) else None}")
    return raw


def open_trades() -> list[dict[str, Any]]:
    with _lock:
        return [json.loads(json.dumps(t)) for t in _open.values()]


async def run(t: float) -> None:
    """Open and close trades from Claude's positions (the watcher, every pass)."""
    global _started
    from agent_trader import ledger, seat, watcher
    from ibkr import depth

    try:
        fills = ledger.fills_today()
        held = {s: q for s, q in ledger.positions(fills).items() if q > 0}
    except ledger.ReadError:
        logger.warning("AGENT journal: Paper could not be read; written next pass", exc_info=True)
        return
    late, _started = not _started, True
    done_now: list[dict[str, Any] | None] = []
    for sym in sorted({str(r.get("symbol") or "").upper() for r in fills}):
        for opened, closed in cycles(fills, sym):
            with _lock:
                written = (sym, opened) in _seen()
            if closed is None or written:
                continue
            snap = snapshot(depth.current_book(sym), await watcher._recent_prints(sym, t), t)
            done_now.append(close_trade(sym, fills, {**snap, "late": t - closed > 1.0}, t, opened=opened,
                                        closed=closed))
    for sym in [s for s in held if s not in _open]:
        snap = snapshot(depth.current_book(sym), await watcher._recent_prints(sym, t), t)
        open_trade(sym, fills, snap, t, late=late)
    for sym in [s for s in list(_open) if s not in held]:
        snap = snapshot(depth.current_book(sym), await watcher._recent_prints(sym, t), t)
        done_now.append(close_trade(sym, fills, snap, t, nova_sold=_nova_sold(sym, fills)))
    for done in [d for d in done_now if d is not None]:
        pnl = float(done["pnl"])
        seat.event("close", f"trade on {done['symbol']} closed {'+' if pnl >= 0 else '-'}${abs(pnl):,.2f}: "
                   f"{done['exit_reason']} ({done['exit_detail']})", t)


def _nova_sold(sym: str, fills: list[dict[str, Any]]) -> tuple[float, float | None] | None:
    """Shares Claude bought in the trade that Nova sold under another origin, and the price those closes got."""
    from agent_trader import ledger

    trade = _open.get(sym) or {}
    rows = _mine(fills, sym, float(trade.get("opened_at") or 0.0))
    left = sum(float(r.get("filled_qty") or 0.0) * (1 if _side(r) == "BUY" else -1) for r in rows)
    if left <= 1e-9:
        return None
    try:
        return left, ledger._closed_for_claude(sym, float(trade.get("opened_at") or 0.0))
    except ledger.ReadError:
        return left, None
