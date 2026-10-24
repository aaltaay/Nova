"""A position the Live Trader bot holds, changed by its host past the plain add (ADR 055). Pure.

- ``sale``: the host sold part -- the bot's copy shrinks by the same share of it (``sizing``: their average moved
  away from the market), and the shares over its target sell once they are worth the host's lot (operator
  2026-10-22, "Their size, $500 lots"; it sold half, once, before): a ``close`` action with ``trim: true`` for
  ``act.close``, which covers a short by whole steps, each with its own buy stop.
- ``follow_target``: shares the bot holds over its target -- a sale made while a key was off, a cover left over --
  sell the pass the keys are on, as a held close does.
- ``key_off_adds``: the host's key is off -- each add of what the bot holds is a skip (``LT_KEY_OFF``).

The bar shows the host's average, never the shares they sold: an average that moved away from the market is a sale
their platform folded into it (``rules.sale_text``, ``LT_ADD_IS_SALE``). Shapes: architecture/schema/bot.md ("A sale
read as an add").
"""
from __future__ import annotations

from typing import Any

from bot.live_trader import feed_rows, rules, sizing
from bot.live_trader.constants_live_trader import (
    LT_ADD_IS_SALE,
    LT_DEFAULT_LOT_USD,
    LT_KEY_OFF,
    LT_SALE_LEAD_SEC,
    LT_UNDER_LOT,
)


def lot_of(st: dict[str, Any]) -> float:
    return float(st.get("lot_usd", LT_DEFAULT_LOT_USD))


def market_at(run: Any, symbol: str, ts: float | None) -> float | None:
    """The market when the host's change was made (``market.price_at``), else the market now."""
    got = run.ctx.get("price_at")
    price = got(symbol, ts) if got is not None and ts is not None else None
    return price if price is not None else feed_rows.reference_price(run.ctx["quote"](symbol))


def sale(run: Any, name: str, st: dict[str, Any], r: dict[str, Any], rs: dict[str, Any], pos: dict[str, Any],
         prev: float | None, g: dict[str, Any], change: dict[str, Any], index: int, *,
         held_why: str | None = None) -> None:
    """The host's partial sale ``g``: the bot's target shrinks by the share they sold; the shares over it sell now
    (``trim``), or once the keys are back on while one is off (``held_why``, said once)."""
    share = sizing.change_share(prev, g["to_price"], market_at(run, r["symbol"], g["first_ts"]))
    before = sizing.target_for(rs, index, pos["qty"])
    after = sizing.shrunk(before, share or 0.0)
    sizing.keep(rs, index, before, after)
    if held_why is not None:
        run.out["actions"].append({"kind": "note", "host": name, "pos_id": pos["id"], "row_id": r["id"],
                                   "symbol": r["symbol"], "side": r["side"], "step": "trim",
                                   "change": {**change, "kind": "trim"},
                                   "why": f"{name} sold part of {r['symbol']}: not sold -- {held_why}; the bot sells "
                                          "its share when it is back on"})
        return
    trim(run, name, st, r, rs, pos, change, share=share)


