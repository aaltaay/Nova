"""Claude's reflexes: Level 2 and Time & Sales conditions Nova checks twice a second (ADR 068 decision 11).

Claude looks every minute or two; a book can turn in a second. So on each look Claude arms conditions on its own
stock, and the watcher acts the moment one holds -- the "flash" decision the operator asked for ("watch level 2 and
make 'flash' decisions"), set by Claude's judgment, pulled by Nova.

Kinds (each one-shot; it fires once, does its action, and is gone):
- ``bid_pulled`` {price, shares}: the bids at ``price`` and above, added up across market makers, were at least
  ``shares`` since the reflex was armed and now are fewer -- the support Claude leaned on was pulled or eaten.
- ``ask_wall`` {price, shares}: one price at or under ``price`` shows at least ``shares`` offered -- a seller arrived.
- ``sellers`` {seconds, shares, ratio}: in the last ``seconds``, at least ``shares`` traded at or under the bid and at
  least ``ratio`` times what traded at or over the ask.
- ``last_below`` {price}: a print that sets a price at or under ``price`` -- a tighter stop than the bracket's.

Actions: ``sell_all`` (Claude's orders on the stock cancelled, its shares sold at market; armed while Claude holds
shares) or ``cancel_buy`` (Claude's unfilled buys and breaks on the stock cancelled; armed while one waits).

A break may carry ``confirm`` {seconds, shares, ratio}: it sends only while buyers lead -- at least ``shares`` traded at
or over the ask in the last ``seconds``, at least ``ratio`` times what traded at or under the bid -- and otherwise
keeps waiting for the next print at its trigger. Pure over what it is handed.
"""
from __future__ import annotations

from typing import Any

KINDS = ("bid_pulled", "ask_wall", "sellers", "last_below")
ACTIONS = ("sell_all", "cancel_buy")
_NEEDS = {"bid_pulled": ("price", "shares"), "ask_wall": ("price", "shares"),
          "sellers": ("seconds", "shares", "ratio"), "last_below": ("price",)}
SECONDS_MAX = 60.0


def _num(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out == out else None


def shape_refusal(row: dict[str, Any]) -> str | None:
    """Why a reflex is not well formed, or None."""
    kind, action = row.get("kind"), row.get("action")
    if kind not in KINDS:
        return f"a reflex is one of {', '.join(KINDS)}"
    if action not in ACTIONS:
        return f"a reflex does one of {', '.join(ACTIONS)}"
    for key in _NEEDS[kind]:
        value = _num(row.get(key))
        if value is None or value <= 0:
            return f"a {kind} reflex needs {', '.join(_NEEDS[kind])} above 0"
    if kind in ("sellers",) and float(row["seconds"]) > SECONDS_MAX:
        return f"a {kind} reflex looks back {SECONDS_MAX:g} seconds at most"
    return None


def confirm_refusal(confirm: dict[str, Any] | None) -> str | None:
    if confirm is None:
        return None
    for key in ("seconds", "shares", "ratio"):
        value = _num(confirm.get(key))
        if value is None or value <= 0:
            return "a break's confirm needs seconds, shares and ratio above 0"
    if float(confirm["seconds"]) > SECONDS_MAX:
        return f"a confirm looks back {SECONDS_MAX:g} seconds at most"
    return None


def text(row: dict[str, Any]) -> str:
    """The reflex in plain words, for the desk."""
    act = "sell all my shares" if row.get("action") == "sell_all" else "cancel my buy"
    kind = row.get("kind")
    if kind == "bid_pulled":
        cond = f"the bids at {row['price']:g} and up drop under {row['shares']:,.0f} shares"
    elif kind == "ask_wall":
        cond = f"a seller of {row['shares']:,.0f}+ shares shows at {row['price']:g} or lower"
    elif kind == "sellers":
        cond = (f"{row['shares']:,.0f}+ shares hit the bid in {row['seconds']:g} s, "
                f"{row['ratio']:g}x more than lift the ask")
    else:
        cond = f"it prints {row['price']:g} or lower"
    return f"{act.capitalize()} if {cond}"


def levels(book: dict[str, Any] | None, side: str) -> dict[float, float]:
    """Shares by price on one side of a depth book, added up across market makers."""
    out: dict[float, float] = {}
    for row in (book or {}).get(side) or []:
        px, size = _num(row.get("price")), _num(row.get("size"))
        if px is None or size is None or px <= 0:
            continue
        out[round(px, 4)] = out.get(round(px, 4), 0.0) + size
    return out


def flow(prints: list[dict[str, Any]], since: float) -> tuple[float, float]:
    """``(at_ask, at_bid)`` shares in prints after ``since``: a print at or over its ask is a buyer's, at or under
    its bid a seller's; prints without a quote count for neither."""
    buy = sell = 0.0
    for row in prints:
        ts, px, size = _num(row.get("ts")), _num(row.get("price")), _num(row.get("size")) or 0.0
        if ts is None or px is None or ts <= since:
            continue
        bid, ask = _num(row.get("bid")), _num(row.get("ask"))
        if ask is not None and px >= ask:
            buy += size
        elif bid is not None and px <= bid:
            sell += size
    return buy, sell


def bid_depth(book: dict[str, Any] | None, price: float) -> float:
    return sum(size for px, size in levels(book, "bids").items() if px >= price - 1e-9)


def fired(row: dict[str, Any], *, book: dict[str, Any] | None, prints: list[dict[str, Any]], now: float,
          primed: bool) -> str | None:
    """Why ``row`` fires now, in words, or None. ``primed``: a bid_pulled reflex has seen its size since arming."""
    kind = row["kind"]
    if kind == "bid_pulled":
        have = bid_depth(book, float(row["price"]))
        if primed and book and have < float(row["shares"]):
            return f"the bids at {row['price']:g} and up fell to {have:,.0f} shares"
        return None
    if kind == "ask_wall":
        for px, size in sorted(levels(book, "asks").items()):
            if px <= float(row["price"]) + 1e-9 and size >= float(row["shares"]):
                return f"a {size:,.0f}-share seller showed at {px:g}"
        return None
    if kind == "sellers":
        buy, sell = flow(prints, now - float(row["seconds"]))
        if sell >= float(row["shares"]) and sell >= float(row["ratio"]) * max(buy, 1.0):
            return f"{sell:,.0f} shares hit the bid in {row['seconds']:g} s against {buy:,.0f} at the ask"
        return None
    armed_at = float(row.get("created_at") or 0.0)
    for p in prints:
        ts, px = _num(p.get("ts")), _num(p.get("price"))
        if ts is not None and px is not None and ts > armed_at and px <= float(row["price"]) + 1e-9:
            return f"it printed {px:g}"
    return None


def primes(row: dict[str, Any], book: dict[str, Any] | None) -> bool:
    """A bid_pulled reflex is primed once the size it guards is there."""
    return row["kind"] == "bid_pulled" and bool(book) and bid_depth(book, float(row["price"])) >= float(row["shares"])


def confirmed(confirm: dict[str, Any] | None, prints: list[dict[str, Any]], now: float) -> tuple[bool, str]:
    """``(ok, words)`` for a break's confirm: buyers lead in the last ``seconds``."""
    if not confirm:
        return True, ""
    buy, sell = flow(prints, now - float(confirm["seconds"]))
    ok = buy >= float(confirm["shares"]) and buy >= float(confirm["ratio"]) * max(sell, 1.0)
    return ok, f"{buy:,.0f} shares lifted the ask against {sell:,.0f} hitting the bid in {confirm['seconds']:g} s"
