"""Every gate between the bot and a fire, in one list (ADR 027, ADR 042 C).

``gates(row)`` is what the Bots page draws -- every one, with its reason in plain words
(``detail.text``); the fire path checks the same facts (``bot.activation``,
``bot.first_pullback.admit``, ``bot.entry_rules``, ``execution.service``). Each gate is
``{id, ok, stage, detail}``: ``stage`` is ``activate`` for a gate Activate needs, or
``fire`` for one each order meets on its own.

ADR 042 removed the read-out gate: on Live the ``venue`` gate refuses (Nova's bot does not
trade Live), and on Paper and Sim the read-out was waived. Read-outs stay on each setup's
card as evidence. Owner: this module (no state).
"""
from __future__ import annotations

import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)


def current_venue() -> str | None:
    """The desk venue (``live`` | ``paper`` | ``sim``); None when it cannot be read."""
    try:
        from sim.mode import venue

        return venue()
    except Exception:
        logger.warning("bot gates: the desk venue is unreadable -- it counts as Live", exc_info=True)
        return None


def _venue_words(venue: str | None, edge: bool) -> str:
    """Where the bot may trade now, in words: Paper, Sim at its live edge, or the Sim replay loaded (ADR 052)."""
    if venue == "sim" and not edge:
        from bot.replay_desk import desk, label

        here = desk()
        return (f"Sim replay of {label(here['key'])}: the bot trades its go triggers on the Sim account as the "
                "playhead plays across them" if here else "Sim replay")
    return "Paper, or Sim at its live edge: the bot may trade here"


def _safe(fn: Callable[[], Any], default: Any, what: str) -> Any:
    try:
        return fn()
    except Exception:
        logger.warning("bot gates: %s could not be read -- the gate reads closed", what, exc_info=True)
        return default


def _gate(gid: str, ok: bool, stage: str, text: str, **detail: Any) -> dict[str, Any]:
    return {"id": gid, "ok": bool(ok), "stage": stage, "detail": {**detail, "text": text}}


def day_lock(row: dict[str, Any], venue: str | None) -> dict[str, Any]:
    """``{active, until, tripped_at, pnl, venue}`` -- this venue's all-stop lock.

    Read through ``bot.buy_lock.lock_for`` when it is there; else from the venue's dial."""
    try:
        from bot import buy_lock

        lock_for = getattr(buy_lock, "lock_for", None)
        if lock_for is not None:
            got = lock_for(row, venue)
            if isinstance(got, dict):
                return {"active": bool(got.get("active")), "until": got.get("until"),
                        "tripped_at": got.get("tripped_at", got.get("at")), "pnl": got.get("pnl"), "venue": venue}
    except Exception:
        logger.warning("bot gates: bot.buy_lock.lock_for failed -- reading the dial", exc_info=True)
    from bot.clock import lock_is_active
    from bot.venue_levels import dial_of

    dial = dial_of(row, venue) if venue is not None else row
    until = dial.get("hard_lock_until_date")
    return {"active": bool(lock_is_active(until)), "until": until, "tripped_at": dial.get("hard_lock_at"),
            "pnl": dial.get("hard_lock_pnl"), "venue": venue}


def lock_text(lock: dict[str, Any]) -> str:
    from bot.activation import hhmm, money

    if not lock.get("active"):
        return "no all-stop lock on this venue"
    when = f" at {hhmm(lock['tripped_at'])} ET" if lock.get("tripped_at") else ""
    said = f" (P&L {money(lock['pnl'])})" if isinstance(lock.get("pnl"), (int, float)) else ""
    return f"the all-stop fired{when}{said}: buys on {lock.get('venue')} are locked until {lock.get('until')}"


