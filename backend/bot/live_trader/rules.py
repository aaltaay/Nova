"""The checks before a Live Trader step, its size and its prices (ADR 055 decisions 3 and 4). Pure.

``check`` answers one step -- an entry, a position already open, or an add -- as ``go`` (with its plan),
``wait`` (a quote line opening, a market cap or a ticker check being read) or ``skip``, each with its code and
the words the Bots page shows. A wait that has lasted ``LT_WAIT_SEC`` is its skip. The first rule that fails
answers: the side, the short hours, the ticker, the market cap, the quote, the misread, a position against it,
the allowance. Shapes: architecture/schema/bot.md ("The Live Trader bot").
"""
from __future__ import annotations

import math
from typing import Any

from bot.live_trader import feed_rows
from bot.live_trader.constants_live_trader import (
    LT_ALLOWANCE,
    LT_CAP_UNKNOWN,
    LT_ENTRY_OFFSET_USD,
    LT_MIN_MARKET_CAP_USD,
    LT_MISREAD,
    LT_MISREAD_PCT,
    LT_NO_QUOTE,
    LT_NOT_PRICEABLE,
    LT_SHORT_HOURS,
    LT_SHORTS_OFF,
    LT_SMALL_CAP,
    LT_TICKER_UNSETTLED,
    LT_WAIT_SEC,
    LT_AGAINST,
)

GO, WAIT, SKIP = "go", "wait", "skip"
SETTLED_TICKERS = (None, "as_read", "corrected")


def money(value: float) -> str:
    return f"${value:,.0f}" if abs(value) >= 100 else f"${value:,.2f}"


def price_text(price: float | None) -> str:
    if price is None:
        return "?"
    return f"{price:.4f}" if abs(price) < 1 else f"{price:.2f}"


def tick_round(price: float) -> float:
    """A US stock's price tick: a cent at $1 and over, a hundredth of a cent under it."""
    return round(price, 2) if price >= 1 else round(price, 4)


def shares(step_usd: float, price: float) -> int:
    """The step's shares: the dollars over the price, rounded down -- and one share when the step buys none
    (operator, 2026-10-14: "Buy 1 share"; the allowance still has to have room)."""
    if price <= 0:
        return 0
    return max(1, math.floor(step_usd / price + 1e-9))


def limits(side: str, quote: dict[str, Any], stop_pct: float) -> tuple[float | None, float | None]:
    """``(limit, stop)``: a long buys at the ask plus ``LT_ENTRY_OFFSET_USD`` (the last when no ask) and has no
    stop; a short sells at the bid less it (the last when no bid) with a buy stop ``stop_pct`` over that."""
    bid, ask, last = quote.get("bid"), quote.get("ask"), quote.get("last")
    if side == "long":
        base = ask if ask and ask > 0 else last
        return (tick_round(base + LT_ENTRY_OFFSET_USD) if base else None), None
    base = bid if bid and bid > 0 else last
    if not base:
        return None, None
    limit = tick_round(max(0.01, base - LT_ENTRY_OFFSET_USD))
    return limit, tick_round(limit * (1.0 + stop_pct / 100.0))


def verdict(kind: str, code: str | None = None, text: str | None = None,
            plan: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"verdict": kind, "code": code, "text": text, "plan": plan}


def _waited(code: str, wait_text: str, skip_text: str, since: float | None, now: float) -> dict[str, Any]:
    if since is not None and now - since >= LT_WAIT_SEC:
        return verdict(SKIP, code, skip_text)
    return verdict(WAIT, code, wait_text)


def check(*, side: str, symbol: str, their_price: float, settings: dict[str, Any], quote: dict[str, Any] | None,
          cap: Any, ticker: dict[str, Any] | None, used_usd: float, against: str | None,
          short_closed: str | None, priceable: bool, now: float, wait_since: float | None) -> dict[str, Any]:
    """One step's verdict. ``cap`` is the market cap in dollars, ``"pending"`` while it is read, or None when it
    could not be read; ``ticker`` the trade's check (``{"state", "why"}``, None when none is needed);
    ``against`` the words for a position on the other side; ``short_closed`` why no short may open now."""
    if side == "short" and settings["sides"] == "long":
        return verdict(SKIP, LT_SHORTS_OFF, "a short: this bot copies longs only")
    if side == "short" and short_closed:
        return verdict(SKIP, LT_SHORT_HOURS, short_closed)
    if not priceable:
        return verdict(SKIP, LT_NOT_PRICEABLE, f"{symbol!r} is not a ticker Nova can ask IBKR for")
    state = (ticker or {}).get("state")
    if state == "checking":
        return _waited(LT_TICKER_UNSETTLED, "checking the ticker against IBKR's tape (it may be glued to its price)",
                       f"the ticker check did not settle in {LT_WAIT_SEC:.0f} s", wait_since, now)
    if state not in SETTLED_TICKERS:
        return verdict(SKIP, LT_TICKER_UNSETTLED, f"the ticker may be misread: {(ticker or {}).get('why') or state}")
    if cap == "pending":
        return _waited(LT_CAP_UNKNOWN, "reading its market cap",
                       f"its market cap did not come in {LT_WAIT_SEC:.0f} s", wait_since, now)
    if not isinstance(cap, (int, float)) or isinstance(cap, bool) or cap <= 0:
        return verdict(SKIP, LT_CAP_UNKNOWN, "Nova could not read its market cap, so it cannot tell a large cap")
    if cap < LT_MIN_MARKET_CAP_USD:
        return verdict(SKIP, LT_SMALL_CAP, f"a small cap ({_cap_words(cap)}): this bot copies large caps only "
                                           f"({_cap_words(LT_MIN_MARKET_CAP_USD)} and up)")
    ref = feed_rows.reference_price(quote) if quote and quote.get("fresh") else None
    if ref is None:
        return _waited(LT_NO_QUOTE, "opening IBKR's quote line",
                       f"no fresh quote from IBKR in {LT_WAIT_SEC:.0f} s", wait_since, now)
    apart = feed_rows.apart_pct(their_price, ref)
    if apart > LT_MISREAD_PCT:
        return verdict(SKIP, LT_MISREAD, f"their average {price_text(their_price)} is {apart:.1f}% from the market "
                                         f"{price_text(ref)}: a misread")
    if against:
        return verdict(SKIP, LT_AGAINST, against)
    limit, stop = limits(side, quote or {}, float(settings["short_stop_pct"]))
    if limit is None:
        return _waited(LT_NO_QUOTE, "waiting for a bid and an ask",
                       f"no {'ask' if side == 'long' else 'bid'} from IBKR in {LT_WAIT_SEC:.0f} s", wait_since, now)
    qty = shares(float(settings["step_usd"]), limit)
    cost = qty * limit
    allowance = float(settings["allowance_usd"])
    if used_usd + cost > allowance + 1e-6:
        return verdict(SKIP, LT_ALLOWANCE, f"allowance used: {money(used_usd)} of {money(allowance)} "
                                           f"(this step is {money(cost)})")
    return verdict(GO, plan={"qty": qty, "limit": limit, "stop": stop, "cost_usd": round(cost, 2),
                             "reference": ref, "apart_pct": round(apart, 2)})


def _cap_words(cap: float) -> str:
    return f"${cap / 1e9:.1f}B" if cap >= 1e9 else f"${cap / 1e6:.0f}M"
