"""A position the Live Trader bot holds, changed by its host past the plain add (ADR 055). Pure.

- ``trim``: the host sold part -- the bot sells half its shares, once (operator 2026-10-16, "Sell half, once"): a
  ``close`` action with ``trim: true`` for ``act.close``.
- ``key_off_adds``: the host's key is off -- each add of what the bot holds is a skip (``LT_KEY_OFF``).

The bar shows the host's average, never the shares they sold: an average that moved away from the market is a sale
their platform folded into it (``rules.sale_text``, ``LT_ADD_IS_SALE``). Shapes: architecture/schema/bot.md ("A sale
read as an add").
"""
from __future__ import annotations

from typing import Any

from bot.live_trader import feed_rows, rules
from bot.live_trader.constants_live_trader import LT_ADD_IS_SALE, LT_KEY_OFF, LT_SALE_LEAD_SEC


def trim(run: Any, name: str, st: dict[str, Any], r: dict[str, Any], pos: dict[str, Any],
         change: dict[str, Any]) -> None:
    """Half the bot's long, once per position. A short keeps every share: Paper cannot shrink its buy stop to the
    rest. A single share has no half; Exit: You keeps them. Each of those is said as a note."""
    if pos.get("trimmed"):
        return
    sym = r["symbol"]
    base = {"host": name, "pos_id": pos["id"], "row_id": r["id"], "symbol": sym, "side": r["side"],
            "step": "trim", "change": {**change, "kind": "trim"}}
    half = int(pos["qty"] // 2)
    if st["exit"] == "you":
        why = f"{name} sold part of {sym}: the exit is yours (Exit: You) -- the bot keeps its {pos['qty']:g} shares"
    elif r["side"] == "short":
        why = (f"{name} covered part of {sym}: the bot keeps its {pos['qty']:g} short -- Paper cannot shrink its buy "
               "stop to the shares left, so it covers when they close")
    elif half < 1:
        why = f"{name} sold part of {sym}: the bot holds {pos['qty']:g} share, nothing to halve"
    else:
        run.out["actions"].append({**base, "kind": "close", "qty": float(half), "trim": True,
                                   "why": f"{name} sold part of {sym}: the bot sells half, once"})
        return
    run.out["actions"].append({**base, "kind": "note", "why": why})


def market_since(run: Any, symbol: str, change_ts: float | None) -> tuple[float, float] | None:
    """The market's ``(low, high)`` since the host's change (``market.range_since``), else None: ``rules.check``
    then judges by the quote now."""
    got = run.ctx.get("range_since")
    if got is None or change_ts is None:
        return None
    return got(symbol, change_ts - LT_SALE_LEAD_SEC)


def sale_past_limit(run: Any, name: str, st: dict[str, Any], r: dict[str, Any], rs: dict[str, Any],
                    pos: dict[str, Any], prev: float | None, g: dict[str, Any], change: dict[str, Any]) -> bool:
    """With every add this bot follows spent, a sale is still a sale: skipped and trimmed. True when it was one."""
    quote = run.ctx["quote"](r["symbol"]) or {}
    ref = feed_rows.reference_price(quote) if quote.get("fresh") else None
    window = market_since(run, r["symbol"], g["first_ts"]) or (None if ref is None else (ref, ref))
    sold = rules.sale_text(prev, g["to_price"], window)
    if not sold:
        return False
    rs["groups_done"] += 1
    run.skip(name, r, pos["id"], "add", LT_ADD_IS_SALE, sold, change)
    trim(run, name, st, r, pos, change)
    return True


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
