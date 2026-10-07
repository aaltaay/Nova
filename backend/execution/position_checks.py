"""What a place may do to the position it trades (ADR 007, ADR 009, ADR 048).

The account checks of ``execution.validate`` hand a plain SELL, a BUY and a long bracket here:

- **a SELL** is only ever a close of what is held: ``NO_POSITION`` when nothing is long, ``OVERSELL``
  past the long less the sells already in flight (a short opens only with ``short_entry``, through
  ``short_sale.door``);
- **a BUY while the account is short** is a cover, a close (``covers_short``): held to the short
  less the covers in flight (``OVERCOVER``), never to buying power and never locked by the day lock
  (ADR 048 gap 3);
- **a long bracket** is refused while short: its SELL exits would open the short again
  (``BRACKET_WHILE_SHORT``).

The positions are the venue's own (``ibkr.account``: IBKR's on Live, the practice ledger's on Paper
and Sim). A position Nova cannot read refuses, ``POSITION_UNAVAILABLE`` -- never read as flat.
"""
from __future__ import annotations

import logging

from execution import inflight as _inflight
from execution.models import ExecutionCommand
from ibkr import account as _account
from ibkr.errors import IbkrAccountError

logger = logging.getLogger(__name__)

Verdict = tuple[bool, str, str | None]
_EPS = 1e-6


def position_qty(symbol: str) -> float:
    """Verified long qty for ``symbol`` via ``account.long_qty`` (positions SSOT).

    Returns ``0.0`` when flat. Raises ``IbkrAccountError`` when the broker
    position cache cannot be read (caller maps that to ``POSITION_UNAVAILABLE``).
    """
    return _account.long_qty(symbol)


def covers_short(cmd: ExecutionCommand) -> bool:
    """A BUY place while the account is short the stock: a cover, a close (ADR 048 gap 3).

    The all-stop's day lock reads it (``execution.service``): a cover is never locked, like selling
    what you hold. A position Nova cannot read is not a cover here -- the account check then
    refuses the order ``POSITION_UNAVAILABLE`` and says why.
    """
    if cmd.operation != "place" or (cmd.side or "").upper() != "BUY" or getattr(cmd, "short_entry", False):
        return False
    try:
        return _account.short_qty(cmd.normalized_symbol() or "") > 0
    except IbkrAccountError:
        logger.warning("validate: short_qty unreadable -- %s's BUY is not treated as a cover", cmd.normalized_symbol())
        return False


def short_open(cmd: ExecutionCommand) -> tuple[float | None, Verdict | None]:
    """``(shares short, None)``, or ``(None, refusal)`` when the position cannot be read."""
    symbol = cmd.normalized_symbol() or ""
    try:
        return _account.short_qty(symbol), None
    except IbkrAccountError as exc:
        logger.exception("validate: short_qty failed — refusing BUY for %s: %s", symbol, exc)
        return None, (False, f"BUY refused — position unavailable: {exc}", "POSITION_UNAVAILABLE")


def cover_refusal(cmd: ExecutionCommand) -> Verdict:
    """BUY mirror of OVERSELL — never buy past the short being covered.

    Only fires while the account is short that symbol: an opening BUY from
    flat or long is a normal entry and stays on the BuyingPower gate alone.
    """
    symbol = cmd.normalized_symbol() or ""
    held, refused = short_open(cmd)
    if refused is not None:
        return refused
    if not held or held <= 0:
        return True, "OK", None

    working = _inflight.committed_qty(symbol, "BUY")
    available = held - working
    buy_qty = float(cmd.qty or 0)
    if buy_qty > available + _EPS:
        detail = f"BUY qty {buy_qty} exceeds short position {held}"
        if working > 0:
            detail = (
                f"BUY qty {buy_qty} exceeds {available} available "
                f"(short {held}, {working} already sent)"
            )
        return False, detail, "OVERCOVER"
    return True, "OK", None


def long_bracket_refusal(cmd: ExecutionCommand) -> Verdict:
    """Refuse a long bracket while short: its SELL legs would re-open the short."""
    symbol = cmd.normalized_symbol() or ""
    try:
        held = _account.short_qty(symbol)
    except IbkrAccountError as exc:
        logger.exception(
            "validate: short_qty failed — refusing bracket for %s: %s", symbol, exc,
        )
        return False, f"bracket refused — position unavailable: {exc}", "POSITION_UNAVAILABLE"
    if held > 0:
        return (
            False,
            f"bracket refused — account is short {held} {symbol}; cover "
            "without legs first (the bracket's exit legs would re-open the short)",
            "BRACKET_WHILE_SHORT",
        )
    return True, "OK", None


def sell_refusal(cmd: ExecutionCommand) -> Verdict:
    """A plain SELL closes a long: never past it, less the sells already in flight."""
    symbol = cmd.normalized_symbol() or ""
    try:
        pos_qty = position_qty(symbol)
    except IbkrAccountError as exc:
        logger.exception("validate: long_qty failed — refusing SELL for %s: %s", symbol, exc)
        return False, f"SELL refused — position unavailable: {exc}", "POSITION_UNAVAILABLE"
    sell_qty = float(cmd.qty or 0)
    if pos_qty <= 0:
        return False, "SELL refused — no long position to reduce", "NO_POSITION"
    # Shares already sent and not yet resolved are spent, even
    # though the broker position will not move until they fill.
    working = _inflight.committed_qty(symbol, "SELL")
    available = pos_qty - working
    if sell_qty > available + _EPS:
        if working > 0:
            # Never a negative count (QA R35): more shares already
            # sent than held leaves none available, not "-5.0".
            return (
                False,
                f"SELL qty {sell_qty} exceeds {max(0.0, available)} available "
                f"(long {pos_qty}, {working} already sent)",
                "OVERSELL",
            )
        return False, f"SELL qty {sell_qty} exceeds position {pos_qty}", "OVERSELL"
    return True, "OK", None
