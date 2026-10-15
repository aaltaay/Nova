"""The bar's own moves the Live Trader bot must not trade on (ADR 055 amendment 2026-10-15). Pure.

Two screen behaviours look like trades and are not (bot.md, "The bar's own moves"):

- **A blank bar** (``blanks``). Every open position of a host -- two or more -- closes in the feed within
  ``LT_SWITCH_SEC`` while their bar reads empty on both sides: a display refresh, and the same positions come back
  about a minute later at their very averages. The closes of those rows wait up to ``LT_BLANK_HOLD_SEC``. Once the
  bar's first row is back and ``LT_BLANK_SETTLE_SEC`` has passed, a position back at its very average (side, stock,
  average to the cent) is the same position -- re-keyed, nothing sold, nothing bought -- and every row back inherits
  its old row's decision; a position not back is sold. Past the limit with the bar still empty, everything is sold.
- **A hand-over that lingers** (``returning``). After a host comes back on air, the bar can show the previous
  host's rows under their name tag until every slot switches at once. The rows the bar shows in the first
  ``LT_RETURN_FIRST_SEC`` after the return are not taken until every one of them has closed (the switch), or
  ``LT_RETURN_HOLD_SEC`` passes; then what is left is already open, as any row is.

Off air, the 10-minute rule, the sell-all time, the key and the Bot switch never wait on either: ``decide_closes``
judges them first. State lives in the decision's snapshot (memory only, a few hundred bytes a host):
``snap["blanks"][host]`` and ``snap["hosts"][host]["return"]``.
"""
from __future__ import annotations

from typing import Any

from bot.live_trader import feed_rows, rules
from bot.live_trader.constants_live_trader import (
    LT_BLANK_HOLD_SEC,
    LT_BLANK_SETTLE_SEC,
    LT_RETURN_FIRST_SEC,
    LT_RETURN_HOLD_SEC,
    LT_SWITCH_SEC,
)
from bot.live_trader.decide_closes import hms


def empty() -> dict[str, Any]:
    """One pass's word on the blanks: rows whose close waits, re-keys, sells and the hosts whose entries wait."""
    return {"held": {}, "rekeys": {}, "sold": {}, "hosts": {}}


def _on_bar(rows: Any) -> list[dict[str, Any]]:
    return [r for r in rows or () if not r.get("left_bar")]


def _avg(r: dict[str, Any]) -> float | None:
    p = r.get("price")
    return feed_rows.cent(float(p)) if isinstance(p, (int, float)) and p > 0 else None


def blank_of(h: dict[str, Any]) -> dict[str, Any] | None:
    """The host's newest blank: two or more rows that closed within ``LT_SWITCH_SEC`` of each other while no other
    row was open -- ``{t0, t1, rows: {row_id: {side, symbol, avg}}}`` -- or None."""
    rows = _on_bar(h.get("rows"))
    closed = [r for r in rows if r["status"] == "closed" and r.get("exit_ts") is not None]
    if len(closed) < 2:
        return None
    t1 = max(r["exit_ts"] for r in closed)
    group = [r for r in closed if t1 - r["exit_ts"] <= LT_SWITCH_SEC]
    if len(group) < 2 or any(_avg(r) is None for r in group):
        return None
    t0 = min(r["exit_ts"] for r in group)
    ids = {r["id"] for r in group}
    for r in rows:
        if r["id"] in ids or r["entry_ts"] >= t0:
            continue                                  # one of the blank's, or opened after it began (the bar back)
        if r["status"] != "closed" or r.get("exit_ts") is None or r["exit_ts"] >= t0:
            return None                               # a position the blank did not close: not the whole bar
    return {"t0": t0, "t1": t1,
            "rows": {r["id"]: {"side": r["side"], "symbol": r["symbol"], "avg": _avg(r)} for r in group}}


def _back(h: dict[str, Any], b: dict[str, Any]) -> list[dict[str, Any]]:
    return sorted((r for r in _on_bar(h.get("rows")) if r["status"] == "open" and r["entry_ts"] >= b["t0"]
                   and r["id"] not in b["rows"]), key=lambda r: r["entry_ts"])


def _same(old: dict[str, Any], r: dict[str, Any]) -> bool:
    shown = {feed_rows.cent(float(p)) for p in (r.get("entry_price"), r.get("price"))
             if isinstance(p, (int, float)) and p > 0}
    return r["side"] == old["side"] and r["symbol"] == old["symbol"] and old["avg"] in shown


