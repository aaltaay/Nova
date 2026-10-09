"""The Sim eyes (ADR 029, ADR 052): what the Setups board, every setup card, the Trader's chart
and Nova's bot read on the Sim desk off the live edge.

With a replay loaded -- a Session Record, or a historical window (a Massive window or an IBKR
download, ``eyes.history_recording``) -- the setup scanner's lanes follow the playhead over it:
the loaded symbol, re-read with today's templates (``eyes.sim_target``). Its proposals are
practice proposals on that desk (pushed on ``/ws/setups``, journalled, never on the bot's audit
stream), and a playing lane's go trigger goes to the trigger listeners -- Nova's bot -- when the
playhead plays across it: one no older than ``BOT_FP_TRIGGER_MAX_AGE_SEC`` at the playhead, on a
forward step. A rebuild (a rewind, a template change, another replay) and a jump forward hand the
bot nothing they passed. With nothing loaded off the edge, the board shows what Nova's live eyes
recorded at the playhead (``eyes/playback.py``, operator ask 2026-09-24). At the live edge the live
board stays.

Nothing after the playhead is shown: while a rewind waits for its rebuild (at most every
``EYES_SIM_REBUILD_MIN_SEC``), the board, the cards and the chart's read say they are catching up
instead of showing the lanes as they stood later.

Every read and step of the replay runs on one worker thread, never on the scanner's loop: the
loop only posts the playhead (``tick``) and reads what the worker last published (``board``,
``symbol_view``, built by ``eyes.sim_board``). The journal gets each moment once: a rebuild replays silently up to the furthest
point already journalled. A journal playback reads the day's file as it grows and folds it forward;
a rewind folds it again (at most every ``EYES_PLAYBACK_REBUILD_MIN_SEC``) and never raises what it
passed.

Owner: this module (in memory only; invalidation: the loaded replay's key, the templates' version,
and the played-back day). Nothing here places an order.
"""
from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Any, Callable

from constants_bot import BOT_FP_TRIGGER_MAX_AGE_SEC, BOT_SCANNER_SETUPS
from constants_eyes import (
    EYES_PLAYBACK_ALERT_STEP_SEC,
    EYES_PLAYBACK_REBUILD_MIN_SEC,
    EYES_REPLAY_SOURCE_SIM,
    EYES_SIM_RELOAD_MIN_SEC,
    EYES_SIM_REBUILD_MIN_SEC,
    EYES_SIM_SYMBOL_VIEW_SEC,
)
from eyes import sim_board
from eyes.sim_target import KIND_CAPTURE, KIND_HISTORY, KIND_JOURNAL, LANE_KINDS, default_target

logger = logging.getLogger(__name__)

_WORKER_WAIT_SEC = 0.5
_BEHIND_SEC = sim_board.BEHIND_SEC
# Kept for callers that named the kinds here before ``eyes.sim_target``.
__all__ = ["KIND_CAPTURE", "KIND_HISTORY", "KIND_JOURNAL", "SimEyes", "get_sim_eyes"]


def _journal_path(date: str) -> Path | None:
    from eyes.journal import day_path

    return day_path(date)


