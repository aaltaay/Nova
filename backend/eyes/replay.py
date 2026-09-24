"""The setup scanner's lanes over a Session Record (ADR 029).

``EyesReplay`` is a lane host (``setup_scanner/lane.py``) whose clock is the
recording's: it steps forward through the day's minute-bar closes and the
recording's price seconds (the high, then the last, of the prints that set a
price in each second), and reads the tape gate from the recorded books and
prints around each moment -- exactly the reads the live eyes make, from what
was recorded instead of what is streaming. Outside the recorded stretches
there is no price and no book: setups can arm on bars there, but nothing is
near, nothing triggers and the tape reads blind -- a gap is never filled.

It never goes backward: a rewind builds a new replay. Rows it would have saved
are kept in ``rows`` (a backtest writes them to its own run, never to
``setups.db``). Pure apart from the pillar lookup and the journal hook.

ADR 031: the templates may be of any setup with a scanner; ``playing`` names each
setup's template in play, and ``levels`` (the Sim eyes) keeps a setup at Off
silent, as the live engine does. A backtest proposes on every lane.
"""
from __future__ import annotations

from typing import Any, Callable

from constants_bot import BOT_LEVEL_EYES, BOT_SCANNER_SETUPS, BOT_SETUP_FIRST_PULLBACK
from constants_setups import TAPE_GATE_WINDOW_SEC
from eyes.recording import Recording, day_start_ts, pillars_at
from setup_scanner.lane import Lane
from setup_scanner.lane_params import lane_params

INF = float("inf")
SESSION_SEC = 16 * 3600


class EyesReplay:
    def __init__(self, rec: Recording, templates: list[Any], *, source: str, playing_id: str | None = None,
                 all_propose: bool = False, journal: Callable[[dict], None] | None = None,
                 pillars: Callable[..., dict] = pillars_at, playing: dict[str, str] | None = None,
                 levels: Callable[[], dict] | None = None):
        self.rec = rec
        self.source = source
        self.session = rec.date
        self._journal_fn = journal or (lambda event: None)
        self._pillars_fn = pillars
        self._all_propose = all_propose
        self._levels_fn = levels
        in_play = dict(playing or {})

        def plays(t: Any) -> bool:
            if all_propose:
                return True
            setup = getattr(t, "setup", None) or BOT_SETUP_FIRST_PULLBACK
            return t.id == in_play[setup] if setup in in_play else t.id == playing_id

        self.lanes = [Lane(lane_params(t), self, playing=plays(t)) for t in templates]
        order = {s: i for i, s in enumerate(BOT_SCANNER_SETUPS)}
        self.lanes.sort(key=lambda lane: (order.get(lane.setup, 99), not lane.playing))
        self.rows: dict[str, dict] = {}
        self.now = day_start_ts(rec.date)
        self.end = self.now + SESSION_SEC
        self.last_price: float | None = None
        self._bi = 0
        self._ti = 0
        self._keep = 3 * max([lane.p.gate.window_sec for lane in self.lanes] + [TAPE_GATE_WINDOW_SEC])
        for lane in self.lanes:
            lane.ensure(rec.symbol)

    # -- the host every lane calls ----------------------------------------------
    @property
    def playing(self) -> Lane | None:
        """The first pullback's template in play (the ADR 029 board), else the first lane in play."""
        return self.playing_lane(BOT_SETUP_FIRST_PULLBACK) or next(
            (lane for lane in self.lanes if lane.playing), self.lanes[0] if self.lanes else None)

    def playing_lane(self, setup: str) -> Lane | None:
        mine = [lane for lane in self.lanes if lane.setup == setup]
        return next((lane for lane in mine if lane.playing), mine[0] if mine else None)

    def playing_lanes(self) -> list[Lane]:
        return [lane for lane in (self.playing_lane(s) for s in BOT_SCANNER_SETUPS) if lane is not None]

    def levels(self) -> dict:
        if self._levels_fn is None:
            return {"chosen": None, "levels": {}}
        try:
            out = self._levels_fn()
        except Exception:
            return {"chosen": None, "levels": {}}
        return out if isinstance(out, dict) else {"chosen": None, "levels": {}}

    def pillars(self, sym: str, now: float) -> dict:
        return self._pillars_fn(sym, self.session, now, last_price=self.last_price, prev_close=self.rec.prev_close)

    def tape_books(self, sym: str) -> list:
        return self.rec.books_between(self.now - self._keep, self.now)

    def tape_prints(self, sym: str) -> list:
        return self.rec.prints_between(self.now - self._keep, self.now)

    def tape_line(self, sym: str) -> dict:
        recorded = self.rec.recorded_at(self.now)
        return {"depth": recorded and bool(self.rec.books), "tape": recorded, "recorded": True}

    def save(self, row: dict) -> None:
        self.rows[row["id"]] = dict(row)

    def journal(self, event: dict) -> None:
        self._journal_fn({"ts": self.now, "date": self.session, "source": self.source,
                          "replay": {"date": self.rec.date, "symbol": self.rec.symbol}, "bot": None, **event})

    def audit(self, **kw: Any) -> None:
        """A replay never writes the bot's audit stream: its proposals are practice, journalled only."""

    def clock(self) -> float:
        return self.now

    def can_propose(self, setup_type: str | None = None) -> bool:
        """A backtest proposes on every lane; the Sim eyes keep a setup at Off silent (ADR 031)."""
        if self._levels_fn is None or setup_type is None:
            return True
        return int((self.levels().get("levels") or {}).get(setup_type) or 0) >= BOT_LEVEL_EYES

    # -- stepping ---------------------------------------------------------------
    def _bar_open_at(self, ts: float) -> float | None:
        """The open of the minute ``ts`` falls in, when the archive holds that minute."""
        bars = self.rec.bars
        if self._bi < len(bars) and bars[self._bi].t <= ts < bars[self._bi].t + 60:
            return bars[self._bi].o
        return None

    def advance(self, until: float) -> None:
        """Run every lane forward to ``until`` (never backward)."""
        until = min(until, self.end)
        bars, ticks, sym = self.rec.bars, self.rec.ticks, self.rec.symbol
        while True:
            bar_end = bars[self._bi].t + 60 if self._bi < len(bars) else INF
            tick_at = ticks[self._ti][0] if self._ti < len(ticks) else INF
            step = min(bar_end, tick_at)
            if step == INF or step > until:
                break
            self.now = step
            if bar_end <= tick_at:
                bar = bars[self._bi]
                self._bi += 1
                completed = bars[:self._bi]
                for lane in self.lanes:
                    lane.on_bars(sym, completed, step, new_bar=bar)
            else:
                _, high, last = ticks[self._ti]
                self._ti += 1
                bar_open = self._bar_open_at(step - 1e-6)
                for lane in self.lanes:
                    lane.on_price(sym, high, step, bar_open)
                    if last != high:
                        lane.on_price(sym, last, step, bar_open)
                self.last_price = last
            for lane in self.lanes:
                lane.sweep(step)
                if lane.watching():
                    lane.gate(step)
        self.now = max(self.now, until)

    def run_to_end(self) -> None:
        self.advance(self.end)

    def take_alerts(self) -> list[dict]:
        out: list[dict] = []
        for lane in self.lanes:
            out += lane.alerts
            lane.alerts = []
        return out
