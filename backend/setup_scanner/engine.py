"""The setup scanner engine (ADR 022).

Watches the HOD Momo active set -- the ~40 names Nova already streams on IBKR
Level 1 -- on the live one-minute bars ``ibkr/l1_minute`` builds for them, runs
the first-pullback state machine per symbol, reads the tape gate where Nova
holds a Level 2 line, raises a proposal when a setup is near its trigger and
the tape says go, and scores every armed setup in ``setups.db``.

It never places, stages or cancels an order, never opens an IBKR line, and
never raises bot autonomy. On a Sim desk off the live edge it keeps watching
the live market but proposes nothing (the desk is showing a replay).
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections import deque
from datetime import datetime, time as dtime
from typing import Any, Callable, Iterable
from zoneinfo import ZoneInfo

from constants_setups import (
    SETUP_STATE_ARMED,
    SETUP_STATE_NEAR,
    SETUP_STATE_TRIGGERED,
    SETUPS_BOARD_PUSH_SEC,
    SETUPS_EMA_PERIOD,
    SETUPS_SCORE_WINDOW_MIN,
    TAPE_VERDICT_BLIND,
    TAPE_VERDICT_GO,
)
from setup_scanner import grade as _grade
from setup_scanner.bars import Bar, MinuteBars, bar_from, minute_start
from setup_scanner.board import build_board
from setup_scanner.pullback import PullbackDetector, ema
from setup_scanner.scoring import ScoreTracker
from setup_scanner.store import SetupStore, StoreVersionError, session_date
from setup_scanner.tape_gate import evaluate as evaluate_tape

logger = logging.getLogger(__name__)
ET = ZoneInfo("America/New_York")
TICK_SEC = 0.25
WATCH_STATES = (SETUP_STATE_ARMED, SETUP_STATE_NEAR)


def session_start_ts(now: float) -> float:
    d = datetime.fromtimestamp(now, ET).date()
    return datetime.combine(d, dtime(4, 0), ET).timestamp()


def _default_universe() -> Iterable[str]:
    from hod_momo_active import get_active_symbols

    return get_active_symbols()


def _default_seed(symbol: str, from_ts: float) -> list[Bar]:
    import bars_store

    res = bars_store.read(symbol, "1Min", 960, from_ts=from_ts)
    return [b for b in (bar_from(r) for r in (res or {}).get("bars") or []) if b is not None]


def _default_replay_desk() -> bool:
    try:
        from sim.mode import is_replay_desk

        return bool(is_replay_desk())
    except Exception:
        logger.debug("setup scanner: venue check failed", exc_info=True)
        return False


def _default_audit(**kw: Any) -> None:
    try:
        from bot.audit import record

        record(**kw)
    except Exception:
        logger.warning("setup scanner: bot audit write failed", exc_info=True)


def _no_catalysts(symbols: Iterable[str]) -> None:
    """Tests and replays: no catalyst fetch (the live one is wired in ``get_engine``)."""


def _live_catalysts(symbols: Iterable[str]) -> None:
    from catalysts import live as catalyst_live

    catalyst_live.request(symbols)


class SetupEngine:
    def __init__(self, *, store: SetupStore | None = None, tape: Any = None,
                 universe: Callable[[], Iterable[str]] = _default_universe,
                 seed: Callable[[str, float], list[Bar]] = _default_seed,
                 replay_desk: Callable[[], bool] = _default_replay_desk,
                 audit: Callable[..., None] = _default_audit,
                 clock: Callable[[], float] = time.time,
                 catalysts: Callable[[Iterable[str]], None] = _no_catalysts):
        self.store = store
        self.store_error: str | None = None
        self.tape = tape
        self._universe_fn, self._seed_fn = universe, seed
        self._replay_fn, self._audit_fn, self._clock = replay_desk, audit, clock
        self._catalysts_fn = catalysts
        self.inbox: deque = deque()
        self.bars: dict[str, MinuteBars] = {}
        self.det: dict[str, PullbackDetector] = {}
        self.rows: dict[str, dict] = {}
        self.active_id: dict[str, str] = {}
        self.trackers: dict[str, ScoreTracker] = {}
        self.tape_view: dict[str, dict] = {}
        self.proposals: dict[str, dict] = {}
        self.alerts: list[dict] = []
        self.seeding: set[str] = set()
        self.clients: set = set()
        self.universe: set[str] = set()
        self.session: str | None = None
        self._last_push = 0.0

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
        await self._sync_universe(now)
        self._drain(now)
        self._gate(now)
        if self.alerts or now - self._last_push >= SETUPS_BOARD_PUSH_SEC:
            await self._push(now)

    def _rollover(self, now: float) -> None:
        sd = session_date(now)
        if sd == self.session:
            return
        self.session = sd
        for store in (self.bars, self.det, self.rows, self.active_id, self.trackers,
                      self.tape_view, self.proposals):
            store.clear()

    async def _sync_universe(self, now: float) -> None:
        wanted = {s.strip().upper() for s in self._universe_fn() if s and s.strip()}
        busy = {s for s, d in self.det.items() if d.state in WATCH_STATES} | {
            self.rows[sid]["symbol"] for sid in self.trackers}
        self.universe = wanted | busy
        try:
            self._catalysts_fn(self.universe)   # queues stale / missing catalyst reads; never blocks
        except Exception:
            logger.warning("setup scanner: catalyst request failed", exc_info=True)
        for sym in list(self.det):
            if sym not in self.universe:
                self.det.pop(sym, None)
                self.bars.pop(sym, None)
        new = [s for s in wanted if s not in self.det]
        for sym in new:
            self.bars[sym] = MinuteBars(sym)
            self.det[sym] = PullbackDetector(sym)
            self.seeding.add(sym)
        if new:
            await asyncio.gather(*(self._seed(sym, now) for sym in new))

    async def _seed(self, sym: str, now: float) -> None:
        try:
            bars = await asyncio.to_thread(self._seed_fn, sym, session_start_ts(now))
        except Exception:
            logger.warning("setup scanner: could not seed %s from the bar store", sym, exc_info=True)
            bars = []
        mb, det = self.bars.get(sym), self.det.get(sym)
        self.seeding.discard(sym)
        if mb is None or det is None:
            return
        mb.seed(bars)
        self._handle(sym, det.on_bars(mb.completed), now)

    def _drain(self, now: float) -> None:
        while self.inbox:
            kind, sym, p = self.inbox.popleft()
            det, mb = self.det.get(sym), self.bars.get(sym)
            if det is None or mb is None:
                continue
            if kind == "bar":
                bar = bar_from(p)
                if bar is None or not mb.append(bar) or sym in self.seeding:
                    continue
                self._handle(sym, det.on_bars(mb.completed), now)
                e9 = ema([b.c for b in mb.completed], SETUPS_EMA_PERIOD)[-1]
                for sid in self._open_tracker_ids(sym):
                    if self.trackers[sid].on_bar(bar, e9):
                        self._score(sid, now)
            elif kind == "last":
                try:
                    price, ts = float(p["price"]), float(p["ts"])
                except (KeyError, TypeError, ValueError):
                    continue
                mb.open_bar_open = p.get("bar_open")
                if sym in self.seeding:
                    continue
                self._handle(sym, det.on_price(price, ts, bar_open=p.get("bar_open")), ts)
                for sid in self._open_tracker_ids(sym):
                    if self.trackers[sid].on_price(price, ts):
                        self._score(sid, now)
        for sid in list(self.trackers):
            tr = self.trackers[sid]
            if tr.exit_px is not None and now > tr.triggered_at + SETUPS_SCORE_WINDOW_MIN * 60 and tr.outcome != "open":
                self._score(sid, now)
                self.trackers.pop(sid, None)

    def _open_tracker_ids(self, sym: str) -> list[str]:
        return [sid for sid in self.trackers if self.rows.get(sid, {}).get("symbol") == sym]

    # -- events -> scoreboard rows ------------------------------------------
    def _handle(self, sym: str, events: list[tuple[str, dict]], now: float) -> None:
        for kind, view in events:
            sid = f"{sym}-{self.session}-{view['setup_key']}"
            setup = view.get("setup") or {}
            row = self.rows.get(sid)
            if kind == "armed":
                if row is None:
                    pillars = _grade.read_pillars(sym, now)
                    g, checks = _grade.grade(pillars)
                    row = {"id": sid, "session_date": self.session, "symbol": sym, "leg_t": view["setup_key"],
                           "armed_at": setup.get("armed_at") or now, "grade": g,
                           "pillars": {**pillars, "checks": checks}}
                    self.rows[sid] = row
                elif row.get("disarmed_at"):
                    row["disarmed_at"] = None          # the same leg armed again
                self._copy_setup(row, view)
                self.active_id[sym] = sid
            elif row is None:
                continue
            elif kind == "rearmed":
                self._copy_setup(row, view)
                self._close_proposal(sid, "rearmed")   # its levels are stale; a new read proposes again
            elif kind == "near":
                row["state"] = view["state"]
                if not row.get("near_at"):
                    row["near_at"] = now
                    row["near_tape"] = self._slim(self._evaluate(sym, now))
            elif kind == "triggered":
                ts = float(setup.get("triggered_at") or now)
                row.update({"state": SETUP_STATE_TRIGGERED, "reason": view["reason"], "triggered_at": ts,
                            "entry": setup.get("entry"), "nth": setup.get("nth"),
                            "trigger_tape": self._evaluate(sym, ts), "outcome": "open"})
                self.trackers[sid] = ScoreTracker(
                    entry=float(setup["entry"]), stop=float(setup["stop"]), target1=float(setup["target1"]),
                    risk=float(setup["risk"]), triggered_at=ts, entry_bar_t=minute_start(ts))
                self._close_proposal(sid, "triggered")
            elif kind in ("failed", "disarmed") and not row.get("triggered_at"):
                row.update({"state": view["state"], "reason": view["reason"]})
                row["failed_at" if kind == "failed" else "disarmed_at"] = now
                if kind == "failed":
                    row["fail_reason"] = view["reason"]
                self._close_proposal(sid, kind)
            self._save(row)

    def _copy_setup(self, row: dict, view: dict) -> None:
        s = view.get("setup") or {}
        row.update({"state": view["state"], "reason": view["reason"], "kind": s.get("kind"),
                    "trigger": s.get("trigger"), "entry_planned": s.get("entry"), "stop": s.get("stop"),
                    "risk": s.get("risk"), "target1": s.get("target1"), "leg_high": s.get("leg_high"),
                    "leg_low": s.get("leg_low"), "leg_pct": s.get("leg_pct"),
                    "pullback_bars": s.get("pullback_bars")})

    def _score(self, sid: str, now: float) -> None:
        tr, row = self.trackers.get(sid), self.rows.get(sid)
        if tr is None or row is None:
            return
        row.update(tr.as_dict())
        self._save(row)

    def _save(self, row: dict) -> None:
        if self.store is None:
            return
        try:
            self.store.upsert(row)
        except Exception:
            logger.exception("setup scanner: could not save %s", row.get("id"))

    # -- tape gate + proposals -------------------------------------------------
    def _evaluate(self, sym: str, now: float) -> dict:
        det = self.det.get(sym)
        setup = (det.armed or det.triggered) if det else None
        if not setup or self.tape is None:
            return {"verdict": TAPE_VERDICT_BLIND, "reasons": ["no setup"], "metrics": {}}
        res = evaluate_tape(trigger=float(setup["trigger"]), now=now,
                            books=self.tape.books(sym), prints=self.tape.prints(sym))
        res["line"] = {"depth": self.tape.has_depth(sym), "tape": self.tape.has_tape(sym)}
        return res

    @staticmethod
    def _slim(res: dict) -> dict:
        return {"verdict": res.get("verdict"), "reasons": res.get("reasons"), "line": res.get("line")}

    def _gate(self, now: float) -> None:
        wanted = {s for s, d in self.det.items() if d.state in WATCH_STATES}
        if self.tape is not None:
            self.tape.sync(wanted, now)
        for sym in list(self.tape_view):
            if sym not in wanted:
                self.tape_view.pop(sym, None)
        replay = self._replay_fn()
        for sym in wanted:
            res = self._evaluate(sym, now)
            self.tape_view[sym] = res
            sid = self.active_id.get(sym)
            prop = self.proposals.get(sid) if sid else None
            if prop is not None and prop["status"] == "open":
                prop["tape_now"] = res["verdict"]
            elif (sid and self.det[sym].state == SETUP_STATE_NEAR and res["verdict"] == TAPE_VERDICT_GO
                  and not replay):
                # No open proposal: none yet, or the last one was withdrawn when the
                # setup re-armed at new levels or was disarmed and armed again.
                self._propose(sym, sid, res, now)

    def _propose(self, sym: str, sid: str, res: dict, now: float) -> None:
        row = self.rows.get(sid) or {}
        prop = {"id": str(uuid.uuid4()), "setup_id": sid, "symbol": sym, "kind": row.get("kind"),
                "trigger": row.get("trigger"), "entry": row.get("entry_planned"), "stop": row.get("stop"),
                "target1": row.get("target1"), "risk": row.get("risk"), "grade": row.get("grade"),
                "reasons": res.get("reasons"), "created_at": now, "status": "open", "tape_now": res["verdict"]}
        self.proposals[sid] = prop
        self.alerts.append(prop)
        row["proposal_id"] = prop["id"]
        self._save(row)
        self._audit_fn(action="setup_proposal", outcome="proposed",
                       reason=(f"{str(prop['kind'] or 'setup').replace('_', ' ')} on {sym}: trigger "
                               f"{prop['trigger']}, stop {prop['stop']} -- tape go"),
                       inputs=prop)

    def _close_proposal(self, sid: str, status: str) -> None:
        prop = self.proposals.get(sid)
        if prop is not None and prop["status"] == "open":
            prop["status"] = status
            prop["closed_at"] = self._clock()

    # -- output ------------------------------------------------------------------
    def board(self, now: float | None = None) -> dict[str, Any]:
        now = self._clock() if now is None else now
        return build_board(self, now)

    async def _push(self, now: float) -> None:
        from scanner_wire import dumps_wire

        self._last_push = now
        frames = []
        if self.alerts:
            frames.append(dumps_wire({"type": "alerts", "alerts": self.alerts}))
            self.alerts = []
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
        _engine = SetupEngine(catalysts=_live_catalysts)
    return _engine


async def run() -> None:
    """Background task entry (``app_runtime_tasks``)."""
    await get_engine().run()
