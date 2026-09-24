"""The Sim eyes (ADR 029): what the Setups board and every setup card show on the
Sim desk off the live edge.

With a Session Record loaded, the setup scanner's lanes follow the playhead over
it -- the recorded symbol, re-read with today's templates -- and its proposals are
practice proposals on that desk (pushed on ``/ws/setups``, journalled, never on
the bot's audit stream). Anything else off the edge -- nothing loaded, a past
day, a historical download (no Level 2) -- shows what Nova's live eyes recorded
at the playhead (``eyes/playback.py``, operator ask 2026-09-24): every symbol
they watched, every setup's rows and funnel, and each recorded proposal popping
up as the playhead plays across it. At the live edge the live board stays.

Every read and step of the recording runs on one worker thread, never on the
scanner's loop: the loop only posts the playhead (``tick``) and reads the last
published board (``board``). A forward playhead advances the replay; a rewind
or a template change rebuilds it (at most every ``EYES_SIM_REBUILD_MIN_SEC``
for rewinds). The journal gets each moment once: a rebuild replays silently up
to the furthest point already journalled. A journal playback reads the day's
file as it grows and folds it forward; a rewind folds it again (at most every
``EYES_PLAYBACK_REBUILD_MIN_SEC``) and never raises what it passed.

Owner: this module (in memory only; invalidation: the loaded replay's key, the
templates' version, and the played-back day). Nothing here places an order.
"""
from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Any, Callable

from constants_bot import BOT_SCANNER_SETUPS
from constants_eyes import (
    EYES_PLAYBACK_ALERT_STEP_SEC,
    EYES_PLAYBACK_REBUILD_MIN_SEC,
    EYES_REPLAY_SOURCE_SIM,
    EYES_SIM_REBUILD_MIN_SEC,
)
from constants_setups import SETUPS_SCHEMA_VERSION

logger = logging.getLogger(__name__)

KIND_CAPTURE = "capture"
KIND_JOURNAL = "journal"
_WORKER_WAIT_SEC = 0.5


def _default_target() -> dict[str, Any] | None:
    """What the Sim desk shows now: ``None`` at the live edge or off the Sim venue."""
    from sim.mode import is_replay_desk

    if not is_replay_desk():
        return None
    from sim import replay as sim_replay
    from sim import session_clock

    st = sim_replay.status_payload()
    playhead = session_clock.now_et()
    if st.get("replay_source") == KIND_CAPTURE and st.get("replay_ok"):
        return {"kind": KIND_CAPTURE, "date": st.get("replay_date"), "symbol": st.get("replay_symbol"),
                "playhead": playhead.timestamp()}
    loaded = st.get("replay_source") if st.get("replay_source") in ("historical", KIND_CAPTURE) else None
    return {"kind": KIND_JOURNAL, "date": playhead.strftime("%Y-%m-%d"), "playhead": playhead.timestamp(),
            "symbol": st.get("replay_symbol") if loaded else None, "loaded": loaded}


def _journal_path(date: str) -> Path:
    from eyes.journal import journal_dir

    return journal_dir() / f"{date}.jsonl"


