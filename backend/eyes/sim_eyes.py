"""The Sim eyes (ADR 029): the setup scanner's lanes following the Sim playhead
over the loaded Session Record.

On the Sim desk off the live edge with a Session Record loaded, the Setups
board is this replay's -- the recorded symbol at the playhead -- instead of
the live market's, and its proposals are practice proposals on that desk
(pushed on ``/ws/setups``, journalled, never on the bot's audit stream). A
historical download carries no Level 2, so the board states that rather than
guess a tape. With nothing loaded the live board stays.

Every read and step of the recording runs on one worker thread, never on the
scanner's loop: the loop only posts the playhead (``tick``) and reads the last
published board (``board``). A forward playhead advances the replay; a rewind
or a template change rebuilds it (at most every ``EYES_SIM_REBUILD_MIN_SEC``
for rewinds). The journal gets each moment once: a rebuild replays silently up
to the furthest point already journalled.

Owner: this module (in memory only; invalidation: the loaded replay's key and
the templates' version). Nothing here places an order.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable

from constants_bot import BOT_SETUP_FIRST_PULLBACK
from constants_eyes import EYES_REPLAY_SOURCE_SIM, EYES_SIM_REBUILD_MIN_SEC
from constants_setups import SETUPS_SCHEMA_VERSION

logger = logging.getLogger(__name__)

HISTORICAL_NOTE = ("Sim eyes read Session Records: this replay is a historical download with no Level 2, "
                   "so there is no tape to gate on. Load a Session Record to watch the eyes here.")
_WORKER_WAIT_SEC = 0.5


def _default_target() -> dict[str, Any] | None:
    """What the Sim desk shows now: ``None`` when it is not a replay desk or nothing is loaded."""
    from sim.mode import is_replay_desk

    if not is_replay_desk():
        return None
    from sim import replay as sim_replay
    from sim import session_clock

    st = sim_replay.status_payload()
    source = st.get("replay_source")
    if source == "historical":
        return {"kind": "historical", "date": st.get("replay_date"), "symbol": st.get("replay_symbol")}
    if source != "capture" or not st.get("replay_ok"):
        return None
    return {"kind": "capture", "date": st.get("replay_date"), "symbol": st.get("replay_symbol"),
            "playhead": session_clock.now_et().timestamp()}


class SimEyes:
    def __init__(self, *, target: Callable[[], dict | None] = _default_target,
                 load: Callable[[str, str], Any] | None = None,
                 templates: Callable[[], Any] | None = None,
                 journal: Callable[[dict], None] | None = None,
                 threaded: bool = True):
        self._target_fn = target
        self._load_fn = load
        self._templates_fn = templates
        self._journal_fn = journal
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
        # Published for the loop (under the lock).
        self._view: dict[str, Any] = {"loading": False, "error": None, "rows": [], "proposals": [],
                                      "template": None, "lanes": 0, "recording": None, "now": None}
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
        if target is None or target["kind"] != "capture":
            if self._key is not None:
                self._drop()
            return
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

        templates = [t for t in store.templates(BOT_SETUP_FIRST_PULLBACK) if not t.error]
        playing = store.in_play(BOT_SETUP_FIRST_PULLBACK).id
        replay = EyesReplay(self._recording, templates, source=EYES_REPLAY_SOURCE_SIM, playing_id=playing,
                            journal=self._journal)
        replay.advance(playhead)
        replay.take_alerts()            # a rebuild never re-raises what it passed on the way
        self._replay = replay
        self._templates_version = store.version()
        self._last_rebuild = time.monotonic()

    def _drop(self) -> None:
        self._key = self._recording = self._replay = None
        self._templates_version = None
        self._journaled_through = 0.0
        self._publish(loading=False, error=None)

    def _publish(self, **overrides: Any) -> None:
        from setup_scanner.board import template_view

        replay = self._replay
        lane = replay.playing if replay is not None else None
        view = {
            "rows": lane.board_rows(replay.now) if lane is not None else [],
            "proposals": lane.open_proposals() if lane is not None else [],
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
        capture = target["kind"] == "capture"
        replay_view = {"kind": target["kind"], "date": target.get("date"), "symbol": target.get("symbol"),
                       "playhead": target.get("playhead"), "at": view["now"], "loading": view["loading"],
                       "error": view["error"], "note": None if capture else HISTORICAL_NOTE,
                       "recording": view["recording"] if capture else None}
        return wire_safe({
            "schema_version": SETUPS_SCHEMA_VERSION, "generated_at": now, "session_date": target.get("date"),
            "source": EYES_REPLAY_SOURCE_SIM, "template": view["template"] if capture else None,
            "templates_watched": view["lanes"] if capture else 0, "universe": 1 if target.get("symbol") else 0,
            "seeding": 1 if view["loading"] else 0, "scoreboard": True, "scoreboard_error": None,
            "proposing": capture, "replay": replay_view,
            "rows": view["rows"] if capture else [], "proposals": view["proposals"] if capture else [],
        })

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {"target": self.target, **{k: v for k, v in self._view.items() if k not in ("rows", "proposals")}}


_sim_eyes: SimEyes | None = None


def get_sim_eyes() -> SimEyes:
    global _sim_eyes
    if _sim_eyes is None:
        _sim_eyes = SimEyes()
    return _sim_eyes


def reset_for_tests() -> None:
    global _sim_eyes
    _sim_eyes = None
