"""The short check the execution door runs on a short entry, under its lock (ADR 048).

``execution.validate.check_account_and_position`` hands every place or bracket that carries
``short_entry`` here. The checks, cheapest and most certain first; the first that fails refuses,
with its rule, its numbers and its fix:

1. the Live key, ``IBKR_SHORT_ENABLED`` (ADR 009, ``SHORT_DISABLED``);
2. a short entry is a SELL and a limit: SSR, the margin and the cushion all need its price
   (``SIDE_INVALID``, ``SHORT_NEEDS_LIMIT``);
3. no flips: never a short while the account holds the stock long (``SHORT_WHILE_LONG``);
4. a margin account with at least $2,000 of equity (``SHORT_NOT_MARGIN``, ``SHORT_EQUITY``);
5. borrow: a fresh tick-236 read from the cache -- the door never asks IBKR -- shortable, and
   covering this order plus the short held plus the shorts in flight (``SHORT_STALE_BORROW``,
   ``SHORT_NOT_SHORTABLE``, ``SHORT_BORROW_TOO_SMALL``);
6. margin by the published rules, and the 25% cushion (``SHORT_MARGIN_UNKNOWN``, ``SHORT_MARGIN``,
   ``SHORT_CUSHION``; ``short_sale.margin``).

The account's maintenance now is IBKR's own on Live (net liquidation less excess liquidity) and the
published rules over the practice ledger's positions on Paper and Sim. Shorts in flight on this
venue are counted at their limits. Reads only: positions, the account summary and the in-flight
commitments, all from memory.
"""
from __future__ import annotations

import logging
import math
from typing import Any

from constants_shorts import (
    SHORT_BORROW_TOO_SMALL,
    SHORT_CUSHION,
    SHORT_CUSHION_PCT,
    SHORT_EQUITY,
    SHORT_MARGIN,
    SHORT_MARGIN_SOURCE_PUBLISHED,
    SHORT_MARGIN_UNKNOWN,
    SHORT_MIN_EQUITY,
    SHORT_NEEDS_LIMIT,
    SHORT_NOT_MARGIN,
    SHORT_WHILE_LONG,
)
from execution import inflight
from execution.models import ExecutionCommand
from ibkr.errors import IbkrAccountError
from short_sale import margin

logger = logging.getLogger(__name__)

Refusal = tuple[str, str]   # (detail, reason_code)


def _num(value: Any) -> float | None:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def _money(value: float) -> str:
    return f"${value:,.2f}"


def entry_price(cmd: ExecutionCommand) -> float | None:
    """The short's limit: a place's ``limit_price`` (a LMT only), a bracket's ``entry_price``."""
    if cmd.operation == "bracket":
        return _num(cmd.entry_price)
    if (cmd.order_type or "").strip().upper() != "LMT":
        return None
    return _num(cmd.limit_price)


def order_qty(cmd: ExecutionCommand) -> float:
    return abs(float(cmd.qty if cmd.qty is not None else cmd.shares or 0))


def _shape(cmd: ExecutionCommand) -> Refusal | None:
    if cmd.operation == "place" and (cmd.side or "").upper() != "SELL":
        return "short_entry requires side=SELL", "SIDE_INVALID"
    price = entry_price(cmd)
    if price is None or price <= 0:
        return ("A short goes in as a limit order: SSR, the margin and the 25% cushion are all read "
                "at its price. Send it as a Limit.", SHORT_NEEDS_LIMIT)
    return None


def _not_long(account: Any, symbol: str) -> Refusal | None:
    try:
        held = float(account.long_qty(symbol))
    except IbkrAccountError as exc:
        logger.exception("short check: long_qty failed -- refusing the short of %s", symbol)
        return f"Short refused -- the {symbol} position cannot be read: {exc}", "POSITION_UNAVAILABLE"
    if held > 0:
        return (f"You hold {held:g} {symbol} long. Nova never flips a long into a short: sell what you "
                "hold first, then short from flat.", SHORT_WHILE_LONG)
    return None


def _account(summary: dict[str, Any]) -> tuple[float | None, Refusal | None]:
    """The equity a short is judged against, or why the account cannot short."""
    if not summary or summary.get("connected") is False or summary.get("pending"):
        return None, ("The account's equity and margin cannot be read yet, so Nova cannot check this "
                      "short against them. Try again once the account loads.", SHORT_MARGIN_UNKNOWN)
    equity = _num(summary.get("NetLiquidation"))
    if equity is None:
        return None, ("The account's net liquidation is not known, so Nova cannot check this short's "
                      "margin. Try again once the account loads.", SHORT_MARGIN_UNKNOWN)
    if str(summary.get("account_class") or "").strip().lower() != "margin":
        return None, ("This account is not a margin account, and only a margin account can short. "
                      "IBKR must show the account as margin before Nova offers a short.", SHORT_NOT_MARGIN)
    if equity < SHORT_MIN_EQUITY:
        return None, (f"A short needs at least {_money(SHORT_MIN_EQUITY)} of equity (FINRA's margin "
                      f"minimum); the account has {_money(equity)}.", SHORT_EQUITY)
    return equity, None