class SimEyes:
    def __init__(self, *, target: Callable[[], dict | None] = _default_target,
                 load: Callable[[str, str], Any] | None = None,
                 templates: Callable[[], Any] | None = None,
                 journal: Callable[[dict], None] | None = None,
                 threaded: bool = True,
                 levels: Callable[[], dict] | None = None,
                 journal_path: Callable[[str], Path] = _journal_path):
        self._target_fn = target
        self._journal_path_fn = journal_path
        self._load_fn = load
        self._templates_fn = templates
        self._journal_fn = journal
        self._levels_fn = levels
        self._threaded = threaded
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None
        self.target: dict | None = None
        # Worker-owned state: only the worker thread touches these.
        self._key: tuple[str, str] | None = None
        self._recording: Any = None
        self._replay: Any = None
        self._templates_version: int | None = None
        self._journaled_through = 0.0
        self._last_rebuild = 0.0
        self._playback: Any = None             # eyes.playback.Playback of the played-back day
        # Published for the loop (under the lock).
        self._view: dict[str, Any] = {"loading": False, "error": None, "rows": [], "proposals": [], "setups": [],
                                      "proposing": False, "template": None, "lanes": 0, "recording": None,
                                      "now": None, "universe": 0, "note": None, "gap": None, "journal": None}
        self._alerts: list[dict] = []

    # -- wiring defaults (late imports keep this module light) -------------------------
    def _load(self, date: str, symbol: str) -> Any:
        if self._load_fn is not None:
            return self._load_fn(date, symbol)
        from eyes.recording import load

        return load(date, symbol)

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
        if target is None or target["kind"] != KIND_CAPTURE:
            if self._key is not None:
                self._drop()
            if target is None:
                self._playback = None
            else:
                self._work_journal(target)
            return
        self._playback = None
        key = (str(target["date"]), str(target["symbol"]).upper())
        if key != self._key:
            self._drop()
            self._key = key
            self._publish(loading=True)
            try:
                self._recording = self._load(*key)
                self._publish(loading=False, error=None)
            except (ValueError, OSError) as exc:
                self._publish(loading=False, error=str(exc))
                return
        if self._recording is None:
            return
        store = self._store()
        playhead = float(target["playhead"])
        stale = self._replay is None or store.version() != self._templates_version
        behind = self._replay is not None and playhead < self._replay.now - 1.0
        if stale or (behind and time.monotonic() - self._last_rebuild >= EYES_SIM_REBUILD_MIN_SEC):
            self._rebuild(store, playhead)
        elif not behind:
            self._replay.advance(playhead)
            alerts = self._replay.take_alerts()
            if alerts:
                with self._lock:
                    self._alerts += alerts
        self._publish()

    def _rebuild(self, store: Any, playhead: float) -> None:
        from eyes.replay import EyesReplay

        templates = [t for setup in BOT_SCANNER_SETUPS for t in store.templates(setup) if not t.error]
        playing = {setup: store.in_play(setup).id for setup in BOT_SCANNER_SETUPS}
        replay = EyesReplay(self._recording, templates, source=EYES_REPLAY_SOURCE_SIM, playing=playing,
                            journal=self._journal, levels=self._levels)
        replay.advance(playhead)
        replay.take_alerts()            # a rebuild never re-raises what it passed on the way
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
            pb = self._playback = Playback(JournalDay(Path(self._journal_path_fn(date)), date))
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
                              gap=gap, note=gap_note(gap, date), journal=pb.journal_view())

    def _drop(self) -> None:
        self._key = self._recording = self._replay = None
        self._templates_version = None
        self._journaled_through = 0.0
        self._publish(loading=False, error=None)

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
        }
        with self._lock:
            self._view.update(view)
            self._view.update(overrides)

    # -- output (the loop side) -------------------------------------------------------------
    def take_alerts(self) -> list[dict]:
        with self._lock:
            out, self._alerts = self._alerts, []
        return out

    def board(self, now: float) -> dict[str, Any] | None:
        """The Setups board while the Sim desk shows a replay; ``None`` keeps the live board."""
        from scanner_wire import wire_safe

        with self._lock:
            target = self.target
            view = dict(self._view)
        if target is None:
            return None
        capture = target["kind"] == KIND_CAPTURE
        replay_view = {"kind": target["kind"], "date": target.get("date"), "symbol": target.get("symbol"),
                       "playhead": target.get("playhead"), "at": view["now"], "loading": view["loading"],
                       "error": view["error"], "note": None if capture else view.get("note"),
                       "recording": view["recording"] if capture else None}
        if not capture:
            replay_view.update(loaded=target.get("loaded"), gap=view.get("gap"), journal=view.get("journal"))
        return wire_safe({
            "schema_version": SETUPS_SCHEMA_VERSION, "generated_at": now, "session_date": target.get("date"),
            "source": EYES_REPLAY_SOURCE_SIM,
            "universe": (1 if target.get("symbol") else 0) if capture else int(view.get("universe") or 0),
            "seeding": 1 if view["loading"] else 0, "scoreboard": True, "scoreboard_error": None,
            "proposing": capture and bool(view["proposing"]), "replay": replay_view,
            "setups": view["setups"], "rows": view["rows"], "proposals": view["proposals"],
        })

    def status(self) -> dict[str, Any]:
        with self._lock:
            hidden = ("rows", "proposals", "setups", "proposing")
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
