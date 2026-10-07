"""The squares' both-sides gates (ADR 049, #778 step 5): "not against you" for every trade, and the short
check's own block behind the orange divider -- borrow, SSR, no halt in 10 min, margin 25%, before 15:50.

A trigger is judged from what was recorded at it, as the other squares are (``bot.trigger_cells``):

- **What the bot read.** The bot and Auto-entry write every judgment on the audit stream: a skip with its
  codes, an entry, a refusal. ``judgments(rows)`` keeps the latest per setup id. ``not_against`` reads its
  codes (``BOT_SKIP_HELD_OTHER_SIDE``), and a short's record carries the short check it read
  (``inputs.short_check``, ``bot.first_pullback.short_side``) -- borrow, the halt, the margin and its cushion.
  A trigger nothing judged (a stock whose Entry was You) says so: ``null``, never a pass.
- **What the trigger itself says.** Its time against the short hours (``short_sale.hours``), and the SSR the
  journal stamped on it. **The SSR square is never red**: under SSR the short sells at the ask, so SSR on --
  or not known, which counts as on -- is an amber pass (``warn``).

``now_cells`` answers the same squares for a stock this minute (``bot.trigger_now``), from the desk: the
position, and for a short strategy that is On the short check's facts (memory reads). The margin square needs
a size, so it is read only for a short setup armed or near on the stock. A long trigger, or a stock with no
short strategy On, leaves the short block empty. Owner: this module (no state).
"""
from __future__ import annotations

import logging
from typing import Any

from bot.trigger_cells import cell
from constants_bot import (
    BOT_AUDIT_ACTION_TRADE,
    BOT_KIND_SETUP_ENTRY,
    BOT_KIND_SETUP_SHORT,
    BOT_SKIP_HELD_OTHER_SIDE,
    BOT_TRIGGER_SHORT_GATES,
    SIDE_SHORT,
    setup_side,
)
from constants_stock_mode import STOCK_MODE_AUDIT_ACTION

logger = logging.getLogger(__name__)
SHORT_GATE_IDS = tuple(gate for gate, _label in BOT_TRIGGER_SHORT_GATES)
_JUDGED = {(BOT_AUDIT_ACTION_TRADE, "skipped"), (BOT_KIND_SETUP_ENTRY, "ok"), (BOT_KIND_SETUP_ENTRY, "failed"),
           (BOT_KIND_SETUP_SHORT, "ok"), (BOT_KIND_SETUP_SHORT, "failed"), (STOCK_MODE_AUDIT_ACTION, "skipped"),
           (STOCK_MODE_AUDIT_ACTION, "sent"), (STOCK_MODE_AUDIT_ACTION, "refused")}
# The short check's rules, by the square that shows them.
_RULES_OF = {"short_borrow": ("borrow",), "short_halt": ("halt",), "short_margin": ("account", "margin", "cushion")}
_NOT_READ = "not recorded: Nova did not judge this trigger (its Entry was You, or the bot was not playing)"


def warn(ok: bool | None, why: str) -> dict[str, Any]:
    """An amber square: it passes, and says what it changed."""
    return {"ok": ok, "why": why, "warn": True}


def is_short(t: dict[str, Any]) -> bool:
    return t.get("side") == SIDE_SHORT or setup_side(t.get("setup_type")) == SIDE_SHORT


