"""``GET /api/agent/trader``: what the desk shows of Claude (ADR 068 decision 10). Read-only; never the holder token."""
from __future__ import annotations

import logging
from typing import Any

from agent_trader import clock
from agent_trader.constants_agent_trader import (
    AGENT_DAY_STOP_USD,
    AGENT_LEASE_SEC,
    AGENT_MAX_ENTRIES_A_DAY,
    AGENT_MAX_RISK_USD,
    AGENT_MAX_SHARES,
    AGENT_NAME,
    AGENT_SCHEMA_VERSION,
    AGENT_VENUE,
    SEAT_DONE,
    SEAT_IDLE,
    SEAT_IN,
    SEAT_OFF,
    SEAT_SET,
    SEAT_WAITING,
    SEAT_WATCHING,
    SEAT_YIELDED,
)

_EVENTS_SHOWN = 12
logger = logging.getLogger(__name__)


def state_of(st: dict[str, Any], *, holds_line: bool, positions: dict[str, float], working: int, breaks: int,
             done: bool) -> str:
    """The seat's one state, in the order the desk should say it."""
    if not st.get("holder"):
        return SEAT_OFF
    if positions:
        return SEAT_IN
    if st.get("yielded"):
        return SEAT_YIELDED
    if done:
        return SEAT_DONE
    if not st.get("symbol"):
        return SEAT_IDLE
    if not holds_line:
        return SEAT_WAITING
    return SEAT_SET if (working or breaks) else SEAT_WATCHING


def text_of(state: str, sym: str | None, pnl: float | None, line_why: str | None,
            buy_at: float | None = None) -> str:
    money = "" if pnl is None else f" {'+' if pnl >= 0 else '-'}${abs(pnl):,.2f}"
    at = "" if buy_at is None else f" {buy_at:.2f}" if buy_at >= 1 else f" {buy_at:.4f}"
    return {
        SEAT_OFF: f"{AGENT_NAME} · Off",
        SEAT_IDLE: f"{AGENT_NAME} · Looking for a stock",
        SEAT_WAITING: f"{AGENT_NAME} · Waiting for a Level 2 line" + (f" ({line_why})" if line_why else ""),
        SEAT_WATCHING: f"{AGENT_NAME} · Watching {sym}",
        SEAT_SET: f"{AGENT_NAME} · Buy set {sym}{at}",
        SEAT_IN: f"{AGENT_NAME} · In {sym}{money}",
        SEAT_YIELDED: f"{AGENT_NAME} · Paused by you",
        SEAT_DONE: f"{AGENT_NAME} · Done for today{money}",
    }[state]


def _buy_at(sym: str | None, breaks: list[dict[str, Any]], working: list[dict[str, Any]]) -> float | None:
    """The price Claude's buy waits at: an armed break's trigger, else the resting entry's limit."""
    for b in breaks:
        if b.get("symbol") == sym and b.get("trigger") is not None:
            return float(b["trigger"])
    for r in working:
        if (r.get("symbol") == sym and str(r.get("side") or "").upper() == "BUY"
                and r.get("leg_role") in (None, "parent") and r.get("limit_price") is not None):
            return float(r["limit_price"])
    return None


def _order(row: dict[str, Any]) -> dict[str, Any]:
    return {k: row.get(k) for k in ("order_id", "symbol", "side", "order_type", "qty", "limit_price", "stop_price",
                                    "leg_role", "status", "parent_id")}


def status(now: float | None = None) -> dict[str, Any]:
    from agent_trader import ledger, lines, reflexes, rules, seat, watcher
    from ibkr import depth

    t = clock.now() if now is None else now
    st = seat.snapshot()
    sym = st.get("symbol")
    read_error, fills, working, positions, pnl, entries = None, [], [], {}, None, 0
    try:
        fills = ledger.fills_today()
        working = ledger.working()
        positions = ledger.positions(fills)
        pnl = ledger.day_pnl(fills)
        entries = ledger.entries_today(fills, working)
    except ledger.ReadError:
        logger.warning("AGENT status: Paper could not be read", exc_info=True)
        read_error = ledger.UNREAD_TEXT
    done = pnl is not None and rules.day_refusal(entries, pnl) is not None
    holds = bool(sym) and lines.holds_depth(sym)
    breaks = st.get("breaks") or []
    state = state_of(st, holds_line=holds, positions=positions, working=len(working), breaks=len(breaks), done=done)
    shown = next(iter(positions), None) or sym
    marks = {}
    for held in positions:
        try:
            marks[held] = ledger.paper().ledger.mark_of(held)
        except Exception:
            marks[held] = None
    beat = st.get("beat_at")
    return {
        "schema_version": AGENT_SCHEMA_VERSION, "generated_at": t, "name": AGENT_NAME, "venue": AGENT_VENUE,
        "state": state, "text": text_of(state, shown, pnl, watcher.line_why(), _buy_at(shown, breaks, working)),
        "on": bool(st.get("holder")), "since": st.get("since"), "beat_at": beat,
        "lease_until": (float(beat) + AGENT_LEASE_SEC) if beat else None, "lapsed": seat.lapsed(t),
        "yielded": bool(st.get("yielded")), "symbol": sym,
        "line": {"symbol": lines.held_symbol(), "depth": holds, "tape": bool(sym) and lines.holds_tape(sym),
                 "why_not": watcher.line_why(), "desk_lines": lines.desk_lines(), "desk_cap": lines.desk_cap(),
                 "all_lines": depth.subscribed_symbols()},
        "positions": [{"symbol": s, "qty": q, "mark": marks.get(s)} for s, q in positions.items()],
        "working": [_order(r) for r in working],
        "breaks": breaks,
        "reflexes": [{**r, "text": reflexes.text(r)} for r in st.get("reflexes") or []],
        "today": {"entries": entries, "max_entries": AGENT_MAX_ENTRIES_A_DAY, "pnl": pnl,
                  "day_stop": AGENT_DAY_STOP_USD, "fills": len(fills)},
        "limits": {"max_shares": AGENT_MAX_SHARES, "max_risk_usd": AGENT_MAX_RISK_USD},
        "note": st.get("note"),
        "events": list(reversed(st.get("events") or []))[:_EVENTS_SHOWN],
        "read_error": read_error,
    }
