"""The exit-only one-cancels-other pair, and the two halves a target sells in (#681, ADR 007 amendment 2026-10-12).

``operation: "exit_oco"`` hands the venue, for shares it already holds, a stop for every share and one or
two limits -- target 1 for the first half, target 2 for the rest -- committed once by the execution door
(``venue_door.commit_position``): the stop's fill cancels the targets, a target's fill shrinks the stop to
the shares left (it stays where it is), so nothing sells twice or past flat. A long's pair sells (SELL
stop under the price, SELL limits over it); a short's covers (BUY stop over, BUY limits under), and a
cover is a close (Invariant #7). A bracket that sells in two halves carries the same second target.

This module holds the rules, pure over the command's numbers, plus the one account read:

- ``split``: how a position splits into its halves (the first half the smaller part of an odd count; a
  position too small to split sells whole at target 1);
- ``halves_error`` / ``shape_error``: the door's and the practice broker's checks, one set of words;
- ``account_refusal``: the shares are held, and not already committed to another close.

Live is refused ``EXIT_OCO_LIVE`` until its proof (#606). Live's shape is written in
``architecture/schema/execution.md`` ("The exit-only pair").
"""
from __future__ import annotations

import logging
import math
from typing import Any

from constants import IBKR_FRACTIONAL_ORDER_API_MSG
from constants_practice import (
    EXIT_OCO_FIELDS_CODE,
    EXIT_OCO_GEOMETRY_CODE,
    EXIT_TARGET1_FRACTION_DEFAULT,
)

logger = logging.getLogger(__name__)

Refusal = tuple[str, str]
_EPS = 1e-9


def _num(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) and out > 0 else None


def beyond(target2: Any, target1: Any, *, short: bool) -> bool:
    """``target2`` is further from the stop than ``target1``: over it for a long, under it for a short."""
    t1, t2 = _num(target1), _num(target2)
    if t1 is None or t2 is None:
        return False
    return t2 < t1 - _EPS if short else t2 > t1 + _EPS


def split(qty: Any, target1: Any, target2: Any, fraction: Any = None, *, short: bool = False) -> tuple[int, int]:
    """``(first half, second half)`` in whole shares; a second half of 0 sells everything at target 1.

    No second target (null, absent, or not beyond target 1) sells whole at target 1, exactly as before
    two halves existed. ``fraction`` is the first half's share (``EXIT_TARGET1_FRACTION_DEFAULT`` when
    not a number strictly between 0 and 1), rounded down: an odd count gives the first half the smaller
    part, and a position the rounding leaves one half empty of -- a single share -- sells whole at target 1.
    """
    try:
        shares = int(math.floor(float(qty) + _EPS))
    except (TypeError, ValueError):
        return 0, 0
    if shares <= 0:
        return 0, 0
    if not beyond(target2, target1, short=short):
        return shares, 0
    try:
        part = float(fraction)
    except (TypeError, ValueError):
        part = EXIT_TARGET1_FRACTION_DEFAULT
    if not (math.isfinite(part) and 0 < part < 1):
        part = EXIT_TARGET1_FRACTION_DEFAULT
    first = int(math.floor(shares * part + _EPS))
    if first < 1 or first >= shares:
        return shares, 0
    return first, shares - first


def _whole(qty: Any) -> float | None:
    q = _num(qty)
    if q is None or abs(q - round(q)) > _EPS:
        return None
    return float(round(q))


def halves_error(qty: Any, target1: Any, target2: Any, target1_qty: Any, *, short: bool) -> Refusal | None:
    """``(detail, code)`` when a second target and the first half's shares do not hang together.

    No second target: ``target1_qty`` is absent or every share. A second target: beyond target 1, and
    the first half whole shares, at least one, short of every share.
    """
    shares = _whole(qty)
    if target2 is None:
        if target1_qty is not None and (shares is None or _whole(target1_qty) != shares):
            return ("target1_qty is the first half's shares: without a second target every share sells at "
                    "target 1", EXIT_OCO_FIELDS_CODE)
        return None
    t1, t2 = _num(target1), _num(target2)
    if t1 is None or t2 is None:
        return "target2_price needs a target_price beside it, both prices over zero", EXIT_OCO_FIELDS_CODE
    if not beyond(t2, t1, short=short):
        need = "under" if short else "over"
        return (f"target 2 {t2:g} must be {need} target 1 {t1:g}: it sells the second half further on",
                EXIT_OCO_GEOMETRY_CODE)
    first = _whole(target1_qty)
    if shares is None or first is None or not 1 <= first <= shares - 1:
        return ("target1_qty must be whole shares, at least one, short of every share -- the rest sell at "
                "target 2", EXIT_OCO_FIELDS_CODE)
    return None


