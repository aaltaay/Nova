"""The bot's read on one stock on a Sim replay (ADR 052): what the Trader's chart draws, at the playhead.

On the Sim desk off its live edge the read is the replay's, never the live market's, and nothing in it
comes from after the playhead:

- **now** is the playhead (``sim.session_clock``);
- **the setups** are the Sim eyes' lanes over the loaded replay (``setup_scanner.symbol_view``
  answers from them on a replay) -- forming, armed, near, triggered, as they stood at the playhead;
- **the price** is the replay's last print at the playhead (``sim.practice.reference``), the change
  against the replayed session's previous close;
- **the bars** are the Sim chart's own candles at the playhead (``sim.chart_replay``), completed ones
  only, so the day's levels -- the high of day, the premarket high, VWAP, tops and bottoms -- are
  the ones the chart shows by then;
- **the daily map** is built from the days before the replayed one (``history.summary(replay=True)``);
- **the bot** is its trade on this replay only (``bot.replay_desk``), as it stood at the playhead.

Everything only the live feed knows -- the Level 2 and tape sensors, the flow score, book pulls,
rvol, why it's moving, HOD Momo, borrow, halts, dilution, LULD, the boards -- is unknown on a replay,
with that reason, rather than today's answer for a past moment.

Reads only.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from constants_stock_read import STOCK_READ_BARS_5M_LIMIT, STOCK_READ_BARS_LIMIT

logger = logging.getLogger(__name__)
REPLAY_UNKNOWN = "a Sim replay: only the live feed knows this, and the replay holds no record of it"
_STEP = {"1Min": 60, "5Min": 300}


def playhead() -> float:
    from sim import session_clock

    return session_clock.now_et().timestamp()


def _ts(raw: Any) -> float:
    return datetime.fromisoformat(raw).timestamp() if isinstance(raw, str) else float(raw)


def _bars(sym: str, timeframe: str, limit: int, now: float) -> list[dict[str, Any]]:
    """The Sim chart's candles at the playhead, oldest first, completed ones only."""
    from sim.chart_replay import fetch_replay_bars

    step = _STEP[timeframe]
    out = []
    for b in fetch_replay_bars(sym, timeframe, limit).get("bars") or []:
        if b.get("partial"):
            continue
        t = _ts(b["t"])
        if t + step <= now + 1e-6:
            out.append({**b, "t": t})
    return out


def _price(sym: str) -> dict[str, Any]:
    """``{price, change_pct, volume}``: the replay at the playhead and its previous close (a fraction)."""
    from sim import practice

    ref = practice.reference(sym)
    prev = None
    try:
        from sim import capture_player, history_playback

        selected = history_playback.selected()
        if selected is not None and selected.spec["symbol"] == sym:
            prev = selected.prev_close
        else:
            state = capture_player.snapshot()
            prev = state.prev_close if state is not None and str(state.symbol).upper() == sym else None
    except Exception:
        logger.warning("stock read: the replay's previous close of %s could not be read", sym, exc_info=True)
    change = (float(ref.last) / float(prev) - 1.0) if ref.last is not None and prev else None
    return {"price": ref.last, "change_pct": change, "volume": None}


def _bot(sym: str) -> dict[str, Any]:
    """The bot's state, its trade only when it is this replay's (as the rewind left it)."""
    from stock_read.gather import _bot as live_bot
    from bot.replay_desk import waits

    out = live_bot(sym)
    trade = out.get("trade")
    if trade is not None and (trade.get("venue") != "sim" or waits(trade) is not None):
        out["trade"] = None
    return out


def gather(symbol: str, now: float) -> dict[str, Any]:
    """The facts ``read.build`` reads, from the replay at ``now`` (the playhead)."""
    from stock_read.gather import _setups, _try

    sym = (symbol or "").strip().upper()
    errors: dict[str, str] = {k: REPLAY_UNKNOWN for k in ("l2", "flow", "pulls", "rvol", "prints", "shortable",
                                                             "halted", "hod_momo", "board", "dilution", "luld")}
    price = _try(errors, "why", lambda: _price(sym)) or {}
    return {
        "symbol": sym,
        "now": now,
        "replay": True,
        "errors": errors,
        "why": {"facts": price, "checks": [], "likely": None, "derived": {}},
        "setups": _try(errors, "setups", lambda: _setups(sym, now)),
        "hod_momo": None,
        "bars": _try(errors, "bars", lambda: _bars(sym, "1Min", STOCK_READ_BARS_LIMIT, now)) or [],
        "bars5": _try(errors, "bars5", lambda: _bars(sym, "5Min", STOCK_READ_BARS_5M_LIMIT, now)) or [],
        "l2": None, "flow": None, "pulls": None, "rvol": None, "prints_per_min": None, "shortable": None,
        "halted": None, "board": None, "nova_exit": None, "dilution": None, "luld": None,
        "bot": _try(errors, "bot", lambda: _bot(sym)),
    }


def empty_day(symbol: str, date: str | None, now: float, *, kind: str) -> dict[str, Any]:
    """A day route on a replay desk (past setups, the decisions timeline) reads whole days -- after the playhead
    too -- so on a replay it answers nothing, and says why."""
    base = {"symbol": symbol, "date": date, "generated_at": now, "replay": True,
            "note": "a Sim replay: this reads the whole day, after the playhead too, so it is not shown on a replay"}
    if kind == "past":
        return {**base, "timeframe": "1m", "episodes": [], "counts": {}, "journal": {"ok": False, "error": base["note"],
                                                                                    "lines": 0},
                "bars": {"ok": False, "error": base["note"], "count": 0}}
    return {**base, "summary": {"text": base["note"]}, "events": [], "sources": {}}
