"""The 5-minute setups (operator ask 2026-09-30: "we need 5-minute strategies ... sometimes I see slow stocks
moving upwards, and you can see clear patterns in the 5-minute chart, but they're not clear in the 1-minute
chart"; on the mockup: build it, chart only, 07:00-15:30).

One built-in lane per setup in ``SETUPS_5M_SETUPS`` -- the first pullback, the bull flag and the flat top --
runs the setup's own detector on 5-minute candles made of the scanner's minutes (``five_minute.candles``:
on the clock from 04:00 ET, complete once their five minutes are over). Its rules are the default template's
but for these, the 2026-09-29 study's 5-minute rules and the operator's window: a candle of
``SETUPS_5M_BAR_SEC``, arming until ``SETUPS_5M_ENTRY_CUTOFF_ET``, a risk up to ``SETUPS_5M_STOP_CAP_PCT`` of
the entry, and a first touch read over ``SETUPS_5M_SCORE_WINDOW_MIN``. Its scoring exit counts 5-minute
candles. Template id ``SETUPS_5M_TEMPLATE_ID``: its scoreboard rows are its own (``~5m``), never the
template in play's, so no read-out, trial or bot reads them.

It never plays: it raises no proposal, tells the bot nothing, and draws no Setups board row and no Bots
page card. The stock read hands it to the 5-minute chart (``setups_5m``), and the 1-minute chart shows an
armed or near one as a chip and its trigger.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
from types import SimpleNamespace
from typing import Any, Sequence

from constants_setups import (
    SETUPS_5M_BAR_SEC,
    SETUPS_5M_ENTRY_CUTOFF_ET,
    SETUPS_5M_SCORE_WINDOW_MIN,
    SETUPS_5M_STOP_CAP_PCT,
    SETUPS_5M_TEMPLATE_ID,
    SETUPS_5M_TEMPLATE_NAME,
    SETUPS_BAR_SEC,
)
from constants_bot import BOT_SETUP_BULL_FLAG, BOT_SETUP_FIRST_PULLBACK, BOT_SETUP_FLAT_TOP
from setup_scanner.bars import Bar
from setup_scanner.five_minute import candles

SETUPS_5M_SETUPS: tuple[str, ...] = (BOT_SETUP_FIRST_PULLBACK, BOT_SETUP_BULL_FLAG, BOT_SETUP_FLAT_TOP)
FIVE_MIN_REV = 1


def is_five_minute(lane: Any) -> bool:
    return int(getattr(lane.p, "bar_sec", SETUPS_BAR_SEC)) != SETUPS_BAR_SEC


def five_minute_params(setup: str) -> Any:
    """The built-in 5-minute lane's ``LaneParams`` for ``setup``."""
    from setup_scanner.lane_params import lane_params
    from setup_templates.catalogue import defaults

    values = {**defaults(setup), "entry_cutoff": SETUPS_5M_ENTRY_CUTOFF_ET}
    rules = {**values, "bar_sec": SETUPS_5M_BAR_SEC, "stop_cap_pct": SETUPS_5M_STOP_CAP_PCT,
             "score_window_min": SETUPS_5M_SCORE_WINDOW_MIN}
    stamp = hashlib.sha256(json.dumps(rules, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:12]
    base = lane_params(SimpleNamespace(id=SETUPS_5M_TEMPLATE_ID, rev=FIVE_MIN_REV, fingerprint=stamp,
                                       name=SETUPS_5M_TEMPLATE_NAME, setup=setup, values=values))
    pattern = dataclasses.replace(base.pattern, bar_sec=SETUPS_5M_BAR_SEC, stop_cap_pct=SETUPS_5M_STOP_CAP_PCT)
    return dataclasses.replace(base, pattern=pattern, bar_sec=SETUPS_5M_BAR_SEC,
                               score_window_min=SETUPS_5M_SCORE_WINDOW_MIN)


class Candles(dict):
    """One 5-minute lane's candles per symbol: ``{symbol: (complete candles fed, (forming start, open))}``.
    A dict, so the lane clears it with its other per-symbol stores."""

    def feed(self, sym: str, bars: Sequence[Bar], now: float) -> tuple[list[Bar] | None, Bar | None]:
        """``(candles, newest)`` when a 5-minute candle completed since the last feed -- the detector reads
        only then -- else ``(None, None)``; either way it notes the forming candle's open."""
        done = [Bar(c["t"], c["o"], c["h"], c["l"], c["c"], c["v"]) for c in candles(bars, now)]
        fed, _ = self.get(sym, (0, None))
        forming = None
        if bars:
            start = float(int(bars[-1].t // SETUPS_5M_BAR_SEC) * SETUPS_5M_BAR_SEC)
            first = next((b for b in bars if b.t >= start), None)
            if first is not None and (not done or done[-1].t < start):
                forming = (start, first.o)
        self[sym] = (len(done), forming)
        if len(done) == fed:
            return None, None
        return done, (done[-1] if done else None)

    def bar_open(self, sym: str, ts: float, minute_open: float | None) -> float | None:
        """The open of the 5-minute candle ``ts`` falls in: its first minute's, else -- no minute of it has
        closed yet -- the forming minute's own."""
        _, forming = self.get(sym, (0, None))
        start = float(int(ts // SETUPS_5M_BAR_SEC) * SETUPS_5M_BAR_SEC)
        if forming is not None and forming[0] == start:
            return forming[1]
        return minute_open