def gates(row: dict[str, Any], venue_now: tuple[str | None, bool, bool] | None = None) -> list[dict[str, Any]]:
    from bot import activation, entry_rules
    from bot.clock import soft_latched
    from bot.day_pnl import commission_hold
    from bot.eligibility import holds_depth_line, normalize_symbols
    from bot.setup_levels import at_strategy, master
    from bot.sleeve import of as sleeve_of
    from constants import IBKR_MAX_DEPTH_SYMBOLS
    from constants_bot import BOT_LEVEL_STRATEGY
    import kill_switch

    venue, edge, readable = venue_now or activation.venue_state()
    blocked = activation.venue_block(venue, edge, readable)
    level = master(row)
    strategy = at_strategy(row)
    symbols = normalize_symbols(row.get("symbol_allowlist"))
    held = [s for s in symbols if _safe(lambda s=s: holds_depth_line(s), False, f"{s}'s depth line")]
    missing = [s for s in symbols if s not in held]
    auto = _safe(_auto_entry_stocks, [], "the Auto-entry stocks")
    padlock_ok, padlock_why = activation.padlock()
    tripped = soft_latched(row)
    lock = day_lock(row, venue)
    killed = _safe(kill_switch.is_tripped, True, "the kill switch")
    now = entry_rules.venue_now()
    wins = entry_rules.windows(strategy, now)
    caps = sleeve_of(row)
    daily = _safe(lambda: entry_rules.today(venue, now, cap=int(caps["entries_per_day"])), None, "the daily count")
    late = _safe(lambda: entry_rules.extended_hours_block(caps), "the venue's clock is unreadable",
                 "regular hours")
    hold = commission_hold(venue)     # #564: Live only; never raises
    return [
        _gate("venue", blocked is None, "activate", blocked[1] if blocked is not None else _venue_words(venue, edge),
              venue=venue, live_edge=edge),
        _gate("level", level >= BOT_LEVEL_STRATEGY, "activate",
              "the master level is at Strategy" if level >= BOT_LEVEL_STRATEGY
              else "the master level is below Strategy: no setup can trade", level=level),
        _gate("setups", bool(strategy), "activate",
              (f"at Strategy: {', '.join(s.replace('_', ' ') for s in strategy)}" if strategy
               else "no setup is at Strategy: set one setup's level to Strategy"), at_strategy=strategy),
        _gate("padlock", padlock_ok, "activate",
              "the desk padlock is unlocked" if padlock_ok else f"the desk padlock is locked: {padlock_why}",
              reason=padlock_why),
        _gate("allowlist", bool(symbols) or bool(auto), "fire",
              _stocks_text(len(symbols), len(auto)), count=len(symbols), auto_entry=len(auto)),
        _gate("depth_lines", bool(held), "fire",
              (f"Level 2 held on {', '.join(held)}" if held
               else "no Bot stock holds a Level 2 line: open its Level 2 or record it"),
              held=held, missing=missing, max_lines=IBKR_MAX_DEPTH_SYMBOLS),
        _gate("bot_trip", not tripped, "activate",
              activation.trip_text(row) if tripped else "the bot trip has not fired on this venue today",
              fired_at=row.get("soft_breaker_at") if tripped else None,
              pnl=row.get("soft_breaker_pnl") if tripped else None,
              until=row.get("soft_breaker_until") if tripped else None),
        _gate("day_lock", not lock["active"], "fire", lock_text(lock), until=lock["until"],
              tripped_at=lock["tripped_at"], pnl=lock["pnl"], venue=venue),
        _gate("kill_switch", not killed, "fire",
              "the kill switch is tripped: nothing is sent until you reset it" if killed
              else "the kill switch is reset"),
        _gate("window", any(w.get("open") for w in wins), "fire",
              ("; ".join(("open: " if w.get("open") else "closed: ") + entry_rules.window_text(w) for w in wins)
               or "no setup is at Strategy, so no window applies"),
              setups=[{k: w.get(k) for k in ("setup", "start", "end", "open", "clipped", "error")} for w in wins],
              venue_time=now.strftime("%H:%M")),
        _gate("daily_cap", daily is not None and daily["count"] < daily["cap"], "fire",
              (entry_rules.cap_text(daily["count"], daily["cap"]) if daily is not None
               else "the day's entries could not be counted: Nova sends no automatic entry"),
              count=(daily or {}).get("count"), cap=int(caps["entries_per_day"]),
              venue_day=(daily or {}).get("venue_day")),
        _gate("extended_hours", late is None, "fire",
              late or ("extended hours allowed by the sleeve" if caps.get("extended_hours")
                       else "inside 09:30-16:00 ET"), allowed=bool(caps.get("extended_hours"))),
        _gate("commissions", hold is None, "fire",
              "the session's commissions read" if hold is None
              else f"the session's commissions are unreadable ({hold.get('error')}): no new bot entry",
              **(hold or {})),
    ]


def _auto_entry_stocks() -> list[str]:
    """The stocks set to Auto-entry (Nova buys, you sell) on the desk venue: Nova buys them only
    while the bot is Active, by the bot's rules (ADR 042 F)."""
    from constants_stock_mode import STOCK_MODE_AUTO_ENTRY
    from stock_mode import model, store

    return sorted(sym for sym, sw in store.switches().items()
                  if model.mode_of(sw.get("buy"), sw.get("sell")) == STOCK_MODE_AUTO_ENTRY)


def _stocks_text(bot: int, auto: int) -> str:
    """Which stocks Nova may buy on this venue, in words."""
    if not bot and not auto:
        return "no stock is set to Bot or Auto-entry on this venue: set one under Who trades"
    parts = []
    if bot:
        parts.append(f"{bot} stock{'' if bot == 1 else 's'} set to Bot")
    if auto:
        parts.append(f"{auto} to Auto-entry")
    return " and ".join(parts) + " on this venue"


def first_closed(gate_list: list[dict[str, Any]]) -> dict[str, Any] | None:
    return next((g for g in gate_list if not g["ok"]), None)
