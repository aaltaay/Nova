"""When the Live Trader bot sells or covers what it holds (ADR 055 decision 2). Pure; ``decide`` calls it first.

A position is closed -- all of it -- for the first of: the sell-all time passed (never overnight); the feed has not
read the bar for ``LT_HIDDEN_SEC``; the bar has been hidden that long; the host went off air; the host's trade left
the bar. With a key off -- the Bot switch, the LiveTrader Bots key or the host's own (``ctx["keys_hold"]``) -- no
close is sent, not even this one (operator decision 2026-10-15: off places no order at all): it is said once and
made when the keys are back on, if its reason still stands. A feed row the feed reopened for
the same stock (its old one ``unknown`` or gone) is the same position, re-keyed, never sold and bought again; so
is one the feed closed and opened again in the same second (``_flipped``: a misread flipping between two readings of
one bar, #1010), and one back at its very average after the whole bar went blank (``decide_bar``), whose sell waits
for the bar.
The host's own reasons follow the Exit switch: with Exit on You the bot says so once and keeps the shares; the
clock's always close. Shapes: architecture/schema/bot.md ("The Live Trader bot").
"""
from __future__ import annotations

import math
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from bot.live_trader.constants_live_trader import LT_BLANK_BAR, LT_HIDDEN_SEC

ET = ZoneInfo("America/New_York")
HOST_REASONS = ("close", "off_air", "hidden", "lost")
TOLD_KEEP = 400


def hms(ts: float | None) -> str:
    return "?" if ts is None else datetime.fromtimestamp(ts, ET).strftime("%H:%M:%S")


def _shows(r: dict[str, Any], sym: str) -> bool:
    """The row's stock is ``sym``: as shown, or as the glued reading of a ticker check still ``checking`` (for a few
    seconds after a flip the row back reads under the glued ticker, RGT 112.08 for RGTI 12.08)."""
    ticker = r.get("ticker") or {}
    return r["symbol"] == sym or (ticker.get("state") == "checking" and ticker.get("other_symbol") == sym)


def _flipped(row: dict[str, Any], rows: list[dict[str, Any]], pos: dict[str, Any]) -> dict[str, Any] | None:
    """The open row the feed opened in the very second it closed ``row``, for the position's side and stock: the same
    position read again (the feed cannot close and open one stock in one read). None for a real close or a hand-over
    to another stock."""
    if row.get("exit_ts") is None:
        return None
    second = math.floor(row["exit_ts"])
    return next((r for r in sorted(rows, key=lambda x: x["entry_ts"])
                 if r["id"] != row["id"] and r["status"] == "open" and not r.get("left_bar")
                 and r["side"] == pos["side"] and math.floor(r["entry_ts"]) == second
                 and _shows(r, pos["symbol"])), None)


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
        back = _flipped(row, rows, pos)
        if back is not None:
            return "rekey", back["id"], (f"the feed closed {name}'s {sym} and opened it again at {hms(row['exit_ts'])} "
                                         "ET, the same second: the same position read again -- nothing sold, "
                                         "nothing bought")
        return "close", f"{name} closed {sym}", row.get("exit_ts") or now
    if again is not None:
        return "rekey", again["id"], None
    if row is None:
        return "lost", f"{sym} is no longer on {name}'s bar", now
    return "lost", f"the feed lost {name}'s {sym} (it saw it open again without a close)", now


def _reason(pos: dict[str, Any], answer: dict[str, Any], ctx: dict[str, Any], flags: dict[str, Any],
            snap: dict[str, Any]) -> tuple | None:
    now = ctx["now"]
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


def _no_hold(_host: str) -> None:
    return None


def _tell_once(snap: dict[str, Any], out: dict[str, Any], pos: dict[str, Any], change: dict[str, Any], key: str,
               why: str) -> None:
    """A close the bot does not make, said once per position, reason and cause."""
    if key in snap["told"]:
        return
    snap["told"] = (snap["told"] + [key])[-TOLD_KEEP:]
    out["actions"].append({"kind": "tell", "host": pos["host"], "pos_id": pos["id"], "row_id": pos["row_id"],
                           "symbol": pos["symbol"], "side": pos["side"], "change": change, "why": why})


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
        bar = flags.get("bar") or {}
        if kind in ("close", "lost") and pos["row_id"] in bar.get("held", {}):
            # A whole bar blank: the sell waits for it to come back. Said here, after every exit that never waits
            # (the operator's, the clock's, off air) has had its say -- never for a sell already sent.
            why = bar["held"][pos["row_id"]]
            out["waits"][pos["id"]] = {"symbol": pos["symbol"], "code": LT_BLANK_BAR, "text": why}
            out["actions"].append({"kind": "note", "host": pos["host"], "pos_id": pos["id"], "row_id": pos["row_id"],
                                   "symbol": pos["symbol"], "side": pos["side"], "step": "blank",
                                   "change": {"kind": "close", "ts": ts, "price": None},
                                   "why": f"{why} before selling {pos['symbol']}"})
            continue
        if kind in ("close", "lost") and pos["row_id"] in bar.get("rekeys", {}):
            kind, (words, why) = "rekey", bar["rekeys"][pos["row_id"]]
        elif kind == "rekey":
            why = ts                                  # the re-key's own words (``_row_reason``), or None
        else:
            why = None
            if kind in ("close", "lost"):
                words = bar.get("sold", {}).get(pos["row_id"], words)
        if kind == "rekey":
            out["actions"].append({"kind": "rekey", "pos_id": pos["id"], "row_id": words, "host": pos["host"],
                                   "symbol": pos["symbol"], "side": pos["side"], "why": why})
            continue
        change = {"kind": kind, "ts": ts, "price": None}
        hold = (ctx.get("keys_hold") or _no_hold)(pos["host"])
        if hold is not None:
            # A key is off: no order at all, not even this sell. Said once; the next pass with the keys on decides
            # again (operator decision 2026-10-15).
            out["waits"][pos["id"]] = {"symbol": pos["symbol"], "code": hold[0], "text": f"not sold: {hold[1]}"}
            _tell_once(snap, out, pos, change, f"{pos['id']}|{pos['row_id']}|{kind}|{hold[0]}",
                       f"{words}: not sold -- {hold[1]}")
            continue
        if kind in HOST_REASONS and ctx["settings"](pos["host"])["exit"] == "you":
            _tell_once(snap, out, pos, change, f"{pos['id']}|{pos['row_id']}|{kind}",
                       f"{words}: the exit is yours (Exit: You) -- the bot keeps its {pos['qty']:g} shares")
            continue
        out["actions"].append({"kind": "close", "host": pos["host"], "pos_id": pos["id"], "row_id": pos["row_id"],
                               "symbol": pos["symbol"], "side": pos["side"], "qty": pos["qty"], "why": words,
                               "change": change})
        if kind in ("off_air", "hidden"):
            rows = snap["hosts"].setdefault(pos["host"], {"rows": {}})["rows"]
            if pos["row_id"] in rows:
                rows[pos["row_id"]]["fate"] = "released"   # still on the bar later: already open