def shape_error(*, side: Any, qty: Any, stop: Any, target1: Any, target2: Any = None,
                target1_qty: Any = None) -> Refusal | None:
    """``(detail, code)`` when an exit pair's numbers do not hang together, else None.

    A SELL pair (a long's): stop < target 1 (< target 2). A BUY pair (a short's cover): stop > target 1
    (> target 2). Every share whole; the execution door and the practice broker say it in these words.
    """
    side_u = str(side or "").strip().upper()
    if side_u not in ("BUY", "SELL"):
        return "an exit pair's side is SELL (a long's) or BUY (a short's cover)", "SIDE_INVALID"
    q = _num(qty)
    if q is None:
        return "an exit pair's qty must be greater than zero", "QTY_INVALID"
    if _whole(q) is None:
        return IBKR_FRACTIONAL_ORDER_API_MSG, "QTY_FRACTIONAL_API"
    s, t1 = _num(stop), _num(target1)
    if s is None or t1 is None:
        return "an exit pair needs its stop_price and target_price, both over zero", EXIT_OCO_FIELDS_CODE
    short = side_u == "BUY"
    if (s <= t1 + _EPS) if short else (s >= t1 - _EPS):
        need = "over" if short else "under"
        return (f"the stop {s:g} must be {need} target 1 {t1:g} -- it would fill the moment the target does",
                EXIT_OCO_GEOMETRY_CODE)
    return halves_error(q, t1, target2, target1_qty, short=short)


def command_error(cmd: Any) -> Refusal | None:
    """The door's structural check of an ``exit_oco`` command (``execution.validate``)."""
    from ibkr import safety as _safety

    if cmd.source in _safety.PROTECTIVE_SOURCES:
        return (f"source {cmd.source} cannot send an exit pair -- protective orders carry no legs",
                EXIT_OCO_FIELDS_CODE)
    if getattr(cmd, "short_entry", False):
        return "an exit pair closes a position: it never opens a short", EXIT_OCO_FIELDS_CODE
    if getattr(cmd, "good_for_sec", None) is not None:
        return "an exit pair rests until it fills or is taken back: it carries no good_for_sec", EXIT_OCO_FIELDS_CODE
    return shape_error(side=cmd.side, qty=cmd.qty, stop=cmd.stop_price, target1=cmd.target_price,
                       target2=cmd.target2_price, target1_qty=cmd.target1_qty)


def account_refusal(cmd: Any) -> tuple[bool, str, str | None]:
    """The venue holds the shares the pair closes, less the closes already in flight (``execution.inflight``).

    A SELL pair sells a long (``NO_POSITION`` / ``OVERSELL``); a BUY pair covers a short (``NO_POSITION``
    / ``OVERCOVER``). A position Nova cannot read refuses, ``POSITION_UNAVAILABLE`` -- never read as flat.
    """
    from execution import inflight
    from ibkr import account as _account
    from ibkr.errors import IbkrAccountError

    symbol = cmd.normalized_symbol() or ""
    side = str(cmd.side or "").upper()
    short = side == "BUY"
    try:
        held = float(_account.short_qty(symbol) if short else _account.long_qty(symbol))
    except IbkrAccountError as exc:
        logger.exception("validate: position unreadable -- refusing the exit pair for %s: %s", symbol, exc)
        return False, f"exit pair refused -- position unavailable: {exc}", "POSITION_UNAVAILABLE"
    if held <= _EPS:
        what = "short to cover" if short else "long to sell"
        return False, f"exit pair refused -- no {symbol} {what}: it closes shares you hold", "NO_POSITION"
    working = inflight.committed_qty(symbol, side)
    available = held - working
    qty = float(cmd.qty or 0)
    if qty > available + 1e-6:
        code = "OVERCOVER" if short else "OVERSELL"
        word = "short" if short else "long"
        if working > 0:
            return (False, f"{side} qty {qty:g} exceeds {max(0.0, available):g} available ({word} {held:g}, "
                           f"{working:g} already sent)", code)
        return False, f"{side} qty {qty:g} exceeds position {held:g}", code
    return True, "OK", None
