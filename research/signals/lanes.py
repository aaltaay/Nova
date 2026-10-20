"""The setup scanner's lanes over one stock-day of minute bars, read at the end of every minute.

The desk's own lane host for a replay (``eyes.replay.EyesReplay``) on the built-in templates -- the Trader's lanes,
long and short, and the built-in 5-minute first pullback and bull flag -- fed the day's minute bars and, inside each
minute, the bar's own prices: its open one second in, its high (long lanes) or low (short lanes) at 30 seconds and its
close at 59. The order inside a bar is not in the data, so a long trigger needs the bar's high to reach the line and a
short's its low. No book and no prints: the tape gate reads blind, which changes no detector's state (ADR 022).
"""
from __future__ import annotations

from typing import Any

from market_reads.signal_registry import FIVE_MINUTE_LANES, LONG_LANES, SHORT_LANES

LANE_TICKS = ((1.0, "open"), (30.0, "extreme"), (59.0, "close"))


def _no_pillars(symbol: str, day: str, ts: float, *, last_price: float | None, prev_close: float | None) -> dict:
    """The lanes' grade reads the pillars; the table keeps the pillars apart, so the lanes see none."""
    return {}


def templates() -> dict[str, Any]:
    from setup_templates.store import default_template
    return {s: default_template(s) for s in (*LONG_LANES, *SHORT_LANES)}


def template_revs() -> dict[str, str]:
    return {s: str(getattr(t, "rev", "")) for s, t in templates().items()}


def _replay(day: str, symbol: str, bars: list, prev_close: float, setups: tuple[str, ...], short: bool,
            five_minute: tuple[str, ...]):
    from eyes.recording import Recording
    from eyes.replay import EyesReplay
    from setup_scanner.five_minute_lane import five_minute_params
    from setup_scanner.lane import Lane

    ticks = []
    for b in bars:
        extreme = b.lo if short else b.h
        for offset, which in LANE_TICKS:
            px = b.o if which == "open" else (extreme if which == "extreme" else b.c)
            ticks.append((b.t + offset, px, px))
    rec = Recording(date=day, symbol=symbol, prints=[], print_ts=[], ticks=ticks, books=[], book_ts=[], bars=bars,
                    bars_source="archive", spans=[], prev_close=prev_close)
    all_templates = templates()
    rep = EyesReplay(rec, [all_templates[s] for s in setups], source="backtest", all_propose=True,
                     pillars=_no_pillars)
    columns = {lane: f"setup_{lane.setup}" for lane in rep.lanes}
    for setup in five_minute:
        lane = Lane(five_minute_params(setup), rep, playing=True)
        lane.ensure(symbol)
        rep.lanes.append(lane)
        columns[lane] = f"setup_{setup}_5m"
    return rep, columns


def run(day: str, symbol: str, bars: list, prev_close: float, minute_ends: list[float]) -> dict[str, list[str]]:
    """Each lane's detector state at each of ``minute_ends`` (epoch seconds, ascending): ``{column: [state]}``."""
    out: dict[str, list[str]] = {}
    for setups, short, five in ((LONG_LANES, False, FIVE_MINUTE_LANES), (SHORT_LANES, True, ())):
        rep, columns = _replay(day, symbol, bars, prev_close, setups, short, five)
        got: dict[str, list[str]] = {c: [] for c in columns.values()}
        for end in minute_ends:
            rep.advance(end)
            for lane, column in columns.items():
                got[column].append(lane.det[symbol].state)
        out.update(got)
    return out