def blanks(snap: dict[str, Any], answer: dict[str, Any], book: dict[str, dict[str, Any]], now: float,
           actions: list[dict[str, Any]]) -> dict[str, Any]:
    """This pass's blanks (``empty()``'s shape), the snapshot's ``blanks`` advanced; a note for each position whose
    sell starts to wait. With no read of the feed nothing is judged: closes wait for a read anyway."""
    out = empty()
    store = snap.setdefault("blanks", {})
    if answer["state"] != "ok":
        return out
    feed_now = answer.get("feed_now")
    for name, h in (answer.get("hosts") or {}).items():
        b = store.get(name)
        found = blank_of(h)
        if found is not None and (b is None or b["t1"] != found["t1"]):
            # Only a bar read empty (or one already back) is a blank; anything else is the host's own closes.
            holding = h.get("bar") == [] or bool(_back(h, found))
            b = store[name] = {**found, "since": now, "back_seen": None, "state": "holding" if holding else "done"}
            if holding:
                _tell(name, b, book, actions)
        if b is None or b["state"] != "holding":
            continue
        back = _back(h, b)
        elapsed = max(now - b["since"], feed_now - b["t1"] if feed_now is not None else 0.0)
        if back:
            if b["back_seen"] is None:
                b["back_seen"] = now
            settled = (feed_now is not None and feed_now - back[0]["entry_ts"] >= LT_BLANK_SETTLE_SEC
                       ) or now - b["back_seen"] >= LT_BLANK_SETTLE_SEC
            if settled or elapsed >= LT_BLANK_HOLD_SEC:
                _resolve(name, b, back, snap, out)
                continue
        elif elapsed >= LT_BLANK_HOLD_SEC:
            b["state"] = "done"
            for rid in b["rows"]:
                out["sold"][rid] = (f"{name}'s bar stayed empty {LT_BLANK_HOLD_SEC:.0f} s after it went blank at "
                                    f"{hms(b['t0'])} ET")
            continue
        why = (f"{name}'s whole bar went blank at {hms(b['t0'])} ET -- a refresh brings the same positions back at "
               f"their very averages: waiting up to {LT_BLANK_HOLD_SEC:.0f} s")
        out["hosts"][name] = why
        for rid in b["rows"]:
            out["held"][rid] = why
    return out


def _tell(name: str, b: dict[str, Any], book: dict[str, dict[str, Any]], actions: list[dict[str, Any]]) -> None:
    for pos in book.values():
        if pos["host"] == name and pos["row_id"] in b["rows"] and pos["state"] != "closing":
            actions.append({"kind": "note", "host": name, "pos_id": pos["id"], "row_id": pos["row_id"],
                            "symbol": pos["symbol"], "side": pos["side"], "step": "blank",
                            "change": {"kind": "close", "ts": b["t0"], "price": None},
                            "why": f"{name}'s whole bar went blank at {hms(b['t0'])} ET: the sell of "
                                   f"{pos['symbol']} waits up to {LT_BLANK_HOLD_SEC:.0f} s for the bar to come back"})


def _resolve(name: str, b: dict[str, Any], back: list[dict[str, Any]], snap: dict[str, Any],
             out: dict[str, Any]) -> None:
    """The bar is back: each old row matched to a row back at its very average, or sold."""
    b["state"] = "done"
    rows_state = snap.setdefault("hosts", {}).setdefault(name, {"rows": {}}).setdefault("rows", {})
    used: set[str] = set()
    for rid, old in b["rows"].items():
        at = f"{old['symbol']} {old['side']} at {rules.price_text(old['avg'])}"
        r = next((x for x in back if x["id"] not in used and _same(old, x)), None)
        if r is None:
            out["sold"][rid] = f"{name}'s bar came back after the blank without {at}"
            continue
        used.add(r["id"])
        out["rekeys"][rid] = (r["id"], f"{name}'s bar went blank and came back with {at}, its very average: the "
                                       "same position -- nothing sold, nothing bought")
        prior = rows_state.get(rid)
        if prior is not None and r["id"] not in rows_state:
            # The row back is the old one: its decision stands (a skip is not said twice, a take not bought twice).
            rows_state[r["id"]] = {**prior, "since": None, "groups_done": None, "ask_id": None}


def returning(hs: dict[str, Any], h: dict[str, Any], now: float, came_back: bool) -> dict[str, str]:
    """The rows whose take waits after the host's return, ``{row_id: why}``; ``hs["return"]`` advanced."""
    if came_back:
        hs["return"] = {"since": now, "rows": [], "window": True}
    ret = hs.get("return")
    if not ret:
        return {}
    rows = _on_bar(h.get("rows"))
    mine = [r for r in rows if r["id"] in ret["rows"]]
    if any(r["status"] != "open" for r in mine) or now - ret["since"] > LT_RETURN_FIRST_SEC:
        ret["window"] = False                         # a row closed: the switch began, nothing after it is stale
    if ret["window"]:
        ret["rows"] = sorted(set(ret["rows"]) | {r["id"] for r in rows if r["status"] == "open"})
        mine = [r for r in rows if r["id"] in ret["rows"]]
    held = [r for r in mine if r["status"] == "open"]
    if now - ret["since"] >= LT_RETURN_HOLD_SEC or (not ret["window"] and not held):
        hs["return"] = None
        return {}
    why = (f"{hms(ret['since'])} ET: back on air, the bar can show the previous host's rows under this name tag until "
           f"every slot switches at once -- not taken until the switch, {LT_RETURN_HOLD_SEC / 60:.0f} min at most")
    return {r["id"]: why for r in held}
