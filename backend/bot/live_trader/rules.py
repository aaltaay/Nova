"""The checks before a Live Trader step, its size and its prices (ADR 055 decisions 3 and 4). Pure.

``check`` answers one step -- an entry, a position already open, or an add -- as ``go`` (with its plan),
``wait`` (a quote line opening, a market cap or a ticker check being read) or ``skip``, each with its code and
the words the Bots page shows. A wait that has lasted ``LT_WAIT_SEC`` is its skip. The first rule that fails
answers: the side, the short hours, the ticker, the market cap, the quote, the misread, an add's average that
no add could make, a position against it, the allowance. Shapes: architecture/schema/bot.md ("The Live Trader bot").
"""
from __future__ import annotations

import math
from typing import Any

from bot.live_trader import feed_rows
from bot.live_trader.constants_live_trader import (
    LT_ADD_DIRECTION_PCT,
    LT_ADD_IMPLAUSIBLE,
    LT_ADD_IS_SALE,
    LT_ADD_SLACK_PCT,
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


def limits(side: str, quote: dict[str, Any], stop_pct: float,
           ssr: str = "off") -> tuple[float | None, float | None]:
    """``(limit, stop)``: a long buys at the ask plus ``LT_ENTRY_OFFSET_USD`` (the last when no ask) and has no
    stop; a short sells at the bid less it (the last when no bid) with a buy stop ``stop_pct`` over that -- while
    SSR is ``"off"``. On or unknown (it counts as on), the short sells at the ask, which must be above the bid, as
    the setup bot prices it (``first_pullback.short_side.price``): the short check refuses one at or below the bid
    (2026-10-16: SHAWN's TSLA short, SSR unknown, refused at the bid less 2 cents)."""
    bid, ask, last = quote.get("bid"), quote.get("ask"), quote.get("last")
    if side == "long":
        base = ask if ask and ask > 0 else last
        return (tick_round(base + LT_ENTRY_OFFSET_USD) if base else None), None
    if ssr != "off":
        if not ask or ask <= 0 or (bid and ask <= bid):
            return None, None
        limit = tick_round(ask)
        return limit, tick_round(limit * (1.0 + stop_pct / 100.0))
    base = bid if bid and bid > 0 else last
    if not base:
        return None, None
    limit = tick_round(max(0.01, base - LT_ENTRY_OFFSET_USD))
    return limit, tick_round(limit * (1.0 + stop_pct / 100.0))


def sale_text(prev_price: float | None, their_price: float, market: tuple[float, float] | None) -> str | None:
    """Why an average change is a partial sale, not an add, or None. ``market`` is ``(low, high)`` since the change.

    A buy only pulls the average toward the price it paid: an average that fell while the market stayed over the old
    one by more than ``LT_ADD_DIRECTION_PCT`` -- its low included -- was a sale (rose while it stayed under, on a
    short). A market that crossed the old average since the change could have been a real add: no sale (Codex
    review, PR #1022: a buy at 99.90 pulling 100.00 to 99.95, the market at 100.11 by the time Nova reads it)."""
    if not prev_price or prev_price <= 0 or market is None:
        return None
    low, high = market
    tol = prev_price * LT_ADD_DIRECTION_PCT / 100.0
    moved = their_price - prev_price
    if (moved < 0 and low > prev_price + tol) or (moved > 0 and high < prev_price - tol):
        edge = low if moved < 0 else high
        return (f"their average went {price_text(prev_price)} -> {price_text(their_price)} while the market stayed at "
                f"{price_text(edge)} or {'over' if moved < 0 else 'under'}: a buy cannot do that -- they sold part, "
                "so the bot buys nothing")
    return None


def verdict(kind: str, code: str | None = None, text: str | None = None,
            plan: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"verdict": kind, "code": code, "text": text, "plan": plan}


def waited(code: str, wait_text: str, skip_text: str, since: float | None, now: float) -> dict[str, Any]:
    """A wait, or its skip once it has lasted ``LT_WAIT_SEC``."""
    return _waited(code, wait_text, skip_text, since, now)


def _waited(code: str, wait_text: str, skip_text: str, since: float | None, now: float) -> dict[str, Any]:
    if since is not None and now - since >= LT_WAIT_SEC:
        return verdict(SKIP, code, skip_text)
    return verdict(WAIT, code, wait_text)


def check(*, side: str, symbol: str, their_price: float, settings: dict[str, Any], quote: dict[str, Any] | None,
          cap: Any, ticker: dict[str, Any] | None, used_usd: float, against: str | None,
          short_closed: str | None, priceable: bool, now: float, wait_since: float | None,
          prev_price: float | None = None, ssr: str = "unknown",
          market: tuple[float, float] | None = None) -> dict[str, Any]:
    """One step's verdict. ``ssr`` is the stock's SSR for a short (``"on"`` | ``"off"`` | ``"unknown"``). ``cap`` is the market cap in dollars, ``"etf"`` for an ETF (always allowed),
    ``"pending"`` while it is read, or None when it could not be read; ``ticker`` the trade's check (``{"state", "why"}``, None when none is needed);
    ``against`` the words for a position on the other side; ``short_closed`` why no short may open now;
    ``prev_price`` an add's average before it (an add moves the average toward the market, never past it)."""
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
    if cap == "etf":
        pass                                          # an ETF is always allowed (operator, 2026-10-14)
    elif not isinstance(cap, (int, float)) or isinstance(cap, bool) or cap <= 0:
        return verdict(SKIP, LT_CAP_UNKNOWN, "Nova could not read its market cap, so it cannot tell a large cap")
    elif cap < LT_MIN_MARKET_CAP_USD:
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
    if prev_price is not None and prev_price > 0:
        slack = ref * LT_ADD_SLACK_PCT / 100.0
        if not min(prev_price, ref) - slack <= their_price <= max(prev_price, ref) + slack:
            return verdict(SKIP, LT_ADD_IMPLAUSIBLE,
                           f"their new average {price_text(their_price)} is not between their average before "
                           f"{price_text(prev_price)} and the market {price_text(ref)}: a misread, not an add")
        # Inside the band but moved away from the market: a partial sale their platform folded into the average.
        sold = sale_text(prev_price, their_price, market or (ref, ref))
        if sold:
            return verdict(SKIP, LT_ADD_IS_SALE, sold)
    if against:
        return verdict(SKIP, LT_AGAINST, against)
    limit, stop = limits(side, quote or {}, float(settings["short_stop_pct"]), ssr)
    if limit is None:
        missing = "ask" if side == "long" else "bid" if ssr == "off" else "ask above the bid (SSR on or not known)"
        return _waited(LT_NO_QUOTE, "waiting for a bid and an ask",
                       f"no {missing} from IBKR in {LT_WAIT_SEC:.0f} s", wait_since, now)
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


STEP_KINDS = ("entry", "already_open", "add")


def used_by_host(book: dict[str, dict[str, Any]]) -> dict[str, float]:
    """Each host's dollars in the market: what its positions cost, and its steps in flight at their limits."""
    out: dict[str, float] = {}
    for p in book.values():
        cost = float(p.get("cost_usd") or 0.0)
        order = p.get("order") or {}
        if order.get("step") in STEP_KINDS and order.get("qty") and order.get("limit"):
            cost += float(order["qty"]) * float(order["limit"])
        out[p["host"]] = out.get(p["host"], 0.0) + cost
    return out


def against(book: dict[str, dict[str, Any]], ctx: dict[str, Any], side: str, symbol: str) -> str | None:
    """Why an entry would trade against a position (the bot's for another host, or the account's); None when not."""
    other = "short" if side == "long" else "long"
    for p in book.values():
        if p["symbol"] == symbol and p["side"] == other:
            return f"the bot holds {symbol} {other} for {p['host']}: Nova never holds both sides"
    held = ctx["held"](symbol, other)
    if held is None:
        return f"Paper's {symbol} position could not be read, so the bot cannot tell it is not against one"
    if held > 0:
        return f"you hold {symbol} {other} on Paper ({held:g} shares): the bot never trades against a position"
    return None