def trim(run: Any, name: str, st: dict[str, Any], r: dict[str, Any], rs: dict[str, Any], pos: dict[str, Any],
         change: dict[str, Any], *, share: float | None = None) -> bool:
    """Sell the shares the bot holds over its target, once they are worth the lot; never all of it on a partial
    sale (the host still holds the rest), never on Exit: You. Each that sends nothing is said as a note. True when
    a sale went out."""
    sym, held = r["symbol"], float(pos["qty"])
    target = rs.get("target")
    if target is None:
        return False
    base = {"host": name, "pos_id": pos["id"], "row_id": r["id"], "symbol": sym, "side": r["side"],
            "step": "trim", "change": {**change, "kind": "trim"}}
    sold = f"about {share:.0%} of" if share else "part of"
    if st["exit"] == "you":
        run.out["actions"].append({**base, "kind": "note", "why": f"{name} sold {sold} {sym}: the exit is yours "
                                                                   f"(Exit: You) -- the bot keeps its {held:g} shares"})
        return False
    price = feed_rows.reference_price(run.ctx["quote"](sym))
    lot = lot_of(st)
    qty = min(sizing.lot_shares(held - float(target), price or 0.0, lot), int(held) - 1)
    if qty <= 0:
        if held - float(target) >= 0.5:
            words = ("the bot keeps its last share until they close" if int(held) <= 1 else
                     f"its share ({held - float(target):.0f} of its {held:g}) is under the "
                     f"{rules.money(lot)} lot: sold once their sales add up")
            run.out["actions"].append({**base, "kind": "note", "code": LT_UNDER_LOT,
                                       "why": f"{name} sold {sold} {sym}: {words}"})
        return False
    run.out["actions"].append({**base, "kind": "close", "qty": float(qty), "trim": True,
                               "why": f"{name} sold {sold} {sym}: the bot sells {qty:g} of its {held:g}, the same "
                                      "share"})
    if r["side"] == "short":
        rs["trim_tried"] = round(float(target), 6)    # whole steps may not fit it: tried once per target
    return True


def follow_target(run: Any, name: str, st: dict[str, Any], r: dict[str, Any], rs: dict[str, Any],
                  pos: dict[str, Any]) -> bool:
    """Shares over the target -- a sale while a key was off, a long's sale that did not fill -- sell the first pass
    the bot may, as a held close does. A short tries each target once: when no whole step fits, it keeps them until
    the host sells or closes again, and its adds go on being followed. True when a sale went out."""
    target = rs.get("target")
    if target is None or float(pos["qty"]) - float(target) < 0.5:
        return False
    if r["side"] == "short" and rs.get("trim_tried") == round(float(target), 6):
        return False
    change = {"kind": "trim", "ts": run.now, "price": None}
    return trim(run, name, st, r, rs, pos, change)


def market_since(run: Any, symbol: str, change_ts: float | None) -> tuple[float, float] | None:
    """The market's ``(low, high)`` since the host's change (``market.range_since``), else None: ``rules.check``
    then judges by the quote now."""
    got = run.ctx.get("range_since")
    if got is None or change_ts is None:
        return None
    return got(symbol, change_ts - LT_SALE_LEAD_SEC)


def sale_of(run: Any, name: str, st: dict[str, Any], r: dict[str, Any], rs: dict[str, Any],
            prev: float | None, g: dict[str, Any], unread: set[str]) -> str | None:
    """Why the add group ``g`` is the host's partial sale, or None -- judged as every add is: a read in doubt, a
    misread, an average outside the band or no fresh quote is no sale (Codex review, PR #1024)."""
    if run.read_doubt(name, r, rs.get("add_since"), unread, entry=False) is not None:
        return None
    v = run.check(name, st, r["side"], r["symbol"], g["to_price"], None, None, entry=False, prev_price=prev,
                  change_ts=g["first_ts"])
    return v["text"] if v["verdict"] == rules.SKIP and v["code"] == LT_ADD_IS_SALE else None


def key_off_adds(run: Any, name: str, st: dict[str, Any], open_rows: list[dict[str, Any]], hs: dict[str, Any],
                 book: dict[str, dict[str, Any]], closing: set[str]) -> None:
    """The host's key is off: its bot places no order, and each add of what it holds is a skip (``LT_KEY_OFF``),
    so turning the key back on never buys an add made while it was off (operator decision 2026-10-15)."""
    off = (LT_KEY_OFF, f"{name}'s Bot key is off: its bot places no order")
    for r in open_rows:
        pid = feed_rows.position_id(name, r["side"], r["symbol"])
        pos = book.get(pid)
        if pos is None or pos["row_id"] != r["id"] or pid in closing:
            continue
        rs = hs["rows"].setdefault(r["id"], {"fate": None, "since": None, "groups_done": None, "ask_id": None,
                                             "kind": "open"})
        run.add(name, st, r, rs, pos, off, set())
