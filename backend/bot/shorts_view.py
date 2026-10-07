"""What a short needs from the account and the clock, for the Bots page's answer line (ADR 049, #778 step 5).

``GET /api/bot/session`` carries ``shorts``: the facts the one short check (``short_sale.check``) reads before
any short, the bot's or yours, said once for the desk's venue -- a margin account, at least $2,000 of equity,
the short hours by the venue's clock, and Live, where shorts wait on the Paper proof (step 6) and the operator's
``IBKR_SHORT_ENABLED``. Each is ``{ok: true | false | null, text, value}``; ``null`` is not known, never a pass.
Memory reads only (the venue's account summary as the short check reads it); never a wait on IBKR.
"""
from __future__ import annotations

import logging
from typing import Any

from constants_shorts import SHORT_MIN_EQUITY

logger = logging.getLogger(__name__)


def _chip(ok: bool | None, text: str, value: str | None = None) -> dict[str, Any]:
    return {"ok": ok, "text": text, "value": value}


def _summary(venue: str) -> dict[str, Any] | None:
    if venue in ("paper", "sim"):
        from practice.broker import for_venue

        return for_venue(venue).account_summary()
    from ibkr import account as _account

    return _account.get_account_summary()


def _num(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out == out else None


def _account(venue: str) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        summary = _summary(venue) or {}
    except Exception as exc:
        logger.warning("bot: the %s account could not be read for the short chips", venue, exc_info=True)
        said = f"the account could not be read ({exc})"
        return _chip(None, said), _chip(None, said)
    if not summary or summary.get("connected") is False or summary.get("pending"):
        said = "the account has not loaded yet"
        return _chip(None, said), _chip(None, said)
    cls = str(summary.get("account_class") or "").strip().lower()
    margin = (_chip(True, "a margin account: it can short") if cls == "margin" else
              _chip(False, "not a margin account: only a margin account can short") if cls else
              _chip(None, "the account's type is not known yet"))
    equity = _num(summary.get("NetLiquidation"))
    if equity is None:
        return margin, _chip(None, "the account's net liquidation is not known yet")
    shown = f"${equity:,.0f}"
    if equity < SHORT_MIN_EQUITY:
        return margin, _chip(False, f"{shown} of equity: a short needs ${SHORT_MIN_EQUITY:,.0f} (FINRA's margin "
                                    "minimum)", shown)
    return margin, _chip(True, f"{shown} of equity, over the ${SHORT_MIN_EQUITY:,.0f} a short needs", shown)


def _hours(venue: str) -> dict[str, Any]:
    from short_sale import hours

    try:
        now = hours.venue_now(venue)
    except Exception as exc:
        logger.warning("bot: the %s clock could not be read for the short chips", venue, exc_info=True)
        return _chip(None, f"the venue's clock could not be read ({exc})")
    refused = hours.entry_refusal(now)
    got = hours.hours_on(now)
    until = hours.clock(got.last_short_ts) if got else "15:50"
    cover = hours.clock(got.cover_ts) if got else "15:55"
    if refused:
        return _chip(False, refused, f"until {until}")
    return _chip(True, f"new shorts until {until} ET; Nova covers what is left at {cover}", f"until {until}")


def _live() -> dict[str, Any]:
    from ibkr import safety

    if safety.short_enabled():
        return _chip(None, "IBKR_SHORT_ENABLED is on: Live shorts by hand; Nova's bot never trades Live")
    return _chip(False, "Live shorts: after the Paper proof -- IBKR_SHORT_ENABLED is off, and Nova's bot never "
                        "trades Live")


def view(venue: str | None) -> dict[str, Any]:
    """``{margin_account, equity, hours, live}`` for the desk's venue."""
    where = venue or "paper"
    margin, equity = _account(where)
    return {"venue": where, "margin_account": margin, "equity": equity, "hours": _hours(where), "live": _live()}