# -- what was recorded -----------------------------------------------------------------------------
def judgments(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """The latest judgment of each setup id the bot or Auto-entry read: its audit line's inputs."""
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        inputs = row.get("inputs") if isinstance(row.get("inputs"), dict) else {}
        sid = inputs.get("setup_id")
        if sid and (row.get("action"), row.get("outcome")) in _JUDGED:
            out[str(sid)] = {**inputs, "outcome": row.get("outcome"), "reason": row.get("reason")}
    return out


def not_against(t: dict[str, Any], judged: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """You held none of the stock the other way when Nova judged this trigger."""
    j = judged.get(str(t.get("setup_id") or ""))
    if j is None:
        return cell(None, _NOT_READ)
    codes = list(j.get("codes") or ([j["code"]] if j.get("code") else []))
    if BOT_SKIP_HELD_OTHER_SIDE in codes:
        reasons = [str(r) for r in (j.get("reasons") or [])]
        said = next((r for r in reasons if "hold" in r or "position" in r), None)
        return cell(False, said or f"you held {t['symbol']} the other way")
    other = "long" if is_short(t) else "short"
    return cell(True, f"you held no {t['symbol']} {other}")


def _from_check(gate: str, check: list[dict[str, Any]]) -> dict[str, Any]:
    found = [v for v in check if v.get("id") in _RULES_OF[gate]]
    if not found:
        return cell(None, "the bot's short check did not reach this rule")
    bad = [v for v in found if not v.get("ok")]
    if bad:
        return cell(False, "; ".join(f"{v.get('label')}: {v.get('text')}" for v in bad))
    return cell(True, "; ".join(str(v.get("text")) for v in found))


def ssr_cell(state: str | None) -> dict[str, Any]:
    """Never red: under SSR the short sells at the ask."""
    if state == "on":
        return warn(True, "SSR · at the ask: under SSR a short sells only above the bid, so the bot sells at the ask")
    if state == "unknown":
        return warn(True, "SSR not known · at the ask: it counts as on, so the bot sells at the ask")
    if state == "off":
        return cell(True, "no SSR: the short sells at its entry")
    return cell(None, "the journal did not record SSR at this trigger")


def hours_cell(ts: float) -> dict[str, Any]:
    from short_sale import hours

    refused = hours.entry_refusal(float(ts))
    if refused:
        return cell(False, refused)
    got = hours.hours_on(float(ts))
    last = hours.clock(got.last_short_ts) if got else "15:50"
    return cell(True, f"{hours.clock(float(ts))} ET, before the {last} last short")


def short_cells(t: dict[str, Any], judged: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """A short trigger's block; ``{}`` for a long (its block stays empty)."""
    if not is_short(t):
        return {}
    j = judged.get(str(t.get("setup_id") or "")) or {}
    check = [v for v in (j.get("short_check") or []) if isinstance(v, dict)]
    if check:
        read = {g: _from_check(g, check) for g in _RULES_OF}
    elif j.get("short_error"):
        read = {g: cell(None, str(j["short_error"])) for g in _RULES_OF}
    elif j:
        read = {g: cell(None, "the bot judged it without reading the short check (it stopped at an earlier rule)")
                for g in _RULES_OF}
    else:
        read = {g: cell(None, _NOT_READ) for g in _RULES_OF}
    return {"short_borrow": read["short_borrow"], "short_ssr": ssr_cell(j.get("ssr") or t.get("ssr")),
            "short_halt": read["short_halt"], "short_margin": read["short_margin"], "short_hours": hours_cell(t["ts"])}


# -- now ---------------------------------------------------------------------------------------------
def not_against_now(sym: str, sides: set[str]) -> dict[str, Any]:
    """The sides the On strategies would enter, against the position you hold now."""
    from bot.first_pullback.admit import against_held

    if not sides:
        return cell(None, "no strategy is On")
    blocked = {side: against_held(sym, side) for side in sorted(sides)}
    stopped = {side: b for side, b in blocked.items() if b is not None}
    if not stopped:
        return cell(True, f"you hold no {sym} the other way")
    words = "; ".join(b[1] for b in stopped.values())
    if len(stopped) == len(sides):
        return cell(False, words)
    open_side = next(side for side in sides if side not in stopped)
    return cell(True, f"{words} -- its {open_side} strategies may still trade")


def now_cells(sym: str, venue: str | None, armed: list[dict[str, Any]], row: dict[str, Any]) -> dict[str, Any]:
    """The short block for a stock with a short strategy On: the short check's facts now. ``armed``: the
    stock's short lanes armed or near (the margin square reads the first one's size)."""
    from bot.first_pullback import short_side

    facts, error = short_side.gather(sym, venue)
    if facts is None:
        return {g: cell(None, str(error)) for g in SHORT_GATE_IDS}
    out = {"short_ssr": ssr_cell(facts.ssr.state), "short_hours": hours_cell(facts.now)}
    out["short_halt"] = cell(facts.halt.ok, facts.halt.text)    # unknown is never a pass (ADR 048)
    borrow = facts.borrow or {}
    shares = borrow.get("shortable_shares")
    if facts.borrow is None or borrow.get("stale"):
        out["short_borrow"] = cell(False, f"no fresh borrow read for {sym}: Nova asks IBKR when a short comes near")
    else:
        out["short_borrow"] = cell(bool(shares) and float(shares) > 0,
                                   f"IBKR lists {float(shares or 0):,.0f} {sym} shares to borrow")
    out["short_margin"] = _margin_now(sym, venue, armed, row, facts)
    return out


def _margin_now(sym: str, venue: str | None, armed: list[dict[str, Any]], row: dict[str, Any],
                facts: Any) -> dict[str, Any]:
    from bot.first_pullback import short_side
    from bot.first_pullback.admit import exposure
    from bot.sizing import size
    from bot.sleeve import of as sleeve_of

    if not armed:
        return cell(None, f"no short setup is armed or near on {sym}: the margin is read for its size at the trigger")
    lane = armed[0]
    setup = lane.get("setup") or {}
    priced = short_side.price(setup, facts)
    if priced.limit is None:
        return cell(False, str(priced.why))
    caps = sleeve_of(row)
    try:
        left = float(caps["bp_budget_usd"]) - exposure(row, venue)
    except Exception as exc:
        logger.warning("triggers audit: the budget left for %s could not be read", sym, exc_info=True)
        return cell(None, f"what Nova's entries hold could not be read ({exc})")
    sized = size(caps["risk_usd"], priced.limit, setup.get("stop"), caps["max_shares"], left, side=SIDE_SHORT)
    if sized["qty"] < 1:
        return cell(False, sized["text"])
    found, why = short_side.verdicts(sym, sized["qty"], priced, setup, facts, venue)
    if why:
        return cell(None, why)
    return _from_check("short_margin", found)
