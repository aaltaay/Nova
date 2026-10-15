"""When the Live Trader bot sells or covers what it holds (ADR 055 decision 2). Pure; ``decide`` calls it first.

A position is closed -- all of it -- for the first of: the operator turned its host's key off, or the Bot switch
off; the sell-all time passed (never overnight); the feed has not read the bar for ``LT_HIDDEN_SEC``; the bar
has been hidden that long; the host went off air; the host's trade left the bar. A feed row the feed reopened for
the same stock (its old one ``unknown`` or gone) is the same position, re-keyed, never sold and bought again.
The host's own reasons follow the Exit switch: with Exit on You the bot says so once and keeps the shares; the
operator's and the clock's always close. Shapes: architecture/schema/bot.md ("The Live Trader bot").
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from bot.live_trader.constants_live_trader import LT_HIDDEN_SEC

ET = ZoneInfo("America/New_York")
HOST_REASONS = ("close", "off_air", "hidden", "lost")
TOLD_KEEP = 400


def hms(ts: float | None) -> str:
    return "?" if ts is None else datetime.fromtimestamp(ts, ET).strftime("%H:%M:%S")


def _row_reason(pos: dict[str, Any], host: dict[str, Any] | None, now: float) -> tuple | None:
    """Why the host's own bar closes ``pos``, a re-key, or None while its trade is still open."""
    name, sym = pos["host"], pos["symbol"]
    if host is None:
        return "lost", f"{name}'s trades are not in the feed's day", now
    if host.get("left_ts") is not None:
        return ("off_air", f"{name} went off air at {hms(host['left_ts'])} ET (another host on the bar 60 s)",
                host["left_ts"])
    rows = host.get("rows") or []
    row = next((r for r in rows if r["id"] == pos["row_id"]), None)
    if row is not None and row["status"] == "open" and not row.get("left_bar"):
        return None
    again = next((r for r in rows if r["id"] != pos["row_id"] and r["status"] == "open" and not r.get("left_bar")
                  and r["side"] == pos["side"] and r["symbol"] == sym), None)
    if row is not None and row["status"] == "closed":
        return "close", f"{name} closed {sym}", row.get("exit_ts") or now
    if again is not None:
        return "rekey", again["id"], None
    if row is None:
        return "lost", f"{sym} is no longer on {name}'s bar", now
    return "lost", f"the feed lost {name}'s {sym} (it saw it open again without a close)", now


def _reason(pos: dict[str, Any], answer: dict[str, Any], ctx: dict[str, Any], flags: dict[str, Any],
            snap: dict[str, Any]) -> tuple | None:
    now, req = ctx["now"], ctx.get("requests") or {}
    if pos["host"] in (req.get("sell_hosts") or {}):
        return "key_off", f"you turned {pos['host']}'s key off", now
    if req.get("sell_all"):
        return "bot_off", "you turned the Bot switch off", now
    sell_ts = ctx.get("sell_all_ts")
    if sell_ts is not None and now >= sell_ts:
        return "sell_all", f"it is {hms(sell_ts)[:5]} ET: the bot never holds overnight", sell_ts
    if flags["blind"]:
        since = snap["blind_since"] if snap["blind_since"] is not None else now
        return "hidden", f"the feed has not read the bar for {minutes(flags['silent'])}", since
    if flags["hidden"]:
        return "hidden", f"the bar has been hidden for {minutes(LT_HIDDEN_SEC)}", snap["hidden_since"]
    if answer["state"] != "ok":
        return None                                   # no read to judge the bar by: hold until there is one
    # A late read is still a true one: what the feed saw close, closed (a close is never held for a doubt).
    return _row_reason(pos, (answer.get("hosts") or {}).get(pos["host"]), now)


def minutes(sec: float) -> str:
    return f"{max(sec, 0) / 60:.0f} min"


def closes(snap: dict[str, Any], answer: dict[str, Any], book: dict[str, dict[str, Any]], ctx: dict[str, Any],
           flags: dict[str, Any], out: dict[str, Any]) -> None:
    for pos in sorted(book.values(), key=lambda p: p.get("opened_ts") or 0):
        if pos["state"] == "closing":
            continue
        found = _reason(pos, answer, ctx, flags, snap)
        if found is None:
            continue
        kind, words, ts = found
        if kind == "rekey":
            out["actions"].append({"kind": "rekey", "pos_id": pos["id"], "row_id": words, "host": pos["host"],
                                   "symbol": pos["symbol"], "side": pos["side"]})
            continue
        change = {"kind": kind, "ts": ts, "price": None}
        if kind in HOST_REASONS and ctx["settings"](pos["host"])["exit"] == "you":
            key = f"{pos['id']}|{pos['row_id']}|{kind}"
            if key not in snap["told"]:
                snap["told"] = (snap["told"] + [key])[-TOLD_KEEP:]
                out["actions"].append({"kind": "tell", "host": pos["host"], "pos_id": pos["id"],
                                       "row_id": pos["row_id"], "symbol": pos["symbol"], "side": pos["side"],
                                       "change": change,
                                       "why": f"{words}: the exit is yours (Exit: You) -- the bot keeps its "
                                              f"{pos['qty']:g} shares"})
            continue
        out["actions"].append({"kind": "close", "host": pos["host"], "pos_id": pos["id"], "row_id": pos["row_id"],
                               "symbol": pos["symbol"], "side": pos["side"], "qty": pos["qty"], "why": words,
                               "change": change})
        if kind in ("off_air", "hidden"):
            rows = snap["hosts"].setdefault(pos["host"], {"rows": {}})["rows"]
            if pos["row_id"] in rows:
                rows[pos["row_id"]]["fate"] = "released"   # still on the bar later: already open
