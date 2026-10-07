"""What a short needs from the account and the clock, for the Bots page's answer line (ADR 049, #778 step 5).

``GET /api/bot/session`` carries ``shorts``: the facts the one short check (``short_sale.check``) reads before
any short, the bot's or yours, said once for the desk's venue -- a margin account (on Live, by IBKR's own
figures), at least $2,000 of equity, the short hours by the venue's clock, and Live, where shorts wait on the
Live short proof and the operator's ``IBKR_SHORT_ENABLED`` (ADR 048 step 6). Each is ``{ok: true | false |
null, text, value}``; ``null`` is not known, never a pass. ``live_cover`` says whether Nova covers Live shorts
at 15:55 (the switch is on), and ``day_cover`` carries the day cover's alarms (``short_sale.cover_alarm``),
which every desk window polls through this session. Memory reads only; never a wait on IBKR.
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
    if venue == "live" and cls == "margin" and str(summary.get("ibkr_account_class") or "") != "margin":
        margin = _chip(False, "IBKR's own figures do not show a margin account (the IBKR_ACCOUNT_CLASS override "
                              "in .env never counts for a short)")
    else:
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


def _proof() -> tuple[bool, int, int]:
    """The Live short proof: ``(complete, items done, items)``; a proof Nova cannot read is incomplete."""
    from short_proof import store, view as proof_view

    doc, _error = store.read()
    done, total = proof_view.done(doc)
    return proof_view.status()[0], done, total


def _live() -> dict[str, Any]:
    from ibkr import safety

    try:
        complete, done, total = _proof()
    except Exception:
        logger.warning("bot: the Live short proof could not be read for the short chips", exc_info=True)
        return _chip(False, "Live shorts: the Live short proof could not be read (the engine log has the details), "
                            "so Live refuses every short; Nova's bot never trades Live")
    proof = "the Live short proof is complete" if complete else f"the Live short proof: {done} of {total} done"
    if safety.short_enabled() and complete:
        return _chip(None, f"IBKR_SHORT_ENABLED is on and {proof}: Live shorts by hand; Nova's bot never trades Live",
                     f"{done}/{total}")
    key = "IBKR_SHORT_ENABLED is on" if safety.short_enabled() else "IBKR_SHORT_ENABLED is off"
    return _chip(False, f"Live shorts: after the Paper proof -- {proof}, {key}, and Nova's bot never trades Live",
                 f"{done}/{total}")


def view(venue: str | None) -> dict[str, Any]:
    """``{margin_account, equity, hours, live, live_cover, day_cover}`` for the desk's venue."""
    from ibkr import safety
    from short_sale import cover_alarm

    where = venue or "paper"
    margin, equity = _account(where)
    return {"venue": where, "margin_account": margin, "equity": equity, "hours": _hours(where), "live": _live(),
            "live_cover": bool(safety.short_enabled()), "day_cover": cover_alarm.view()}