def _borrow(snapshot: dict[str, Any] | None, symbol: str, need: float, held: float, flying: float) -> Refusal | None:
    from ibkr.shortability import assert_shortable_for_order

    if not snapshot:
        return (f"No borrow read for {symbol} is on hand, so Nova cannot tell whether IBKR can lend it. "
                f"Nova asked IBKR just now: place the short again in a moment (an open {symbol} Trader tab "
                "keeps its borrow fresh).", "SHORT_STALE_BORROW")
    ok, detail, code = assert_shortable_for_order(snapshot)
    if not ok:
        if code == "SHORT_STALE_BORROW":
            detail = (f"{symbol}'s borrow read is {float(snapshot.get('age_sec') or 0):.0f} s old, past its "
                      f"{float(snapshot.get('ttl_sec') or 0):.0f} s limit. Nova asked IBKR again: place the "
                      "short again in a moment.")
        return detail, code or "SHORT_NOT_SHORTABLE"
    lendable = _num(snapshot.get("shortable_shares"))
    total = need + held + flying
    if lendable is None or lendable < total:
        shown = "unknown" if lendable is None else f"~{lendable:,.0f}"
        return (f"IBKR lends {shown} {symbol} shares; this short needs {total:,.0f} -- {need:,.0f} for this "
                f"order, {held:,.0f} already short and {flying:,.0f} on the way. Short fewer shares.",
                SHORT_BORROW_TOO_SMALL)
    return None


def _maintenance_now(summary: dict[str, Any], positions: list[dict[str, Any]], symbol: str,
                     held_short: float, entry: float) -> float | None:
    """What every position but this stock's short needs now; None when it cannot be read.

    IBKR's own figure when the summary carries it (net liquidation less excess liquidity, less this
    stock's short at the published rules); else the published rules over the positions' marks.
    """
    equity, excess = _num(summary.get("NetLiquidation")), _num(summary.get("ExcessLiquidity"))
    if equity is not None and excess is not None:
        return max(0.0, equity - excess - margin.short_requirement(entry, held_short))
    total = 0.0
    for row in positions:
        if str(row.get("symbol") or "").strip().upper() == symbol:
            continue
        qty, price = _num(row.get("qty")), _num(row.get("market_price"))
        if qty is None or price is None:
            return None
        total += margin.short_requirement(price, qty) if qty < 0 else margin.long_requirement(price, qty)
    return total


def _margin(cmd: ExecutionCommand, *, equity: float, summary: dict[str, Any], positions: list[dict[str, Any]],
            symbol: str, held: float, venue: str | None) -> Refusal | None:
    entry = float(entry_price(cmd) or 0)
    other = _maintenance_now(summary, positions, symbol, held, entry)
    if other is None:
        return ("Nova cannot read what the account's other positions need in margin, so it cannot check "
                "this short. Try again once the positions load.", SHORT_MARGIN_UNKNOWN)
    flying_same = 0.0
    for row in inflight.commitments(inflight.SHORT, venue):
        if row.symbol == symbol:
            flying_same += row.qty
        elif row.price is not None:
            other += margin.short_requirement(row.price, row.qty)
    qty = order_qty(cmd) + held + flying_same
    verdict = margin.cushion(equity=equity, other_maint=other, qty=qty, entry=entry)
    liq = verdict["liquidation_price"]
    where = f"IBKR would liquidate near {liq:.2f}" if isinstance(liq, float) else "IBKR would liquidate at once"
    need = float(verdict["requirement"] or 0)
    if not verdict["fits"]:
        return (f"Margin ({SHORT_MARGIN_SOURCE_PUBLISHED}): {qty:,.0f} {symbol} short at {entry:.2f} needs "
                f"{_money(need)}, and the account's {_money(equity)} of equity has "
                f"{_money(max(0.0, equity - other))} left after its other positions. Short fewer shares.",
                SHORT_MARGIN)
    if not verdict["ok"]:
        return (f"Margin ({SHORT_MARGIN_SOURCE_PUBLISHED}): {where}, under {verdict['cushion_price']:.2f}, "
                f"the {SHORT_CUSHION_PCT:.0%} move against a short at {entry:.2f}. Nova keeps a "
                f"{SHORT_CUSHION_PCT:.0%} cushion: short fewer shares.", SHORT_CUSHION)
    return None


def refusal(cmd: ExecutionCommand, *, borrow: dict[str, Any] | None, venue: str | None) -> Refusal | None:
    """``(detail, reason_code)`` when the short entry ``cmd`` may not go out; None to let it."""
    from ibkr import account as _acct
    from ibkr import safety as _safety

    if not _safety.short_enabled():
        return "IBKR_SHORT_ENABLED is false — short entry locked", "SHORT_DISABLED"
    shaped = _shape(cmd)
    if shaped is not None:
        return shaped
    symbol = cmd.normalized_symbol() or ""
    flipped = _not_long(_acct, symbol)
    if flipped is not None:
        return flipped
    try:
        summary = _acct.get_account_summary()
        positions = list(_acct.get_positions() or [])
        held = float(_acct.short_qty(symbol))
    except IbkrAccountError as exc:
        logger.exception("short check: the account could not be read -- refusing the short of %s", symbol)
        return f"Short refused -- the account cannot be read: {exc}", SHORT_MARGIN_UNKNOWN
    equity, refused = _account(summary or {})
    if refused is not None:
        return refused
    flying = inflight.committed_qty(symbol, inflight.SHORT, venue)
    lent = _borrow(borrow, symbol, order_qty(cmd), held, flying)
    if lent is not None:
        return lent
    return _margin(cmd, equity=float(equity or 0), summary=summary or {}, positions=positions,
                   symbol=symbol, held=held, venue=venue)
