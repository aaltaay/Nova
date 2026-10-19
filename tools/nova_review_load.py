"""Assemble one review page from the data front door.

Owner: this module. It does not persist a file. The answer's ``schema_version``
is the wire shape. Readers are injectable so a test never touches the operator's
files. The default readers are ``market_reads`` (ADR 059).
"""
from __future__ import annotations

from typing import Any, Callable

import nova_review_causal as causal

BarsReader = Callable[[str, str, str], list[dict[str, Any]]]
DailyReader = Callable[[str, str, str], list[dict[str, Any]]]


def _records(frame) -> list[dict[str, Any]]:
    if frame is None or len(frame) == 0:
        return []
    return frame.to_dict(orient="records")


def front_door_bars(symbol: str, day: str, tf: str) -> list[dict[str, Any]]:
    from market_reads import reads
    return _records(reads.bars(symbol, day, tf))


def front_door_daily(symbol: str, date_from: str, date_to: str) -> list[dict[str, Any]]:
    from market_reads import daily
    return _records(daily.daily_bars(symbol, date_from, date_to))


def load_review(symbol: str, day: str, tfs: list[str] | str | None, as_of: str | None = None, *,
                bars_reader: BarsReader = front_door_bars, daily_reader: DailyReader = front_door_daily) -> dict[str, Any]:
    """Bars, levels and setups the page may paint at ``as_of``. Nothing after that time."""
    name = causal.check_symbol(symbol)
    session = causal.parse_day(day).isoformat()
    frames = causal.check_tfs(tfs)
    clock = causal.check_clock(as_of or causal.DEFAULT_AS_OF)
    moment = causal.as_of_dt(session, clock)
    minutes = causal.closed_bars(list(bars_reader(name, session, "1m")), "1m", moment)
    dailies = list(daily_reader(name, causal.lookback_start(session), session))
    timeframes: dict[str, Any] = {"1m": {"bars": [causal.wire_bar(row, "1m") for row in minutes]}}
    fives: list[dict[str, Any]] = []
    if "5m" in frames:
        fives = causal.closed_bars(list(bars_reader(name, session, "5m")), "5m", moment)
        timeframes["5m"] = {"bars": [causal.wire_bar(row, "5m") for row in fives]}
    if "10s" in frames:
        tens = causal.closed_bars(list(bars_reader(name, session, "10s")), "10s", moment)
        timeframes["10s"] = {"bars": [causal.wire_bar(row, "10s") for row in tens]}
    if "1d" in frames:
        timeframes["1d"] = {"bars": causal.daily_series(dailies, minutes, session)}
    return {
        "ok": True,
        "schema_version": 1,
        "symbol": name,
        "date": session,
        "as_of": clock,
        "as_of_iso": moment.isoformat(),
        "source": "front-door",
        "lookahead": False,
        "vwap_anchor": "04:00",
        "timeframes": timeframes,
        "levels": causal.levels(minutes, dailies, session, moment),
        "setups": causal.causal_setups(fives),
        "vwap": causal.session_vwap(minutes),
    }
