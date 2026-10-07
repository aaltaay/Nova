"""The short check's rules, in order (ADR 048 1). Pure: facts in, verdicts out.

``rules`` judges one short against every rule and returns them all -- the execution door refuses
with the first that fails (``short_sale.door``); the ticket's SHORT CHECK box, the plan and the
bot's squares show the whole list (``GET /api/short-check/{symbol}``). Each verdict names its rule,
its numbers and its fix:

1. ``live_key`` -- Live only: ``IBKR_SHORT_ENABLED`` (ADR 009, ``SHORT_DISABLED``);
2. ``order`` -- a SELL, a limit, and a buy stop above it (``SHORT_NEEDS_LIMIT``, ``SHORT_NEEDS_STOP``);
3. ``not_long`` -- never a short while the account holds the stock long (``SHORT_WHILE_LONG``);
4. ``account`` -- a margin account with at least $2,000 of equity;
5. ``hours`` -- 09:35 to 15:50 ET by the venue's clock (12:50 on an early close);
6. ``halt`` -- not halted, not within 10 minutes of an up-halt's resumption, never unknown;
7. ``borrow`` -- IBKR's estimate covers this order, the short held and the shorts on the way;
8. ``ssr`` -- under SSR (or when SSR is unknown) a short sells only above the bid;
9. ``margin`` -- the requirement fits (IBKR's what-if for the stock, else the published rules);
10. ``cushion`` -- IBKR would not liquidate within a 25% move against the short.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from constants_shorts import (
    SHORT_BORROW_TOO_SMALL,
    SHORT_CUSHION,
    SHORT_CUSHION_PCT,
    SHORT_EQUITY,
    SHORT_HALT_COOLOFF,
    SHORT_HALT_UNKNOWN,
    SHORT_HALTED,
    SHORT_HOURS,
    SHORT_MARGIN,
    SHORT_MARGIN_SOURCE_PUBLISHED,
    SHORT_MARGIN_SOURCE_WHATIF,
    SHORT_MARGIN_UNKNOWN,
    SHORT_MIN_EQUITY,
    SHORT_NEEDS_LIMIT,
    SHORT_NEEDS_STOP,
    SHORT_NO_RECORDED_BORROW,
    SHORT_NOT_MARGIN,
    SHORT_SSR_AT_BID,
    SHORT_SSR_NO_BID,
    SHORT_WHILE_LONG,
)
from short_sale import hours as short_hours
from short_sale import margin
from short_sale.facts import Facts


@dataclass(frozen=True)
class Order:
    symbol: str
    qty: float
    entry: float | None       # the short's limit
    stop: float | None        # its buy stop
    target: float | None = None
    side_ok: bool = True      # a SELL (a place) or a short bracket


@dataclass(frozen=True)
class Account:
    """The account as the door reads it under its lock (``short_sale.door.read_account``)."""

    summary: dict[str, Any] | None
    positions: list[dict[str, Any]]
    held_long: float | None           # None: the position could not be read
    held_short: float | None
    error: str | None = None
    flying_same: float = 0.0          # shorts of this stock on the way
    flying_other_maint: float = 0.0   # what the shorts of other stocks on the way will need
    flying_same_at: tuple[tuple[float, float], ...] = ()   # those of this stock with a limit: (qty, limit)


@dataclass(frozen=True)
class Verdict:
    id: str
    label: str
    ok: bool
    state: str                # "ok" | "bad" | "unknown" | "info"
    text: str
    code: str | None = None
    value: str | None = None
    numbers: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"id": self.id, "label": self.label, "ok": self.ok, "state": self.state, "text": self.text,
                "code": self.code, "value": self.value, "numbers": self.numbers}


def _num(value: Any) -> float | None:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def _money(value: float) -> str:
    return f"${value:,.2f}"


def _ok(rule: str, label: str, text: str, value: str | None = None, **numbers: Any) -> Verdict:
    return Verdict(rule, label, True, "ok", text, None, value, numbers)


def _bad(rule: str, label: str, code: str, text: str, value: str | None = None, *, state: str = "bad",
         **numbers: Any) -> Verdict:
    return Verdict(rule, label, False, state, text, code, value, numbers)


def _order(order: Order) -> Verdict:
    if not order.side_ok:
        return _bad("order", "The order", "SIDE_INVALID", "short_entry requires side=SELL")
    if order.entry is None or order.entry <= 0:
        return _bad("order", "The order", SHORT_NEEDS_LIMIT,
                    "A short goes in as a limit order: SSR, the margin and the 25% cushion are all read at its "
                    "price. Send it as a Limit.")
    if order.stop is None:
        return _bad("order", "The stop", SHORT_NEEDS_STOP,
                    "A short goes out with its buy stop above the entry: no stop price, no short. Set the Buy stop.")
    if order.stop <= order.entry:
        return _bad("order", "The stop", SHORT_NEEDS_STOP,
                    f"The buy stop ({order.stop:.2f}) must sit above the short's price ({order.entry:.2f}).")
    risk = order.stop - order.entry
    return _ok("order", "The stop", (f"Short {order.qty:,.0f} at {order.entry:.2f}, buy stop {order.stop:.2f}: "
                                     f"{risk:.2f} a share, {_money(risk * order.qty)} at risk."),
               f"stop {order.stop:.2f}", risk_per_share=round(risk, 4))


def _not_long(order: Order, account: Account) -> Verdict:
    if account.held_long is None:
        return _bad("not_long", "You hold", "POSITION_UNAVAILABLE",
                    f"Short refused -- the {order.symbol} position cannot be read: {account.error or 'unknown'}")
    if account.held_long > 0:
        return _bad("not_long", "You hold", SHORT_WHILE_LONG,
                    (f"You hold {account.held_long:g} {order.symbol} long. Nova never flips a long into a short: "
                     "sell what you hold first, then short from flat."), f"{account.held_long:g} long")
    held = account.held_short or 0.0
    text = f"You hold none long; this adds to your {held:g} short." if held else "You hold none long."
    return _ok("not_long", "You hold", text, "none long")


def _account(account: Account) -> tuple[float | None, Verdict]:
    summary = account.summary or {}
    if not summary or summary.get("connected") is False or summary.get("pending"):
        return None, _bad("account", "Equity", SHORT_MARGIN_UNKNOWN,
                          ("The account's equity and margin cannot be read yet, so Nova cannot check this short "
                           "against them. Try again once the account loads."), state="unknown")
    equity = _num(summary.get("NetLiquidation"))
    if equity is None:
        return None, _bad("account", "Equity", SHORT_MARGIN_UNKNOWN,
                          ("The account's net liquidation is not known, so Nova cannot check this short's margin. "
                           "Try again once the account loads."), state="unknown")
    if str(summary.get("account_class") or "").strip().lower() != "margin":
        return None, _bad("account", "Margin account", SHORT_NOT_MARGIN,
                          ("This account is not a margin account, and only a margin account can short. IBKR must "
                           "show the account as margin before Nova offers a short."))
    if equity < SHORT_MIN_EQUITY:
        return None, _bad("account", "Equity", SHORT_EQUITY,
                          (f"A short needs at least {_money(SHORT_MIN_EQUITY)} of equity (FINRA's margin minimum); "
                           f"the account has {_money(equity)}."), _money(equity))
    return equity, _ok("account", "Equity", f"A margin account with {_money(equity)} of equity.", _money(equity))


def _hours(facts: Facts) -> Verdict:
    refused = short_hours.entry_refusal(facts.now)
    if refused:
        return _bad("hours", "Hours", SHORT_HOURS, refused, short_hours.clock(facts.now))
    got = short_hours.hours_on(facts.now)
    assert got is not None  # inside the hours
    return _ok("hours", "Hours", (f"Shorts until {short_hours.clock(got.last_short_ts)} ET; Nova covers what is left "
                                  f"at {short_hours.clock(got.cover_ts)}."),
               f"until {short_hours.clock(got.last_short_ts)}")


def _halt(facts: Facts) -> Verdict:
    halt = facts.halt
    codes = {"halted": SHORT_HALTED, "cooloff": SHORT_HALT_COOLOFF, "unknown": SHORT_HALT_UNKNOWN}
    if halt.state in codes:
        return _bad("halt", "Halt", codes[halt.state], halt.text, halt.state,
                    state="unknown" if halt.state == "unknown" else "bad", halt=halt.as_dict())
    return _ok("halt", "Halt", halt.text, "none in 10 min", halt=halt.as_dict())


def _borrow(order: Order, facts: Facts, account: Account) -> Verdict:
    from ibkr.shortability import assert_shortable_for_order

    snap = facts.borrow
    sym = order.symbol
    if facts.replay and snap is None:
        return _bad("borrow", "Borrow", SHORT_NO_RECORDED_BORROW, facts.borrow_why or "No borrow recorded then.",
                    state="unknown")
    if not snap:
        return _bad("borrow", "Borrow", "SHORT_STALE_BORROW",
                    (f"No borrow read for {sym} is on hand, so Nova cannot tell whether IBKR can lend it. Nova asked "
                     f"IBKR just now: place the short again in a moment (an open {sym} Trader tab keeps its borrow "
                     "fresh)."), state="unknown")
    ok, detail, code = assert_shortable_for_order(snap)
    if not ok:
        if code == "SHORT_STALE_BORROW":
            detail = (f"{sym}'s borrow read is {float(snap.get('age_sec') or 0):.0f} s old, past its "
                      f"{float(snap.get('ttl_sec') or 0):.0f} s limit. Nova asked IBKR again: place the short again "
                      "in a moment.")
        return _bad("borrow", "Borrow", code or "SHORT_NOT_SHORTABLE", detail,
                    state="unknown" if code == "SHORT_STALE_BORROW" else "bad")
    lendable = _num(snap.get("shortable_shares"))
    held = account.held_short or 0.0
    total = order.qty + held + account.flying_same
    shown = "unknown" if lendable is None else f"~{lendable:,.0f}"
    if lendable is None or lendable < total:
        return _bad("borrow", "Borrow", SHORT_BORROW_TOO_SMALL,
                    (f"IBKR lends {shown} {sym} shares; this short needs {total:,.0f} -- {order.qty:,.0f} for this "
                     f"order, {held:,.0f} already short and {account.flying_same:,.0f} on the way. Short fewer "
                     "shares."), f"shortable {shown}", shares=lendable)
    where = " (recorded)" if facts.replay else ""
    return _ok("borrow", "Borrow", f"IBKR lends {shown} {sym}{where}: enough for {total:,.0f}.",
               f"shortable {shown}", shares=lendable, age_sec=snap.get("age_sec"))


def _ssr(order: Order, facts: Facts) -> Verdict:
    read = facts.ssr
    numbers = {"ssr": read.as_dict(), "bid": facts.bid, "ask": facts.ask}
    if not read.effective_on:
        return _ok("ssr", "SSR", read.text, "off", **numbers)
    if facts.bid is None:
        return _bad("ssr", "SSR", SHORT_SSR_NO_BID,
                    (f"{read.text} Nova sees no bid for {order.symbol}, so it cannot price the short above it: "
                     "wait for a quote."), "no bid", state="unknown", **numbers)
    entry = float(order.entry or 0)
    if entry <= facts.bid:
        ask = f", at the ask {facts.ask:.2f}" if facts.ask is not None else ""
        return _bad("ssr", "SSR", SHORT_SSR_AT_BID,
                    (f"{read.text} {entry:.2f} is at or below the bid {facts.bid:.2f}: price it above the bid{ask}."),
                    "at the ask", **numbers)
    return _ok("ssr", "SSR", f"{read.text} {entry:.2f} is above the bid {facts.bid:.2f}.",
               "on · at the ask" if read.state == "on" else "unknown · at the ask", **numbers)


def _held_mark(account: Account, symbol: str) -> float | None:
    """The price the short already held is marked at now (its position row's), or None."""
    for row in account.positions:
        if str(row.get("symbol") or "").strip().upper() == symbol:
            price = _num(row.get("market_price"))
            return price if price is not None and price > 0 else None
    return None


def _maintenance_now(account: Account, symbol: str, held_mark: float | None, ratio: float) -> float | None:
    """What every position but this stock's short needs now; None when it cannot be read.

    The account's own figure when its summary carries one (net liquidation less excess liquidity,
    less this stock's short at its mark now); else the published rules over the positions' marks.
    """
    summary = account.summary or {}
    held_short = account.held_short or 0.0
    equity, excess = _num(summary.get("NetLiquidation")), _num(summary.get("ExcessLiquidity"))
    if equity is not None and excess is not None:
        held_need = margin.short_requirement(held_mark, held_short) * ratio if held_mark is not None else 0.0
        return max(0.0, equity - excess - held_need)
    total = 0.0
    for row in account.positions:
        if str(row.get("symbol") or "").strip().upper() == symbol:
            continue
        qty, price = _num(row.get("qty")), _num(row.get("market_price"))
        if qty is None or price is None:
            return None
        total += margin.short_requirement(price, qty) if qty < 0 else margin.long_requirement(price, qty)
    return total


def _margin(order: Order, facts: Facts, account: Account, equity: float) -> list[Verdict]:
    entry = float(order.entry or 0)
    answer = None if facts.replay else facts.whatif
    ratio = answer.ratio if answer is not None else 1.0
    source = SHORT_MARGIN_SOURCE_WHATIF if answer is not None else SHORT_MARGIN_SOURCE_PUBLISHED
    held = account.held_short or 0.0
    held_mark = _held_mark(account, order.symbol) if held > 0 else None
    if held > 0 and held_mark is None:
        return [_bad("margin", "Margin", SHORT_MARGIN_UNKNOWN,
                     (f"Nova cannot read the price of the {held:g} {order.symbol} already short, so it cannot check "
                      "what adding to it needs. Try again once the positions load."), state="unknown")]
    other = _maintenance_now(account, order.symbol, held_mark, ratio)
    if other is None:
        return [_bad("margin", "Margin", SHORT_MARGIN_UNKNOWN,
                     ("Nova cannot read what the account's other positions need in margin, so it cannot check this "
                      "short. Try again once the positions load."), state="unknown")]
    other += account.flying_other_maint
    # This stock's shorts on the way keep their own limits; one Nova cannot price counts at this entry.
    # The short already held keeps its mark now: by the time the price reaches the entry it has moved.
    priced = account.flying_same_at
    unpriced = max(0.0, account.flying_same - sum(qty for qty, _ in priced))
    verdict = margin.cushion(equity=equity, other_maint=other, qty=order.qty + unpriced, entry=entry, ratio=ratio,
                             flying=priced, held=(held, held_mark) if held_mark is not None else None)
    qty = float(verdict["qty"] or 0)
    fill = float(verdict["fill_price"] or entry)
    at = f"at {entry:.2f}" if fill <= entry else f"up to {fill:.2f} (the shorts on the way keep their prices)"
    liq = verdict["liquidation_price"]
    need = float(verdict["requirement"] or 0)
    left = max(0.0, equity - other)
    numbers = {"source": source, "ratio": round(ratio, 4), "requirement": round(need, 2), "excess": round(left, 2),
               "liquidation_price": liq, "cushion_price": verdict["cushion_price"], "fill_price": fill,
               "held_short": held, "held_mark": held_mark}
    held_note = f" (the {held:g} already short counted from its mark {held_mark:.2f})" if held_mark is not None else ""
    at += held_note
    if not verdict["fits"]:
        return [_bad("margin", "Margin", SHORT_MARGIN,
                     (f"Margin ({source}): {qty:,.0f} {order.symbol} short {at} needs {_money(need)}, and "
                      f"the account's {_money(equity)} of equity has {_money(left)} left after its other positions. "
                      "Short fewer shares."), _money(need), **numbers)]
    fits = _ok("margin", "Margin", f"Margin ({source}): {_money(need)} of {_money(left)}.", _money(need), **numbers)
    if not verdict["ok"]:
        where = f"IBKR would liquidate near {liq:.2f}" if isinstance(liq, float) else "IBKR would liquidate at once"
        return [fits, _bad("cushion", "25% cushion", SHORT_CUSHION,
                           (f"Margin ({source}): {where}, under {verdict['cushion_price']:.2f}, the "
                            f"{SHORT_CUSHION_PCT:.0%} move against a short at {fill:.2f}{held_note}. Nova keeps a "
                            f"{SHORT_CUSHION_PCT:.0%} cushion: short fewer shares."),
                           f"LIQ {liq:.2f}" if isinstance(liq, float) else None, **numbers)]
    return [fits, _ok("cushion", "25% cushion",
                      (f"IBKR would liquidate near {liq:.2f}, over {verdict['cushion_price']:.2f} (a "
                       f"{SHORT_CUSHION_PCT:.0%} move against the short)."),
                      f"LIQ {liq:.2f}" if isinstance(liq, float) else None, **numbers)]


def rules(order: Order, facts: Facts, account: Account, *, live_key: bool | None) -> list[Verdict]:
    """Every rule's verdict, in order; ``live_key`` is None off Live (Paper and Sim need none)."""
    out: list[Verdict] = []
    if live_key is not None:
        out.append(_ok("live_key", "Live shorts", "IBKR_SHORT_ENABLED is on.") if live_key else
                   _bad("live_key", "Live shorts", "SHORT_DISABLED",
                        "IBKR_SHORT_ENABLED is false — short entry locked"))
    out += [_order(order), _not_long(order, account)]
    equity, verdict = _account(account)
    out += [verdict, _hours(facts), _halt(facts), _borrow(order, facts, account), _ssr(order, facts)]
    if equity is not None and order.entry:
        out += _margin(order, facts, account, equity)
    return out


def first_refusal(verdicts: list[Verdict]) -> tuple[str, str] | None:
    """``(detail, reason_code)`` of the first rule that fails, in order; None when every rule passes."""
    for verdict in verdicts:
        if not verdict.ok:
            return verdict.text, verdict.code or "SHORT_REFUSED"
    return None