class SimEyes:
    def __init__(self, *, target: Callable[[], dict | None] = default_target,
                 load: Callable[[str, str], Any] | None = None,
                 templates: Callable[[], Any] | None = None,
                 journal: Callable[[dict], None] | None = None,
                 threaded: bool = True,
                 levels: Callable[[], dict] | None = None,
                 journal_path: Callable[[str], Path | None] = _journal_path,
                 sizing: Any = None):
        self._target_fn = target
        self._journal_path_fn = journal_path
        self._load_fn = load
        self._templates_fn = templates
        self._journal_fn = journal
        self._levels_fn = levels
        self._sizing = sizing
        self._threaded = threaded
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None
        self._listeners: list[Callable[[dict], None]] = []
        self.target: dict | None = None
        self._symbol_asked = 0.0               # monotonic: when a reader last asked for the symbol view
        # Worker-owned state: only the worker thread touches these.
        self._key: tuple | None = None
        self._loaded_at = 0.0
        self._recording: Any = None
        self._replay: Any = None
        self._replay_key: list | None = None
        self._templates_version: int | None = None
        self._journaled_through = 0.0
        self._last_rebuild = 0.0
        self._playback: Any = None             # eyes.playback.Playback of the played-back day
        # Published for the loop (under the lock).
        self._view: dict[str, Any] = {"loading": False, "error": None, "rows": [], "proposals": [], "setups": [],
                                      "proposing": False, "template": None, "lanes": 0, "recording": None,
                                      "now": None, "universe": 0, "note": None, "gap": None, "journal": None,
                                      "symbol": None}
        self._alerts: list[dict] = []

    # -- wiring defaults (late imports keep this module light) -------------------------
    def _load(self, target: dict) -> Any:
        if self._load_fn is not None:
            return self._load_fn(str(target["date"]), str(target["symbol"]).upper())
        if target["kind"] == KIND_HISTORY:
            from eyes.history_recording import load_loaded

            return load_loaded()
        from eyes.recording import load

        return load(str(target["date"]), str(target["symbol"]).upper())

    def _store(self) -> Any:
        if self._templates_fn is not None:
            return self._templates_fn()
        from setup_templates.store import get_store

        return get_store()

    def _levels(self) -> dict:
        """Each setup's level (ADR 031): the Sim eyes keep a setup at Off silent, as the live board does."""
        if self._levels_fn is not None:
            return self._levels_fn()
        from setup_scanner.hooks import default_levels

        return default_levels()

    def _sizer(self) -> Any:
        """The desk's sleeve, read as the live host reads it (``LaneHost.risk_usd``): the liquidity's size."""
        if self._sizing is None:
            from setup_scanner.host import LaneHost

            self._sizing = LaneHost()
        return self._sizing

    def _journal(self, event: dict) -> None:
        ts = float(event.get("ts") or 0)
        if ts <= self._journaled_through:
            return                      # already journalled before a rewind
        self._journaled_through = ts
        fn = self._journal_fn
        if fn is None:
            from eyes import journal

            fn = journal.record
        fn(event)

    # -- triggers to whoever trades them (ADR 052) ---------------------------------------
    def add_trigger_listener(self, fn: Callable[[dict], None]) -> None:
        with self._lock:
            if fn not in self._listeners:
                self._listeners.append(fn)

    def remove_trigger_listener(self, fn: Callable[[dict], None]) -> None:
        with self._lock:
            if fn in self._listeners:
                self._listeners.remove(fn)

    def _announce(self, triggers: list[dict], playhead: float) -> None:
        """Hand the bot the triggers the playhead played across: none older than the bot would take."""
        with self._lock:
            listeners = list(self._listeners)
        for event in triggers:
            at = float((event.get("setup") or {}).get("triggered_at") or event.get("ts") or 0)
            if playhead - at > BOT_FP_TRIGGER_MAX_AGE_SEC:
                continue                        # passed over, never played across: a jump trades nothing
            event = {**event, "replay_key": self._replay_key}
            for fn in listeners:
                try:
                    fn(event)
                except Exception:
                    logger.exception("sim eyes: a trigger listener failed on %s", event.get("setup_id"))

    # -- the loop side -------------------------------------------------------------------
    def tick(self, now: float) -> None:
        """Called on the scanner's loop: post the Sim desk's playhead; never reads a file."""
        try:
            target = self._target_fn()
        except Exception:
            logger.warning("sim eyes: the Sim desk's replay could not be read", exc_info=True)
            target = None
        with self._lock:
            self.target = target
        if not self._threaded:
            self._work()
            return
        if target is not None or self._key is not None:
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._run, name="sim-eyes", daemon=True)
                self._thread.start()
            self._wake.set()

    def _run(self) -> None:
        while True:
            self._wake.wait(_WORKER_WAIT_SEC)
            self._wake.clear()
            try:
                self._work()
            except Exception:
                logger.exception("sim eyes: a step failed")

    # -- the worker side -------------------------------------------------------------------
    def _work(self) -> None:
        with self._lock:
            target = self.target
        if target is None or target["kind"] not in LANE_KINDS:
            if self._key is not None:
                self._drop()
            if target is None:
                self._playback = None
            else:
                self._work_journal(target)
            return
        self._playback = None
        key = tuple(target.get("key") or (target["kind"], target["date"], str(target["symbol"]).upper()))
        if key != self._key and not self._reload_waits(key):
            grown = self._key is not None and key[:6] == self._key[:6]
            journaled = self._journaled_through
            self._drop()
            if grown:
                self._journaled_through = journaled     # the same window, more of it: journalled moments stay so
            self._key, self._loaded_at = key, time.monotonic()
            self._replay_key = target.get("replay_key")
            self._publish(loading=True)
            try:
                self._recording = self._load(target)
                self._publish(loading=False, error=None)
            except (ValueError, OSError) as exc:
                self._publish(loading=False, error=str(exc))
                return
        if self._recording is None:
            return
        store = self._store()
        playhead = float(target["playhead"])
        stale = self._replay is None or store.version() != self._templates_version
        behind = self._replay is not None and playhead < self._replay.now - _BEHIND_SEC
        if stale or (behind and time.monotonic() - self._last_rebuild >= EYES_SIM_REBUILD_MIN_SEC):
            self._rebuild(store, playhead)
        elif not behind:
            self._replay.advance(playhead)
            self._announce(self._replay.take_triggers(), playhead)
            alerts = self._replay.take_alerts()
            if alerts:
                with self._lock:
                    self._alerts += alerts
        self._publish()

    def _reload_waits(self, key: tuple) -> bool:
        """A download still fetching changes its key as it grows: the same window reloads at most every
        ``EYES_SIM_RELOAD_MIN_SEC``. Another window, or another kind, reloads at once."""
        if self._key is None or self._recording is None or key[:6] != self._key[:6]:
            return False
        return time.monotonic() - self._loaded_at < EYES_SIM_RELOAD_MIN_SEC

    def _rebuild(self, store: Any, playhead: float) -> None:
        from eyes.replay import EyesReplay

        templates = [t for setup in BOT_SCANNER_SETUPS for t in store.templates(setup) if not t.error]
        playing = {setup: store.in_play(setup).id for setup in BOT_SCANNER_SETUPS}
        replay = EyesReplay(self._recording, templates, source=EYES_REPLAY_SOURCE_SIM, playing=playing,
                            journal=self._journal, levels=self._levels, sizing=self._sizer())
        replay.advance(playhead)
        replay.take_alerts()            # a rebuild never re-raises what it passed on the way
        replay.take_triggers()          # ... and never hands the bot a trigger it passed
        self._replay = replay
        self._templates_version = store.version()
        self._last_rebuild = time.monotonic()

    def _work_journal(self, target: dict) -> None:
        """Fold the live eyes' journal of the playhead's day forward to the playhead."""
        from eyes.journal_day import JournalDay
        from eyes.playback import Playback, gap_note, template_window

        date, at = str(target["date"]), float(target["playhead"])
        pb = self._playback
        if pb is None or pb.day.date != date:
            where = self._journal_path_fn(date)
            pb = self._playback = Playback(JournalDay(Path(where) if where is not None else None, date))
        try:
            pb.day.refresh()
        except OSError as exc:
            self._publish(loading=False, error=f"the eyes' journal could not be read: {exc}")
            return
        prev = pb.at
        backward = prev is not None and at < prev
        if backward:
            if time.monotonic() - self._last_rebuild < EYES_PLAYBACK_REBUILD_MIN_SEC:
                return                          # the last view stands; the next wake folds again
            self._last_rebuild = time.monotonic()
        raised = pb.advance(at)
        if raised and prev is not None and not backward and at - prev <= EYES_PLAYBACK_ALERT_STEP_SEC:
            with self._lock:
                self._alerts += raised          # played across, never jumped to
        body = pb.body(self._levels(), template_window(self._store()))
        gap = pb.gap()
        with self._lock:
            self._view.update(body, template=None, lanes=0, recording=None, now=at, loading=False, error=None,
                              gap=gap, note=gap_note(gap, date), journal=pb.journal_view(), symbol=None)

    def _drop(self) -> None:
        self._key = self._recording = self._replay = self._replay_key = None
        self._templates_version = None
        self._journaled_through = 0.0
        self._publish(loading=False, error=None)

    def _symbol_view(self, replay: Any) -> dict[str, Any] | None:
        """The loaded symbol across every setup's template in play, as the live engine answers it for the
        Trader's read (``setup_scanner.symbol_view``) -- built only while a reader asks for it."""
        if replay is None or time.monotonic() - self._symbol_asked > EYES_SIM_SYMBOL_VIEW_SEC:
            return None
        from setup_scanner.symbol_view import lane_entry

        sym, levels = replay.rec.symbol, replay.levels()
        return {"symbol": sym, "at": replay.now, "session_date": replay.session,
                "setups": [lane_entry(lane, sym, levels, replay.now) for lane in replay.playing_lanes()]}

    def _publish(self, **overrides: Any) -> None:
        from setup_scanner.board import board_body, template_view

        replay = self._replay
        lane = replay.playing if replay is not None else None
        body = (board_body(replay.playing_lanes(), replay.lanes, replay.levels(), replay.now, can_propose=True)
                if replay is not None else {"rows": [], "proposals": [], "setups": [], "proposing": False})
        view = {
            **body,
            "template": template_view(lane),
            "lanes": len(replay.lanes) if replay is not None else 0,
            "recording": self._recording.summary() if self._recording is not None else None,
            "now": replay.now if replay is not None else None,
            "symbol": self._symbol_view(replay),
        }
        with self._lock:
            self._view.update(view)
            self._view.update(overrides)

    # -- output (the loop side) -------------------------------------------------------------
    def take_alerts(self) -> list[dict]:
        with self._lock:
            out, self._alerts = self._alerts, []
        return out

    def flow_reading(self, setup_id: str) -> dict | None:
        """The replay's newest flow reading on a triggered setup (Nova's bot's flush exit on a Sim replay)."""
        replay = self._replay
        return replay.flow_reading(setup_id) if replay is not None else None

    def symbol_view(self, symbol: str) -> dict[str, Any] | None:
        """The loaded symbol's lanes as the worker last published them (``eyes.sim_board.symbol_view``); asking
        keeps the worker building them."""
        self._symbol_asked = time.monotonic()
        self._wake.set()
        with self._lock:
            target, view = self.target, dict(self._view)
        return sim_board.symbol_view(target, view, symbol)

    def board(self, now: float) -> dict[str, Any] | None:
        """The Setups board while the Sim desk shows a replay (``eyes.sim_board.board``); ``None`` keeps the live one."""
        with self._lock:
            target, view = self.target, dict(self._view)
        return sim_board.board(target, view, now)

    def status(self) -> dict[str, Any]:
        with self._lock:
            hidden = ("rows", "proposals", "setups", "proposing", "symbol")
            return {"target": self.target, **{k: v for k, v in self._view.items() if k not in hidden}}


_sim_eyes: SimEyes | None = None


def get_sim_eyes() -> SimEyes:
    global _sim_eyes
    if _sim_eyes is None:
        _sim_eyes = SimEyes()
    return _sim_eyes


def reset_for_tests() -> None:
    global _sim_eyes
    _sim_eyes = None
