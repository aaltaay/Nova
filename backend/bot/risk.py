"""Small-cap risk filters: shares, $50 BP, working block, EH, TTL."""
from __future__ import annotations

import time
from typing import Any

from bot.errors import BotError
from bot.kinds import is_allowlisted, is_buy_kind
from bot.persist import load_session, save_session
from bot.quotes import last_quote, top_of_book
from constants_bot import (
    BOT_DEFAULT_ASK_OFFSET_USD,
    BOT_DEFAULT_BID_EXIT_OFFSET_USD,
    BOT_DEFAULT_EXIT_PCT,
    BOT_EXIT_PCTS,
    BOT_REASON_BP_BUDGET,
    BOT_REASON_FREE_FORM_QTY,
    BOT_REASON_KIND_BLOCKED,
    BOT_REASON_NEEDS_DEPTH,
    BOT_REASON_SHARES_CAP,
    BOT_REASON_WORKING_BLOCK,
)


def _caps(row: dict[str, Any]) -> dict[str, Any]:
    return dict(row.get("caps") or {})


def assert_kind(kind: str, row: dict[str, Any] | None = None) -> str:
    current = row or load_session()
    allow = list(_caps(current).get("allowlist") or [])
    if not is_allowlisted(kind, allow):
        raise BotError(
            f"{kind} is not on the small-cap allowlist",
            409,
            BOT_REASON_KIND_BLOCKED,
        )
    return kind


def resolve_shares(kind: str, body: dict[str, Any], row: dict[str, Any]) -> int:
    if body.get("qty") is not None or body.get("shares") is not None:
        raise BotError(
            "free-form qty is refused -- sizes come from the session max-shares preset",
            400,
            BOT_REASON_FREE_FORM_QTY,
        )
    shares = int(_caps(row).get("max_shares") or 1)
    if shares < 1:
        raise BotError("max shares must be at least 1", 400, BOT_REASON_SHARES_CAP)
    return shares


def resolve_percent(body: dict[str, Any]) -> int:
    percent = body.get("percent")
    if percent is None:
        return BOT_DEFAULT_EXIT_PCT
    percent = int(percent)
    if percent not in BOT_EXIT_PCTS:
        raise BotError(
            f"percent must be one of {BOT_EXIT_PCTS}",
            400,
            BOT_REASON_FREE_FORM_QTY,
        )
    return percent


def resolve_offset(kind: str, body: dict[str, Any]) -> float:
    offset = body.get("offset_dollars", body.get("offsetDollars"))
    if offset is not None:
        raise BotError(
            "free-form offset is refused -- use session Ask/Bid presets",
            400,
            BOT_REASON_FREE_FORM_QTY,
        )
    if kind == "sell_pos_pct_bid_offset" or kind == "sell_limit_bid_offset":
        return BOT_DEFAULT_BID_EXIT_OFFSET_USD
    return BOT_DEFAULT_ASK_OFFSET_USD


def outside_rth(row: dict[str, Any]) -> bool:
    return bool(_caps(row).get("extended_hours"))


def working_bot_orders(row: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    current = row or load_session()
    return list(current.get("working") or [])


def assert_no_working_buy(kind: str, row: dict[str, Any]) -> None:
    if not is_buy_kind(kind):
        return
    if working_bot_orders(row):
        raise BotError(
            "new bot buy blocked while a working bot order exists",
            409,
            BOT_REASON_WORKING_BLOCK,
        )


def _mark_price(symbol: str, limit_price: float | None) -> float:
    if limit_price is not None and limit_price > 0:
        return float(limit_price)
    last = last_quote(symbol) or {}
    price = last.get("price")
    if price and float(price) > 0:
        return float(price)
    bid, ask = top_of_book(symbol)
    for candidate in (ask, bid):
        if candidate and candidate > 0:
            return float(candidate)
    return 0.0


def open_plus_working_usd(row: dict[str, Any]) -> float:
    total = 0.0
    qty_map = dict(row.get("bot_qty") or {})
    for symbol, qty in qty_map.items():
        try:
            shares = float(qty)
        except (TypeError, ValueError):
            continue
        if shares <= 0:
            continue
        total += shares * _mark_price(str(symbol), None)
    for order in working_bot_orders(row):
        if str(order.get("side") or "").upper() != "BUY":
            continue
        try:
            shares = abs(float(order.get("qty") or 0))
            price = float(order.get("price") or 0)
        except (TypeError, ValueError):
            continue
        total += shares * max(price, 0.0)
    return total


def assert_bp_budget(kind: str, symbol: str, qty: float, price: float | None, row: dict[str, Any]) -> None:
    if not is_buy_kind(kind):
        return
    budget = float(_caps(row).get("bp_budget_usd") or 0)
    used = open_plus_working_usd(row)
    add = abs(float(qty)) * _mark_price(symbol, price)
    if used + add > budget + 1e-9:
        raise BotError(
            f"small-cap BP budget ${budget:.2f} would be exceeded "
            f"(open+working ${used:.2f} + new ${add:.2f})",
            409,
            BOT_REASON_BP_BUDGET,
        )


def limit_from_book(kind: str, symbol: str, offset: float) -> float:
    bid, ask = top_of_book(symbol)
    if kind == "buy_limit_ask_offset":
        if ask is None or ask <= 0:
            raise BotError("needs live L2 ask for the focused symbol", 409, BOT_REASON_NEEDS_DEPTH)
        return float(ask) + offset
    if kind == "sell_limit_ask_offset" or kind == "sell_pos_pct_ask":
        if ask is None or ask <= 0:
            raise BotError("needs live L2 ask for the focused symbol", 409, BOT_REASON_NEEDS_DEPTH)
        return float(ask) + offset
    if bid is None or bid <= 0:
        raise BotError("needs live L2 bid for the focused symbol", 409, BOT_REASON_NEEDS_DEPTH)
    return float(bid) - offset


def remember_working(
    *,
    order_id: int,
    symbol: str,
    side: str,
    qty: float,
    price: float | None,
    kind: str,
    ttl_sec: int | None,
) -> None:
    """Record a working bot order; ``ttl_sec=None`` is one whose owner cancels it (ADR 030), not the TTL loop."""
    row = load_session()
    working = [w for w in list(row.get("working") or []) if int(w.get("order_id") or 0) != order_id]
    working.append({
        "order_id": int(order_id),
        "symbol": symbol,
        "side": side.upper(),
        "qty": float(qty),
        "price": float(price or 0),
        "kind": kind,
        "expire_ts": None if ttl_sec is None else time.time() + max(1, int(ttl_sec)),
    })
    row["working"] = working
    save_session(row)


def drop_working(order_id: int) -> dict[str, Any] | None:
    row = load_session()
    kept: list[dict[str, Any]] = []
    found = None
    for item in list(row.get("working") or []):
        if int(item.get("order_id") or 0) == int(order_id):
            found = item
            continue
        kept.append(item)
    row["working"] = kept
    save_session(row)
    return found


def adjust_bot_qty(symbol: str, delta: float) -> None:
    row = load_session()
    qty_map = dict(row.get("bot_qty") or {})
    key = symbol.upper()
    nxt = float(qty_map.get(key) or 0) + float(delta)
    if nxt <= 1e-9:
        qty_map.pop(key, None)
    else:
        qty_map[key] = nxt
    row["bot_qty"] = qty_map
    save_session(row)
