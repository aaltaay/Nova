"""The Trader's signals as the signal table stores them: one entry per column, with the values it can hold, the
desk rule that writes it and how far back it reaches (architecture/schema/agent-desk.md, "The Trader's signals on
past days"). The builder writes exactly these columns, ``signal_test`` refuses anything else, and
``signal_catalog`` lists them.

A ``kind`` is ``state`` (the panel's row state), ``label`` (a word from ``values``), ``number`` or ``bool``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

STATES = ("ok", "warn", "bad", "info", "unknown")
LONG_LANES = ("first_pullback", "bull_flag", "flat_top_breakout", "flat_top_5m", "red_to_green", "gap_and_go",
              "pullback_dip", "abcd")
FIVE_MINUTE_LANES = ("first_pullback", "bull_flag")
SHORT_LANES = ("backside_lower_high", "bear_flag", "failed_breakout", "lost_vwap", "ssr_bounce")
LANE_STATES = ("watching", "leg", "pullback", "armed", "near", "triggered", "failed")
TAPE_LABELS = ("burst", "flush", "neutral", "quiet", "blind", "not_built")
FULL = "2016 on (every in-play stock-day)"


@dataclass(frozen=True)
class Signal:
    column: str
    group: str
    kind: str
    label: str
    source: str
    history: str = FULL
    values: tuple[str, ...] = ()
    unit: str | None = None

    def to_dict(self) -> dict[str, Any]:
        out = {"signal": self.column, "group": self.group, "kind": self.kind, "label": self.label,
               "source": self.source, "history": self.history}
        if self.values:
            out["values"] = list(self.values)
        if self.unit:
            out["unit"] = self.unit
        return out


def _state(column: str, group: str, label: str, source: str, history: str = FULL) -> Signal:
    return Signal(column, group, "state", label, source, history, STATES)


def _lane(name: str, column: str, label: str, short: bool = False) -> Signal:
    prices = "its open, then its low" if short else "its open, then its high"
    return Signal(column, "setups", "label", label,
                  f"setup scanner lane {name} on the built-in template (EyesReplay over minute bars: {prices})",
                  values=LANE_STATES)


BOARD_HISTORY = "the leaderboard store's boards: 1,752 of 2,713 sessions, 2016-11-30 on, with holes"
CATALYST_HISTORY = ("items only for tickers the catalyst backfill targeted (Massive's news thin before 2021-04, "
                    "Finnhub 2025 on); not_checked where no source looked")
HALT_HISTORY = "Nasdaq's halt log 2021-09-21 on; unknown before"
HOD_HISTORY = ("rebuilt HOD Momo days only (hod_momo_rebuild; a rebuilt day reads Yahoo's float of today -- "
               "look-ahead), null elsewhere")
TAPE_HISTORY = "the tape stage's days only (Massive trades sided on the NBBO); not_built elsewhere"

SIGNALS: tuple[Signal, ...] = (
    Signal("in_play", "in_play", "label", "In play (the tile)", "stock_read.read._verdict('in_play')",
           values=("Yes", "Partly", "No", "Too thin", "Not known")),
    _state("pillars", "in_play", "Five Pillars", "stock_read.rows._pillars (strategy.five_pillars)"),
    Signal("pillars_n", "in_play", "number", "Five Pillars passed", "strategy.five_pillars", unit="0-5"),
    *(Signal(f"pillar_{p}", "in_play", "bool", f"Pillar: {p}", "strategy.five_pillars")
      for p in ("price", "change", "rvol", "catalyst", "float")),
    _state("rvol_state", "in_play", "Relative volume (the row)", "stock_read.rows._rvol"),
    Signal("rvol_pace", "in_play", "number", "Relative volume, the day's pace",
           "market.pace_relative_volume(volume since 04:00, day_avg_volume, the minute)", unit="x"),
    Signal("rvol", "in_play", "number", "Relative volume, cumulative by minute", "the relative-volume table",
           unit="x"),
    Signal("rvol_5m", "in_play", "number", "Relative volume, the last 5 minutes", "the relative-volume table",
           unit="x"),
    Signal("rvol_daily", "in_play", "number", "Relative volume, the daily rate", "the relative-volume table",
           unit="x"),
    Signal("change_pct", "in_play", "number", "Change vs the prior close", "the relative-volume table",
           unit="percent points"),
    Signal("price", "in_play", "number", "Last price", "the minute bars", unit="dollars"),
    Signal("catalyst", "in_play", "label", "Catalyst verdict", "catalysts.classify.verdict at the minute",
           CATALYST_HISTORY, ("catalyst", "negative", "routine_only", "noise_only", "none_found", "not_checked")),
    _state("catalyst_state", "in_play", "Catalyst (the row)", "stock_read.rows._catalyst", CATALYST_HISTORY),
    Signal("why", "in_play", "label", "Why it's moving (likely kind)", "move_reason.rules.read",
           values=("news", "short_squeeze", "split_squeeze", "low_float_momentum", "news_pending", "routine_news",
                   "thin_trading", "unexplained", "not_moving", "not_read")),
    _state("why_state", "in_play", "Why it's moving (the row)", "stock_read.rows._likely"),
    Signal("board", "in_play", "label", "On the boards", "strategy.symbol_pillars.find_board_row at the minute",
           BOARD_HISTORY, ("gappers", "gainers", "losers", "afterhours", "large_cap", "market")),
    _state("board_state", "in_play", "On the boards (the row)", "stock_read.rows._board", BOARD_HISTORY),
    _state("ran_before", "in_play", "Has it run before", "stock_read.history.runs + rows._ran_before"),
    Signal("runs_n", "in_play", "number", "+40% runs in the prior 260 sessions", "stock_read.history.runs",
           unit="sessions"),
    Signal("liquidity", "in_play", "label", "Liquidity", "stock_read.plan_liquidity.read (no book walk)",
           values=("ok", "thin", "unknown")),
    Signal("liquidity_day_usd", "in_play", "number", "Dollars traded since 04:00", "stock_read.plan_liquidity",
           unit="dollars"),
    Signal("liquidity_5m_usd", "in_play", "number", "Dollars traded in the last 5 minutes",
           "stock_read.plan_liquidity", unit="dollars"),
    _state("hod_today", "in_play", "HOD Momo today", "stock_read.rows._hod_today over a rebuilt day's alerts",
           HOD_HISTORY),
    Signal("hod_alerts", "in_play", "number", "HOD Momo alerts so far", "hod_momo_rebuild alerts", HOD_HISTORY,
           unit="alerts"),
    Signal("front", "front", "label", "Front side (the tile)", "stock_read.read._verdict('front')",
           values=("Front side", "Mixed", "Back side", "Not known")),
    *(_state(f"front_{k}", "front", f"Front side: {k.replace('_', ' ')}", f"stock_read.rows.front_rows ({k})")
      for k in ("macd_1m", "vwap", "ema", "volume_profile", "hod")),
    *(_lane(n, f"setup_{n}", f"Setup: {n.replace('_', ' ')}") for n in LONG_LANES),
    *(_lane(f"{n} (5-minute)", f"setup_{n}_5m", f"Setup: {n.replace('_', ' ')} (5-minute)")
      for n in FIVE_MINUTE_LANES),
    *(_lane(n, f"setup_{n}", f"Short setup: {n.replace('_', ' ')}", short=True) for n in SHORT_LANES),
    _state("float", "float", "Float (the row)", "stock_read.rows.float_rows (SEC shares outstanding)",
           "SEC shares outstanding filed by the day (XBRL era); an upper bound on the float"),
    Signal("float_shares", "float", "number", "Shares outstanding (the float's stand-in)",
           "day_movers.floats.sec_shares", unit="shares"),
    _state("rotation", "float", "Rotation (volume over the float)", "stock_read.rows.float_rows"),
    Signal("halted", "halts", "bool", "Halted now", "leaderboard.halts.halted_at", HALT_HISTORY),
    _state("halts_today", "halts", "Halts today (the row)", "stock_read.rows.halts_rows", HALT_HISTORY),
    Signal("halts_n", "halts", "number", "Halt starts today", "move_reason.facts.count_halts", HALT_HISTORY,
           unit="halts"),
    Signal("halts", "halts", "label", "Halts (the tile)", "stock_read.read tiles", HALT_HISTORY,
           ("Halted", "No halts", "Not known")),
    Signal("tape", "tape", "label", "Tape flow at the minute's end", "setup_scanner.tape_flow (10 s)",
           TAPE_HISTORY, TAPE_LABELS),
    Signal("tape_score", "tape", "number", "Tape flow score", "setup_scanner.tape_flow", TAPE_HISTORY,
           unit="-1..1"),
    Signal("tape_flush", "tape", "bool", "A flush inside the minute", "setup_scanner.tape_flow", TAPE_HISTORY),
    Signal("tape_burst", "tape", "bool", "A burst inside the minute", "setup_scanner.tape_flow", TAPE_HISTORY),
)
BY_COLUMN = {s.column: s for s in SIGNALS}
TAPE_COLUMNS = tuple(s.column for s in SIGNALS if s.group == "tape")
MINUTE_COLUMNS = tuple(s.column for s in SIGNALS if s.group != "tape")
NOT_REBUILT = {
    "short": "IBKR's borrow (tick 236) is live only: no history exists",
    "hod_now": "HOD Momo's gate decisions are not kept by a rebuilt day",
    "liquidity book walk": "Level 2 depth is not in Massive's archive",
}


def catalog() -> list[dict[str, Any]]:
    return [s.to_dict() for s in SIGNALS]


def check(when: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """``when`` validated against the registry (a list of ``{signal, is}`` or ``{signal, min?, max?}``)."""
    if not isinstance(when, list) or not when:
        raise ValueError("when is a non-empty list of conditions: {signal, is} or {signal, min?, max?}")
    out = []
    for c in when:
        if not isinstance(c, dict) or "signal" not in c:
            raise ValueError(f"a condition names its signal: {c!r}")
        s = BY_COLUMN.get(str(c["signal"]))
        if s is None:
            raise ValueError(f"unknown signal {c['signal']!r}; signal_catalog lists them")
        extra = set(c) - {"signal", "is", "min", "max"}
        if extra:
            raise ValueError(f"{s.column}: unknown keys {sorted(extra)}")
        if s.kind == "number":
            if "is" in c or ("min" not in c and "max" not in c):
                raise ValueError(f"{s.column} is a number: give min and/or max")
            lo = None if c.get("min") is None else float(c["min"])
            hi = None if c.get("max") is None else float(c["max"])
            out.append({"signal": s.column, "min": lo, "max": hi})
            continue
        if "min" in c or "max" in c or "is" not in c:
            raise ValueError(f"{s.column} is a {s.kind}: give is")
        want = c["is"] if isinstance(c["is"], list) else [c["is"]]
        if s.kind == "bool":
            if any(not isinstance(v, bool) for v in want):
                raise ValueError(f"{s.column} is true or false")
        elif any(v not in s.values for v in want):
            raise ValueError(f"{s.column} is one of {', '.join(s.values)}")
        out.append({"signal": s.column, "is": list(want)})
    return out
