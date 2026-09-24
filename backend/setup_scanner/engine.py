"""The setup scanner engine (ADR 022, ADR 029, ADR 031).

Watches the HOD Momo active set -- the ~40 names Nova already streams on IBKR
Level 1 -- on the live one-minute bars ``ibkr/l1_minute`` builds for them, and
runs one *lane* per template of every setup with a scanner -- the first
pullback, the bull flag, the flat-top breakout and red to green
(``setup_scanner/lane.py``): the state machine, the tape gate where Nova holds
a Level 2 line, and a scoreboard row for every armed setup in ``setups.db``.
Each setup's template in play draws that setup's rows and raises its proposals
(when a setup is near its trigger and the tape says go) -- at Eyes or above
only: a setup at Off watches and scores in silence (ADR 031). The other
templates score in silence, so variations collect evidence on the same days.
Everything every lane sees goes to the eyes' journal (``eyes/journal.py``).

It never places, stages or cancels an order, never opens an IBKR line, and
never raises bot autonomy. On a Sim desk off the live edge it keeps watching
the live market but proposes nothing; the Sim eyes (``eyes/sim_eyes.py``) draw
the board from the loaded Session Record instead.

ADR 030: when a playing lane's setup triggers on the live feed, it tells its
trigger listeners -- Nova's bot (``bot/first_pullback``) registers one and
decides for itself whether to trade (the chosen setup's, ADR 031). A listener
only enqueues; nothing here imports an order path.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from datetime import datetime, time as dtime
from typing import Any, Callable, Iterable
from zoneinfo import ZoneInfo

from constants_bot import BOT_SCANNER_SETUPS, BOT_SETUP_FIRST_PULLBACK
from constants_setups import SETUPS_BOARD_PUSH_SEC
from setup_scanner.bars import Bar, MinuteBars, bar_from
from setup_scanner.board import build_board
from setup_scanner.hooks import (
    default_audit as _default_audit,
    default_bot_state as _default_bot_state,
    default_journal as _default_journal,
    default_levels as _default_levels,
    default_replay_desk as _default_replay_desk,
    default_seed as _default_seed,
    default_sim_eyes as _default_sim_eyes,
    default_templates as _default_templates,
    default_universe as _default_universe,
    live_catalysts as _live_catalysts,
    no_catalysts as _no_catalysts,
)
from setup_scanner.host import LaneHost
from setup_scanner.lane import Lane
from setup_scanner.lane_params import lane_params
from setup_scanner.store import SetupStore, StoreVersionError, session_date

logger = logging.getLogger(__name__)
ET = ZoneInfo("America/New_York")
TICK_SEC = 0.25


def session_start_ts(now: float) -> float:
    d = datetime.fromtimestamp(now, ET).date()
    return datetime.combine(d, dtime(4, 0), ET).timestamp()


class SetupEngine(LaneHost):
    source = "live"

    def __init__(self, *, store: SetupStore | None = None, tape: Any = None,
                 universe: Callable[[], Iterable[str]] = _default_universe,
                 seed: Callable[[str, float], list[Bar]] = _default_seed,
                 replay_desk: Callable[[], bool] = _default_replay_desk,
                 audit: Callable[..., None] = _default_audit,
                 clock: Callable[[], float] = time.time,
                 catalysts: Callable[[Iterable[str]], None] = _no_catalysts,
                 templates: Callable[[], Any] = _default_templates,
                 journal: Callable[[dict], None] = _default_journal,
                 bot_state: Callable[[], dict] = _default_bot_state,
                 sim_eyes: Callable[[], Any] = lambda: None,
                 levels: Callable[[], dict] = _default_levels,
                 setups: Iterable[str] = BOT_SCANNER_SETUPS):
        self.store = store
        self.store_error: str | None = None
        self.tape = tape
        self._universe_fn, self._seed_fn = universe, seed
        self._replay_fn, self._audit_fn, self._clock = replay_desk, audit, clock
        self._catalysts_fn = catalysts
        self._templates_fn, self._journal_fn, self._bot_state_fn = templates, journal, bot_state
        self._sim_eyes_fn = sim_eyes
        self._levels_fn = levels
        self.setups: tuple[str, ...] = tuple(setups)     # the setups whose lanes run (tests pin one)
        self.inbox: deque = deque()
        self.bars: dict[str, MinuteBars] = {}
        self.lanes: list[Lane] = []
        self._templates_version: int | None = None
        self.seeding: set[str] = set()
        self.clients: set = set()
        self.universe: set[str] = set()
        self.session: str | None = None
        self._last_push = 0.0
        self._trigger_listeners: list[Callable[[dict], None]] = []

    # -- the lanes in play, and the views the board / tests read ----------------
    @property
    def playing(self) -> Lane | None:
        """The first pullback's template in play (ADR 029's one board; tests read it)."""
        return self.playing_lane(BOT_SETUP_FIRST_PULLBACK)

    def playing_lane(self, setup: str) -> Lane | None:
        mine = [lane for lane in self.lanes if lane.setup == setup]
        return next((lane for lane in mine if lane.playing), mine[0] if mine else None)

    def playing_lanes(self) -> list[Lane]:
        """Each setup's template in play, in the playbook's order (ADR 031)."""
        return [lane for lane in (self.playing_lane(s) for s in self.setups) if lane is not None]

    def _view(self, name: str) -> dict:
        lane = self.playing
        return getattr(lane, name) if lane is not None else {}

    det = property(lambda self: self._view("det"))
    rows = property(lambda self: self._view("rows"))
    active_id = property(lambda self: self._view("active_id"))
    trackers = property(lambda self: self._view("trackers"))
    tape_view = property(lambda self: self._view("tape_view"))
    proposals = property(lambda self: self._view("proposals"))

    # -- feed (called on the IB loop: enqueue only) -------------------------
    def on_l1_minute(self, kind: str, symbol: str, payload: dict) -> None:
        if symbol in self.universe:
            self.inbox.append((kind, symbol, payload))

    # -- loop ----------------------------------------------------------------
    async def run(self) -> None:
        from ibkr import l1_minute

        if self.tape is None:
            from setup_scanner.tape_feed import TapeFeed

            self.tape = TapeFeed()
        if self.store is None:
            try:
                self.store = SetupStore()
            except (StoreVersionError, OSError) as exc:
                self.store_error = str(exc)
                logger.exception("setup scanner: scoreboard disabled -- %s", exc)
        l1_minute.add_listener(self.on_l1_minute)
        try:
            while True:
                try:
                    await self.tick()
                except Exception:
                    logger.exception("setup scanner: tick failed")
                await asyncio.sleep(TICK_SEC)
        finally:
            l1_minute.remove_listener(self.on_l1_minute)
            self.tape.close()

    async def tick(self, now: float | None = None) -> None:
        now = self._clock() if now is None else now
        self._rollover(now)
        self._sync_lanes(now)
        await self._sync_universe(now)
        self._drain(now)
        self._gate(now)
        sim = self._sim_eyes_fn()
        if sim is not None:
            sim.tick(now)
        if any(lane.alerts for lane in self.lanes) or now - self._last_push >= SETUPS_BOARD_PUSH_SEC:
            await self._push(now)

    def _rollover(self, now: float) -> None:
        sd = session_date(now)
        if sd == self.session:
            return
        self.session = sd
        self.bars.clear()
        self.seeding.clear()
        for lane in self.lanes:
            lane.clear()
        self.journal({"event": "session", "symbol": None})

    def _sync_lanes(self, now: float) -> None:
        """One lane per template of every setup with a scanner; rebuilt when the templates change."""
        store = self._templates_fn()
        version = store.version()
        if self.lanes and version == self._templates_version:
            return
        self._templates_version = version
        have = {(lane.setup, lane.p.template_id, lane.p.template_rev): lane for lane in self.lanes}
        lanes: list[Lane] = []
        kept: set[tuple[str, str]] = set()
        for setup in self.setups:
            playing_id = store.in_play(setup).id
            wanted = [t for t in store.templates(setup) if not t.error]
            mine: list[Lane] = []
            for t in wanted:
                kept.add((setup, t.id))
                lane = have.pop((setup, t.id, t.rev), None)
                if lane is None:
                    lane = Lane(lane_params(t), self)
                    for sym, mb in self.bars.items():   # warm up on today's bars; it sees from now on
                        if sym not in self.seeding and mb.completed:
                            lane.on_bars(sym, mb.completed, now)
                else:
                    lane.p = lane_params(t)            # same rules; the name may have changed
                if lane.playing and t.id != playing_id:
                    lane.withdraw_all("template")
                lane.playing = t.id == playing_id
                mine.append(lane)
            mine.sort(key=lambda lane: not lane.playing)
            lanes += mine
        for (setup, tid, _rev), gone in have.items():
            gone.withdraw_all("edited" if (setup, tid) in kept else "deleted")
        self.lanes = lanes
        self.journal({"event": "lanes", "symbol": None, "lanes": [
            {"setup_type": lane.setup, "template": lane.p.template_id, "rev": lane.p.template_rev,
             "name": lane.p.name, "params_hash": lane.p.params_hash, "playing": lane.playing} for lane in lanes]})

    async def _sync_universe(self, now: float) -> None:
        wanted = {s.strip().upper() for s in self._universe_fn() if s and s.strip()}
        busy: set[str] = set()
        for lane in self.lanes:
            busy |= lane.busy()
        self.universe = wanted | busy
        try:
            self._catalysts_fn(self.universe)   # queues stale / missing catalyst reads; never blocks
        except Exception:
            logger.warning("setup scanner: catalyst request failed", exc_info=True)
        gone = [sym for sym in self.bars if sym not in self.universe]
        for sym in gone:
            self.bars.pop(sym, None)
            for lane in self.lanes:
                lane.drop(sym)
        new = [s for s in sorted(wanted) if s not in self.bars]
        for sym in new:
            self.bars[sym] = MinuteBars(sym)
            for lane in self.lanes:
                lane.ensure(sym)
            self.seeding.add(sym)
        if new or gone:
            self.journal({"event": "watch", "symbol": None, "added": new, "removed": sorted(gone),
                          "count": len(self.bars)})
        if new:
            await asyncio.gather(*(self._seed(sym, now) for sym in new))

    async def _seed(self, sym: str, now: float) -> None:
        try:
            bars = await asyncio.to_thread(self._seed_fn, sym, session_start_ts(now))
        except Exception:
            logger.warning("setup scanner: could not seed %s from the bar store", sym, exc_info=True)
            bars = []
        mb = self.bars.get(sym)
        self.seeding.discard(sym)
        if mb is None:
            return
        mb.seed(bars)
        for lane in self.lanes:
            lane.on_bars(sym, mb.completed, now)

    def _drain(self, now: float) -> None:
        while self.inbox:
            kind, sym, p = self.inbox.popleft()
            mb = self.bars.get(sym)
            if mb is None:
                continue
            if kind == "bar":
                bar = bar_from(p)
                if bar is None or not mb.append(bar) or sym in self.seeding:
                    continue
                for lane in self.lanes:
                    lane.on_bars(sym, mb.completed, now, new_bar=bar)
            elif kind == "last":
                try:
                    price, ts = float(p["price"]), float(p["ts"])
                except (KeyError, TypeError, ValueError):
                    continue
                mb.open_bar_open = p.get("bar_open")
                if sym in self.seeding:
                    continue
                for lane in self.lanes:
                    lane.on_price(sym, price, ts, p.get("bar_open"))
        for lane in self.lanes:
            lane.sweep(now)

    # -- tape gate + proposals -------------------------------------------------
    def _gate(self, now: float) -> None:
        wanted: set[str] = set()
        windows = [lane.p.gate.window_sec for lane in self.lanes]
        history = [lane.p.flow.history_sec for lane in self.lanes]
        for lane in self.lanes:
            wanted |= lane.watching() | lane.trade_symbols(now)   # a trade on keeps its tape (ADR 034)
        if self.tape is not None:
            if windows and hasattr(self.tape, "keep_window"):
                self.tape.keep_window(max(windows), max(history))
            self.tape.sync(wanted, now)
        for lane in self.lanes:
            lane.gate(now)

    # -- output ------------------------------------------------------------------
    def board(self, now: float | None = None) -> dict[str, Any]:
        now = self._clock() if now is None else now
        sim = self._sim_eyes_fn()
        if sim is not None:
            sim_board = sim.board(now)
            if sim_board is not None:
                return sim_board
        return build_board(self, now)

    async def _push(self, now: float) -> None:
        from scanner_wire import dumps_wire

        self._last_push = now
        frames = []
        alerts: list[dict] = []
        for lane in self.lanes:
            alerts += lane.alerts
            lane.alerts = []
        sim = self._sim_eyes_fn()
        if sim is not None:
            alerts += sim.take_alerts()
        if alerts:
            frames.append(dumps_wire({"type": "alerts", "alerts": alerts}))
        frames.append(dumps_wire({"type": "board", **self.board(now)}))
        for ws in list(self.clients):
            try:
                for f in frames:
                    await ws.send_text(f)
            except Exception:
                logger.debug("setup scanner: dropping a socket client", exc_info=True)
                self.clients.discard(ws)


_engine: SetupEngine | None = None


def get_engine() -> SetupEngine:
    global _engine
    if _engine is None:
        _engine = SetupEngine(catalysts=_live_catalysts, sim_eyes=_default_sim_eyes)
    return _engine


async def run() -> None:
    """Background task entry (``app_runtime_tasks``)."""
    await get_engine().run()
