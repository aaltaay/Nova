"""The order size limit at the door: which orders it reads, and the words of a refusal (ADR 064).

``execution.service`` asks ``refusal`` with the door's own venue for every place or bracket, after the
daily loss limit. It reads only your own hand orders -- source ``manual``: the ticket, the hotkeys and
the plan box's Approve -- on Paper and Sim, and only one that opens or adds: a BUY that covers nothing,
a SELL that opens a short. Selling what you hold, a BUY that covers a short, exit pairs, cancels,
replaces, Flatten, KILL and every bot order (source ``bot``: the bots, Auto-entry, the bot API; they keep
their sleeve caps) never meet it. Live never meets it either: Live keeps ``IBKR_QTY_CAP``
(``execution.qty_gate``) and its PIN.

Each order is read alone, when it is placed. A place carries no protective stop -- its ``stop_price``
is a stop order's own trigger -- so while Max risk at stop is set a place is refused
``ORDER_SIZE_LIMIT_NO_STOP``, its risk unknown (operator decision 2026-10-20). A bracket risks
``shares x |entry - stop|``, in cents. Moving a working order's stop later is never refused here.
"""
from __future__ import annotations

from typing import Any

from constants_order_size_limit import (
    ORDER_SIZE_LIMIT_REASON_NO_STOP,
    ORDER_SIZE_LIMIT_REASON_RISK,
    ORDER_SIZE_LIMIT_REASON_SHARES,
    ORDER_SIZE_LIMIT_REASON_UNREADABLE,
    ORDER_SIZE_LIMIT_VENUES,
)
from execution.models import ExecutionCommand
from execution.size_limit import settings

_NAMES = {"paper": "Paper", "sim": "Sim"}
WHERE = "Settings > Loss limits"
STILL_WORKS = "Selling what you hold, covering a short, cancels, Flatten and KILL still work."


def _money(value: float) -> str:
    text = f"{abs(float(value)):,.2f}"
    return f"${text[:-3] if text.endswith('.00') else text}"


def _price(value: float) -> str:
    """``9.80``, ``0.1234``: a sub-dollar price keeps its fourth decimal."""
    if abs(value) >= 1:
        return f"{value:,.2f}"
    text = f"{value:.4f}".rstrip("0")
    whole, _, cents = text.partition(".")
    return f"{whole}.{cents.ljust(2, '0')}"


def _shares(value: float) -> str:
    return f"{value:,.0f}" if value == int(value) else f"{value:,g}"


def check(venue: str | None, shares: float | None, entry: float | None, stop: float | None) -> dict[str, Any] | None:
    """``{code, text}`` when ``venue``'s limit refuses an opening order of ``shares`` at ``entry`` with its
    protective ``stop`` (None: the order carries none), else None. Not a practice venue: None."""
    if venue not in ORDER_SIZE_LIMIT_VENUES:
        return None
    name = _NAMES[venue]
    setting = settings.current()
    if setting["source"] == "unreadable":
        return {"code": ORDER_SIZE_LIMIT_REASON_UNREADABLE,
                "text": (f"{setting['error']}, so {name} refuses your new orders until the order size limit is "
                         f"saved again in {WHERE}. {STILL_WORKS}")}
    row = setting["venues"][venue]
    max_shares, max_risk = row["max_shares"], row["max_risk_usd"]
    if max_shares is not None and shares is not None and shares > max_shares:
        return {"code": ORDER_SIZE_LIMIT_REASON_SHARES,
                "text": (f"{name} allows at most {max_shares:,} shares per order; this order is {_shares(shares)} "
                         f"shares. Lower the size, or change Max shares in {WHERE}. {STILL_WORKS}")}
    if max_risk is None:
        return None
    if entry is None or stop is None:
        return {"code": ORDER_SIZE_LIMIT_REASON_NO_STOP,
                "text": (f"{name} allows at most {_money(max_risk)} at risk per order, and this order has no "
                         f"stop, so its risk is unknown. Attach a stop, or clear Max risk at stop in {WHERE}. "
                         f"{STILL_WORKS}")}
    if shares is None:
        return None
    per_share = abs(float(entry) - float(stop))
    risk = round(shares * per_share, 2)          # cents: 100 x 0.20 is $20.00, never $20.000000000000004
    if risk <= max_risk:
        return None
    return {"code": ORDER_SIZE_LIMIT_REASON_RISK,
            "text": (f"{name} allows at most {_money(max_risk)} at risk per order; this order risks "
                     f"{_money(risk)} ({_shares(shares)} shares x ${_price(per_share)} from the entry "
                     f"{_price(float(entry))} to the stop {_price(float(stop))}). Lower the size or bring the "
                     f"stop closer, or change Max risk at stop in {WHERE}. {STILL_WORKS}")}


def refusal(cmd: ExecutionCommand, venue: str | None, *, covers: bool) -> dict[str, Any] | None:
    """``{code, text}`` when ``venue``'s order size limit refuses this command, else None.

    ``covers``: the door's own reading that a BUY covers a short (a close, never limited)."""
    if (cmd.source or "") != "manual" or cmd.operation not in ("place", "bracket"):
        return None
    side = (cmd.side or "").upper()
    if not ((side == "BUY" and not covers) or (side == "SELL" and bool(cmd.short_entry))):
        return None
    shares = float(cmd.qty) if cmd.qty is not None else float(cmd.shares) if cmd.shares is not None else None
    if cmd.operation == "bracket":
        entry = cmd.entry_price if cmd.entry_price is not None else cmd.limit_price
        return check(venue, shares, entry, cmd.stop_price)
    return check(venue, shares, None, None)
