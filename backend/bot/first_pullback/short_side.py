"""A short trigger's own rules before Nova's bot or Auto-entry sends it (ADR 049, #778 step 5).

The strategy that triggers decides the side: a long strategy buys, a short strategy shorts. A short goes out
through the same door as a long, and the door runs the one short check (``short_sale.check``). This reads the
same check first, on the same facts (``short_sale.facts.gather``, memory reads), so a short the door would
refuse is a stated skip on the timeline -- borrow, SSR, the halt, the hours, the margin and its 25% cushion --
never a refused order:

- **The price.** Off SSR the short sells at the scanner's entry, as a long buys at its entry: it never chases.
  Under SSR, on or not known, it sells at the ask -- the higher of the entry and the ask, so always above the
  bid and never under the plan. No ask on the book, or an ask at or over the buy stop, is no short.
- **The size** is the sleeve's (``bot.sizing``, ``side="short"``) for the risk from that price to the buy stop.
- **The check** runs with that size. ``not_long`` is left to ``admit.against_held`` (the same rule, said once),
  and ``live_key`` never applies: Nova's bot trades Paper and Sim only.

The verdicts ride on the sized result (``short_check``), so the runner records them on its audit line and the
squares (``bot.trigger_cells``) show what the bot read at the trigger. Reads only; the runners send.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from constants_bot import BOT_SKIP_SHORT_PRICE, SIDE_LONG, SIDE_SHORT, setup_side

logger = logging.getLogger(__name__)
_SKIP_RULES = frozenset({"not_long", "live_key"})
Blocker = tuple[str, str]


def side_of(event: dict[str, Any]) -> str:
    """The side a trigger enters: the event's, else its setup's."""
    if event.get("side") == SIDE_SHORT or setup_side(event.get("setup_type")) == SIDE_SHORT:
        return SIDE_SHORT
    return SIDE_LONG


def _num(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out == out and out > 0 else None


@dataclass(frozen=True)
class Priced:
    limit: float | None         # the short's sell price, or None
    at_ask: bool                # priced at the ask because of SSR
    ssr: str                    # "on" | "off" | "unknown"
    why: str | None             # why there is no price


def price(setup: dict[str, Any], facts: Any) -> Priced:
    """The short's sell price for the setup's levels and the stock's facts now."""
    entry, stop = _num(setup.get("entry")), _num(setup.get("stop"))
    state = str(getattr(getattr(facts, "ssr", None), "state", None) or "unknown")
    if entry is None or stop is None:
        return Priced(None, False, state, "the setup has no entry and buy stop to short by")
    if state == "off":
        return Priced(round(entry, 4), False, state, None)
    ask, bid = _num(getattr(facts, "ask", None)), _num(getattr(facts, "bid", None))
    said = "on" if state == "on" else "not known (it counts as on)"
    if ask is None:
        return Priced(None, False, state, f"SSR is {said}: the short sells at the ask, and the book shows no ask")
    limit = round(max(entry, ask), 4)
    if bid is not None and limit <= bid:
        return Priced(None, False, state, f"SSR is {said}: the ask {ask:g} is not above the bid {bid:g}")
    if limit >= stop:
        return Priced(None, False, state, f"SSR is {said}: the short sells at the ask {ask:g}, at or over its buy "
                                          f"stop {stop:g} -- no room for a short")
    return Priced(limit, True, state, None)


def gather(symbol: str, venue: str | None) -> tuple[Any | None, str | None]:
    """``(facts, error)``: the short check's facts now (memory reads), or why they could not be read."""
    try:
        from short_sale.facts import gather as _gather

        return _gather(symbol, venue or "paper"), None
    except Exception as exc:
        logger.warning("bot: the short check's facts for %s could not be read", symbol, exc_info=True)
        return None, f"the short check's facts could not be read ({exc})"


def verdicts(symbol: str, qty: float, priced: Priced, setup: dict[str, Any], facts: Any,
             venue: str | None) -> tuple[list[dict[str, Any]], str | None]:
    """Every rule's verdict for this short, as the door would judge it, and an error when it cannot be read."""
    try:
        from short_sale import check, door

        order = check.Order(symbol=symbol, qty=float(qty), entry=priced.limit, stop=_num(setup.get("stop")),
                            target=_num(setup.get("target1")))
        account = door.read_account(symbol, venue or "paper")
        found = check.rules(order, facts, account, live_key=None)
    except Exception as exc:
        logger.warning("bot: the short check for %s could not be read", symbol, exc_info=True)
        return [], f"the short check could not be read ({exc})"
    return [v.as_dict() for v in found if v.id not in _SKIP_RULES], None


def blocks(sized: dict[str, Any]) -> list[Blocker]:
    """The short check's failures, each as ``(code, words)``; nothing for a long."""
    if sized.get("side") != SIDE_SHORT:
        return []
    out: list[Blocker] = []
    if sized.get("short_error"):
        out.append(("SHORT_CHECK_UNREAD", f"{sized['short_error']}: no automatic short"))
    for v in sized.get("short_check") or []:
        if not v.get("ok"):
            out.append((str(v.get("code") or "SHORT_REFUSED"), f"{v.get('label')}: {v.get('text')}"))
    return out


def audit_inputs(sized: dict[str, Any] | None) -> dict[str, Any]:
    """A short's price and its short check, as the bot or Auto-entry read them at the trigger: the audit
    line carries them so the squares (``bot.trigger_short``) show the verdict. ``{}`` for a long."""
    if not sized or sized.get("side") != SIDE_SHORT:
        return {}
    return {"side": SIDE_SHORT, "ssr": sized.get("ssr"), "priced_at_ask": bool(sized.get("priced_at_ask")),
            "short_limit": sized.get("limit"), "short_check": sized.get("short_check") or [],
            "short_error": sized.get("short_error")}


def size(event: dict[str, Any], caps: dict[str, Any], left: float, venue: str | None) -> dict[str, Any]:
    """The sleeve's size for a short trigger, its price, and the short check at that size."""
    from bot.sizing import size as sized_by

    sym = str(event.get("symbol") or "").strip().upper()
    setup = event.get("setup") or {}
    facts, error = gather(sym, venue)
    base = {"side": SIDE_SHORT, "limit": None, "priced_at_ask": False, "ssr": None, "short_check": [],
            "short_error": None}
    if facts is None:
        return {**base, "qty": 0, "by_risk": None, "capped_by": None, "text": error, "short_error": error,
                "price_code": BOT_SKIP_SHORT_PRICE}
    priced = price(setup, facts)
    base.update(priced_at_ask=priced.at_ask, ssr=priced.ssr, limit=priced.limit)
    if priced.limit is None:
        return {**base, "qty": 0, "by_risk": None, "capped_by": None, "text": priced.why,
                "price_code": BOT_SKIP_SHORT_PRICE}
    out = {**base, **sized_by(caps["risk_usd"], priced.limit, setup.get("stop"), caps["max_shares"], left,
                              side=SIDE_SHORT)}
    if out["qty"] >= 1:
        found, why = verdicts(sym, out["qty"], priced, setup, facts, venue)
        out.update(short_check=found, short_error=why)
    return out
