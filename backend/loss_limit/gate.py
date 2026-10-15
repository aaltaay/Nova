"""No new buys: the order an account refuses after its daily loss limit, and the words (ADR 056).

``execution.service`` asks ``buy_refusal`` with the door's own venue for every place, bracket or
exit pair from a non-protective source, yours and the bots' alike: a BUY, and a SELL that opens a
short. Selling what is held, a BUY that covers a short (ADR 048), cancels, Flatten and KILL are
never refused. The bot and stock mode ask ``buys_stopped``. A buy is refused only while No new buys
is checked and the account tripped today; raising the limit or unchecking it clears the trip
(``loss_limit.state.clear``).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from constants_loss_limit import LOSS_LIMIT_REASON_NO_NEW_BUYS

_ET = ZoneInfo("America/New_York")
_NAMES = {"live": "Live", "paper": "Paper", "sim": "Sim"}
_PROTECTIVE = frozenset({"kill", "cancel_working", "flatten"})
STILL_WORKS = "Selling what you hold, covering a short, cancels, Flatten and KILL still work."
TO_BUY_AGAIN = "To buy again, raise the limit or uncheck No new buys in Settings > Loss limits."


def account_name(account: str | None) -> str:
    return _NAMES.get(str(account), str(account))


def money(value: float | None) -> str:
    if value is None:
        return "unknown"
    text = f"{abs(float(value)):,.2f}"
    return f"${text[:-3] if text.endswith('.00') else text}"


def _clock(epoch: Any) -> str | None:
    if not isinstance(epoch, (int, float)) or isinstance(epoch, bool):
        return None
    return f"{datetime.fromtimestamp(float(epoch), tz=_ET):%H:%M} ET"


def _until(epoch: float) -> str:
    end = datetime.fromtimestamp(epoch, tz=_ET)
    return f"{end:%H:%M} ET {end:%a} {end:%b} {end.day}"


def stopped(account: str | None, now: float | None = None) -> dict[str, Any] | None:
    """``{account, tripped_at, loss, limit_usd, until, text}`` while ``account`` refuses new buys."""
    from loss_limit import settings, state

    if account is None or not settings.current()["no_new_buys"]:
        return None
    row = state.record(account, now)
    if not row.get("tripped_at"):
        return None
    end = state.until(now)
    when = _clock(row.get("tripped_at"))
    said = f"Daily loss limit reached on {account_name(account)}" + (f" at {when}" if when else "")
    said += f" (down {money(row.get('tripped_loss'))} against your {money(row.get('limit_usd'))} limit)"
    return {"account": account, "tripped_at": row.get("tripped_at"), "loss": row.get("tripped_loss"),
            "limit_usd": row.get("limit_usd"), "until": end,
            "text": f"{said}: no new buys until {_until(end)}. {STILL_WORKS} {TO_BUY_AGAIN}"}


def buys_stopped(account: str | None, now: float | None = None) -> bool:
    return stopped(account, now) is not None


def buy_refusal(
    side: str | None,
    source: str | None,
    venue: str | None,
    *,
    short_entry: bool = False,
    covers: bool = False,
) -> dict[str, Any] | None:
    """``{code, text}`` when ``venue`` refuses this order under No new buys, else None.

    It refuses what opens or adds: a BUY that covers nothing, or a SELL that opens a short."""
    upper = (side or "").upper()
    opens = (upper == "BUY" and not covers) or (upper == "SELL" and short_entry)
    if not opens or source in _PROTECTIVE:
        return None
    held = stopped(venue)
    if held is None:
        return None
    return {"code": LOSS_LIMIT_REASON_NO_NEW_BUYS, "text": held["text"]}
