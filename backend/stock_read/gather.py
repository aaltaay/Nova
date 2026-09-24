"""Gather one symbol's facts from the owners that hold them (ADR 036). Reads caches, stores and the
sensor rings; never waits on the network, never opens an IBKR line, never writes.

Each owner is read on its own: one that fails leaves its fact ``None`` and its reason in
``errors`` -- the rules then say "unknown" with that reason, and every other fact still answers.
"""
from __future__ import annotations

import logging
from collections import Counter
from typing import Any, Callable

from constants_stock_read import STOCK_READ_BARS_5M_LIMIT, STOCK_READ_BARS_LIMIT, STOCK_READ_PRINTS_WINDOW_SEC

logger = logging.getLogger(__name__)


def _try(errors: dict[str, str], name: str, fn: Callable[[], Any]) -> Any:
    try:
        return fn()
    except Exception as exc:          # one owner's failure blanks its rows, never the read
        logger.warning("stock read: %s failed", name, exc_info=True)
        errors[name] = f"{type(exc).__name__}: {exc}"[:200]
        return None


def _why(sym: str, now: float) -> dict[str, Any]:
    from move_reason import facts as facts_mod
    from move_reason import rules

    facts = facts_mod.gather(sym, now)
    read = rules.read(facts, now)
    return {"facts": facts, "checks": read["checks"], "likely": read["likely"], "derived": read["derived"]}


def _setups(sym: str, now: float) -> dict[str, Any]:
    from setup_scanner.engine import get_engine
    from setup_scanner.symbol_view import symbol_view

    return symbol_view(get_engine(), sym, now)


def _hod(sym: str) -> dict[str, Any]:
    from hod_momo_high import high_debug
    from hod_momo_state import get_state

    state = get_state()
    alerts = [a for a in list(state.today_alerts) if (a.ticker or "").upper() == sym]
    alerts.sort(key=lambda a: float(a.created_ts or 0))
    firsts: dict[str, Any] = {}
    for a in alerts:
        firsts.setdefault(a.strategy_name, {"ts": float(a.created_ts or 0), "price": a.price, "name": a.strategy_name,
                                            "id": a.strategy_id})
    records = list(state.per_symbol_decisions.get(sym, []))
    last = records[-1] if records else None
    high = high_debug(sym)
    return {
        "count": len(alerts),
        "by_strategy": dict(Counter(a.strategy_name for a in alerts)),
        "firsts": sorted(firsts.values(), key=lambda f: f["ts"]),
        "last_ts": float(alerts[-1].created_ts or 0) if alerts else None,
        "decision": ({"ts": last.ts, "price": last.price, "gate_blocked": last.gate_blocked,
                      "strategies": list(last.strategies or []), "would_fire": last.would_fire} if last else None),
        "session_high": high.get("session_high"),
        "new_hod_age_sec": high.get("new_hod_age_sec"),
        "followed": sym in state.ticker_snaps,
    }


def _bars(sym: str, timeframe: str, limit: int, now: float) -> list[dict[str, Any]]:
    """Stored bars, oldest first, closed ones only (the forming bar's minute is not over)."""
    from sensors.feeds import get_bars

    step = {"1Min": 60, "5Min": 300}[timeframe]
    bars, _source = get_bars(sym, timeframe, limit)
    return [b for b in bars if float(b["t"]) + step <= now]


def _sensor(read: Callable[[str], dict[str, Any]], sym: str) -> dict[str, Any] | None:
    body = read(sym)
    data = body.get("data") or None
    return None if body.get("error") and not data else data


def _prints_per_minute(sym: str, now: float) -> int | None:
    from sensors import rings

    prints = rings.recent_prints(sym)
    if not prints:
        return None
    return sum(1 for p in prints if isinstance(p.get("ts"), (int, float))
               and now - float(p["ts"]) <= STOCK_READ_PRINTS_WINDOW_SEC)


def _bot(sym: str) -> dict[str, Any]:
    from bot.arming import is_desk_active
    from bot.breaker_limits import limits
    from bot.eligibility import eligible_symbols, holds_depth_line
    from bot.persist import load_session
    from bot.setup_levels import levels_of
    from sim.mode import venue

    row = load_session()
    both = levels_of(row)
    where = venue()
    trade = row.get("trade") if isinstance(row.get("trade"), dict) else None
    return {"level": int(row.get("level") or 0), "active": bool(is_desk_active(row)), "chosen": both["chosen"],
            "levels": both["levels"], "allowlisted": sym in eligible_symbols(row),
            "depth_line": holds_depth_line(sym), "venue": where, "breakers": limits(row, where),
            "trade": trade if trade and str(trade.get("symbol") or "").upper() == sym else None}


def _board(sym: str) -> str | None:
    from strategy.symbol_pillars import find_board_row, raw_boards

    _row, source = find_board_row(sym, raw_boards())
    return source


def gather(symbol: str, now: float) -> dict[str, Any]:
    from ibkr.halt_status import halted_now
    from ibkr.shortability import cached as shortability
    from sensors.adapters.bookish import read_flow, read_l2
    from sensors.adapters.pulls import read_book_pulls
    from sensors.adapters.volume import read_rvol

    sym = (symbol or "").strip().upper()
    errors: dict[str, str] = {}
    flow = _try(errors, "flow", lambda: _sensor(read_flow, sym))
    return {
        "symbol": sym,
        "now": now,
        "errors": errors,
        "why": _try(errors, "why", lambda: _why(sym, now)),
        "setups": _try(errors, "setups", lambda: _setups(sym, now)),
        "hod_momo": _try(errors, "hod_momo", lambda: _hod(sym)),
        "bars": _try(errors, "bars", lambda: _bars(sym, "1Min", STOCK_READ_BARS_LIMIT, now)) or [],
        "bars5": _try(errors, "bars5", lambda: _bars(sym, "5Min", STOCK_READ_BARS_5M_LIMIT, now)) or [],
        "l2": _try(errors, "l2", lambda: _sensor(read_l2, sym)),
        "flow": (flow or {}).get("score"),
        "pulls": _try(errors, "pulls", lambda: _sensor(read_book_pulls, sym)),
        "rvol": _try(errors, "rvol", lambda: _sensor(read_rvol, sym)),
        "prints_per_min": _try(errors, "prints", lambda: _prints_per_minute(sym, now)),
        "shortable": _try(errors, "shortable", lambda: shortability(sym)),
        "halted": _try(errors, "halted", lambda: halted_now([sym], now=now).get(sym)),
        "bot": _try(errors, "bot", lambda: _bot(sym)),
        "board": _try(errors, "board", lambda: _board(sym)),
    }
