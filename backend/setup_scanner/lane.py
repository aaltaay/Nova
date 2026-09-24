"""One template's eyes (ADR 029): a lane of one setup's detectors over the
scanner's symbols, with its own scoreboard rows, tape reads, proposals and
journal lines.

The engine runs one lane per template of every setup with a scanner (ADR 031)
on the same bars and the same tape; a replay runs the same lanes over a Session
Record. Only the lane whose template is in play for its setup may raise
proposals, and only when its host allows it for that setup (its level, ADR
031). A setup the template's stock filter keeps out is journalled as
``filtered`` and goes no further: no tape read, no score, no row.

The host (``SetupEngine`` live, ``eyes.replay.EyesReplay`` on a recording)
supplies ``session``, ``pillars(sym, now)``, ``tape_books(sym)``,
``tape_prints(sym)``, ``tape_line(sym)``, ``save(row)``, ``journal(event)``,
``audit(**kw)``, ``clock()`` and ``can_propose(setup_type)``, and may supply
``on_trigger(event)`` (the live engine: ADR 030), ``flow(sym, now, params)`` (a
shared, cached tape flow reading) and ``tape_since(sym)`` (the earliest moment
its prints vouch for). Nothing here places an order.

ADR 034: every tape read carries the tape flow score, and a triggered setup's
flow is read through its scoring window (``setup_scanner/lane_flow.py``).
"""
from __future__ import annotations

import uuid
from typing import Any

from constants_bot import BOT_SETUP_FIRST_PULLBACK
from constants_setups import (
    SETUP_STATE_NEAR,
    SETUP_STATE_TRIGGERED,
    SETUP_TEMPLATE_DEFAULT_ID,
    SETUPS_SCORE_WINDOW_MIN,
    TAPE_VERDICT_BLIND,
    TAPE_VERDICT_GO,
)
from setup_scanner import grade as _grade
from setup_scanner import lane_view
from setup_scanner.bars import Bar, minute_start
from setup_scanner.detector import TriggerDetector
from setup_scanner.detectors import make_detector
from setup_scanner.lane_params import LaneParams
from setup_scanner import lane_flow, tape_flow
from setup_scanner.scoring import ScoreTracker
from setup_scanner.tape_gate import evaluate as evaluate_tape

WATCH_STATES = lane_view.WATCH_STATES
STATE_FILTERED = lane_view.STATE_FILTERED
# Why an open proposal closed, as the Bots page timeline says it.
PROPOSAL_CLOSE_REASONS = {
    "rearmed": "re-armed at new levels -- the next go raises a fresh one",
    "disarmed": "the setup disarmed",
    "failed": "the setup failed before its trigger",
    "triggered": "the trigger printed",
    "template": "another template went in play",
    "edited": "the template's rules changed",
    "deleted": "the template was deleted",
}
ORDER = lane_view.ORDER


def slim(res: dict) -> dict:
    return {"verdict": res.get("verdict"), "reasons": res.get("reasons"), "line": res.get("line"),
            "flow": tape_flow.brief(res.get("flow"))}


class Lane:
    def __init__(self, params: LaneParams, host: Any, *, playing: bool = False):
        self.p = params
        self.host = host
        self.playing = playing
        self.det: dict[str, TriggerDetector] = {}
        self.rows: dict[str, dict] = {}
        self.active_id: dict[str, str] = {}
        self.trackers: dict[str, ScoreTracker] = {}
        self.tape_view: dict[str, dict] = {}
        self.proposals: dict[str, dict] = {}
        self.filtered: dict[str, str] = {}
        self.alerts: list[dict] = []
        self._tape_said: dict[str, str] = {}
        self.flow_last: dict[str, dict] = {}      # setup id -> the newest flow reading after its trigger
        self._flow_said: dict[str, str] = {}
        self._flow_next: dict[str, float] = {}

    # -- identity -------------------------------------------------------------
    @property
    def template_id(self) -> str:
        return self.p.template_id

    @property
    def setup(self) -> str:
        return self.p.setup

    def sid(self, sym: str, key: Any) -> str:
        """``SYMBOL-DATE-KEY`` for the first pullback's default (ADR 022); another setup adds
        ``@SETUP`` (ADR 031) and another template ``~TEMPLATE_ID`` (ADR 029)."""
        base = f"{sym}-{self.host.session}-{key}"
        if self.p.setup != BOT_SETUP_FIRST_PULLBACK:
            base = f"{base}@{self.p.setup}"
        return base if self.p.template_id == SETUP_TEMPLATE_DEFAULT_ID else f"{base}~{self.p.template_id}"

    def stamp(self) -> dict[str, Any]:
        return {"template_id": self.p.template_id, "template_rev": self.p.template_rev,
                "params_hash": self.p.params_hash, "setup_type": self.p.setup}

    def journal(self, event: str, sym: str | None, **fields: Any) -> None:
        self.host.journal({"event": event, "symbol": sym, "setup_type": self.p.setup, "template": self.p.template_id,
                           "rev": self.p.template_rev, "playing": self.playing, **fields})

    # -- symbols ----------------------------------------------------------------
    def clear(self) -> None:
        for store in (self.det, self.rows, self.active_id, self.trackers, self.tape_view,
                      self.proposals, self.filtered, self._tape_said, self.flow_last, self._flow_said,
                      self._flow_next):
            store.clear()
        self.alerts = []

    def ensure(self, sym: str) -> TriggerDetector:
        det = self.det.get(sym)
        if det is None:
            det = self.det[sym] = make_detector(self.p.setup, sym, self.p.pattern)
        return det

    def drop(self, sym: str) -> None:
        self.det.pop(sym, None)

    def watching(self) -> set[str]:
        """Symbols whose live setup wants the tape read (armed or near, not filtered)."""
        return {s for s, d in self.det.items()
                if d.state in WATCH_STATES and self.active_id.get(s) not in self.filtered}

    def busy(self) -> set[str]:
        """Symbols this lane still needs: a watched setup or a trade being scored."""
        return self.watching() | {self.rows[sid]["symbol"] for sid in self.trackers if sid in self.rows}

    def trades(self, now: float) -> list[str]:
        """Setup ids whose trade is inside its scoring window: their flow is read (ADR 034)."""
        return lane_flow.trades(self, now)

    def trade_symbols(self, now: float) -> set[str]:
        return {self.rows[sid]["symbol"] for sid in self.trades(now)}

    def _tracker_ids(self, sym: str) -> list[str]:
        return [sid for sid in self.trackers if self.rows.get(sid, {}).get("symbol") == sym]

    # -- feed -------------------------------------------------------------------
    def on_bars(self, sym: str, bars: list[Bar], now: float, new_bar: Bar | None = None) -> None:
        det = self.ensure(sym)
        before = (det.state, det.reason)
        events = det.on_bars(bars)
        self.handle(sym, events, now)
        if not events and (det.state, det.reason) != before and not det.reason.startswith("warming up"):
            view = det.view()
            self.journal("state", sym, state=det.state, reason=det.reason, leg=view.get("leg"))
        if new_bar is not None:
            for sid in self._tracker_ids(sym):
                if self.trackers[sid].on_bar(new_bar, det.ema_now):
                    self._score(sid)

    def on_price(self, sym: str, price: float, ts: float, bar_open: float | None) -> None:
        det = self.det.get(sym)
        if det is None:
            return
        self.handle(sym, det.on_price(price, ts, bar_open=bar_open), ts)
        for sid in self._tracker_ids(sym):
            if self.trackers[sid].on_price(price, ts):
                self._score(sid)

    def sweep(self, now: float) -> None:
        """Close the scoring of trades whose window has passed."""
        for sid in list(self.trackers):
            tr = self.trackers[sid]
            if tr.exit_px is not None and now > tr.triggered_at + SETUPS_SCORE_WINDOW_MIN * 60 and tr.outcome != "open":
                self._score(sid)
                self.trackers.pop(sid, None)

    # -- events -> rows -----------------------------------------------------------
    def handle(self, sym: str, events: list[tuple[str, dict]], now: float) -> None:
        for kind, view in events:
            sid = self.sid(sym, view["setup_key"])
            row = self.rows.get(sid)
            if kind == "leg":
                self.journal("leg", sym, reason=view.get("reason"), leg=view.get("leg"))
                continue
            if kind == "armed":
                if row is None:
                    row = self._new_row(sym, sid, view, now)
                else:
                    if row.get("disarmed_at"):
                        row["disarmed_at"] = None      # the same leg armed again
                    if row.get("failed_at"):
                        row["failed_at"] = row["fail_reason"] = None   # a flat top's base armed again
                self._copy_setup(row, view)
                self.active_id[sym] = sid
                if sid in self.filtered:
                    row.update({"state": STATE_FILTERED, "reason": f"filtered: {self.filtered[sid]}"})
                    continue
                self.journal("armed", sym, setup_id=sid, setup=view.get("setup"), grade=row.get("grade"),
                             pillars=row.get("pillars"), reason=view.get("reason"))
            elif row is None or sid in self.filtered:
                det = self.det.get(sym)
                if kind == "triggered" and sid in self.filtered and det is not None and det.nth > 0:
                    det.nth -= 1   # a setup the template kept out is not one of its setups that day
                continue
            elif kind == "rearmed":
                self._copy_setup(row, view)
                self.journal("rearmed", sym, setup_id=sid, setup=view.get("setup"), reason=view.get("reason"))
                self._close_proposal(sid, "rearmed")    # its levels are stale; a new read proposes again
            elif kind == "near":
                row["state"] = view["state"]
                tape = None
                if not row.get("near_at"):
                    row["near_at"] = now
                    tape = self.evaluate(sym, now)
                    row["near_tape"] = slim(tape)
                self.journal("near", sym, setup_id=sid, last=view.get("last_price"), reason=view.get("reason"),
                             tape=tape)
            elif kind == "triggered":
                setup = view.get("setup") or {}
                ts = float(setup.get("triggered_at") or now)
                tape = self.evaluate(sym, ts)
                row.update({"state": SETUP_STATE_TRIGGERED, "reason": view["reason"], "triggered_at": ts,
                            "entry": setup.get("entry"), "nth": setup.get("nth"), "trigger_tape": tape,
                            "outcome": "open", "stop": setup.get("stop"), "risk": setup.get("risk"),
                            "target1": setup.get("target1"), "detail": setup.get("detail")})
                # A flat-top hold enters at a candle's close: it is scored from that candle,
                # which takes no half at target 1 (the research's half_on_entry_bar=False).
                self.trackers[sid] = ScoreTracker(
                    entry=float(setup["entry"]), stop=float(setup["stop"]), target1=float(setup["target1"]),
                    risk=float(setup["risk"]), triggered_at=ts,
                    entry_bar_t=float(setup.get("score_bar_t") or minute_start(ts)),
                    bailout_bars=self.p.bailout_bars,
                    half_on_entry_bar=bool(setup.get("half_on_entry_bar", True)), flush=self.p.flush)
                self.journal("triggered", sym, setup_id=sid, setup=setup, price=setup.get("trigger_price"),
                             tape=tape)
                self._close_proposal(sid, "triggered")
                self._announce_trigger(sym, sid, setup, tape, ts)
            elif kind in ("failed", "disarmed") and not row.get("triggered_at"):
                row.update({"state": view["state"], "reason": view["reason"]})
                row["failed_at" if kind == "failed" else "disarmed_at"] = now
                if kind == "failed":
                    row["fail_reason"] = view["reason"]
                self.journal(kind, sym, setup_id=sid, reason=view["reason"])
                self._close_proposal(sid, kind)
            self.host.save(row)

    def _new_row(self, sym: str, sid: str, view: dict, now: float) -> dict:
        setup = view.get("setup") or {}
        pillars = self.host.pillars(sym, now)
        g, checks = _grade.grade(pillars, self.p.grade)
        row = {"id": sid, "session_date": self.host.session, "symbol": sym, "leg_t": view["setup_key"],
               "armed_at": setup.get("armed_at") or now, "grade": g,
               "pillars": {**pillars, "checks": checks, "float_note": _grade.float_note(pillars, self.p.grade)},
               **self.stamp()}
        self.rows[sid] = row
        why = self.p.stock.check(pillars, g) if self.p.stock.active else None
        if why:
            self.filtered[sid] = why
            self.journal(STATE_FILTERED, sym, setup_id=sid, reason=why, setup=setup, grade=g,
                         pillars=row["pillars"])
        return row

    def _copy_setup(self, row: dict, view: dict) -> None:
        s = view.get("setup") or {}
        row.update({"state": view["state"], "reason": view["reason"], "kind": s.get("kind"),
                    "trigger": s.get("trigger"), "entry_planned": s.get("entry"), "stop": s.get("stop"),
                    "risk": s.get("risk"), "target1": s.get("target1"), "leg_high": s.get("leg_high"),
                    "leg_low": s.get("leg_low"), "leg_pct": s.get("leg_pct"),
                    "pullback_bars": s.get("pullback_bars"), "detail": s.get("detail")})

    def _score(self, sid: str) -> None:
        tr, row = self.trackers.get(sid), self.rows.get(sid)
        if tr is None or row is None:
            return
        before = (row.get("outcome"), row.get("bar_r"))
        row.update(tr.as_dict())
        self.host.save(row)
        if (row.get("outcome"), row.get("bar_r")) != before:
            self.journal("scored", row["symbol"], setup_id=sid, outcome=row.get("outcome"), bar_r=row.get("bar_r"),
                         exit_reason=row.get("bar_exit_reason"), mfe=row.get("mfe"), mae=row.get("mae"))

    # -- tape gate + proposals -------------------------------------------------
    def evaluate(self, sym: str, now: float) -> dict:
        det = self.det.get(sym)
        setup = (det.armed or det.triggered) if det else None
        if not setup:
            return {"verdict": TAPE_VERDICT_BLIND, "reasons": ["no setup"], "metrics": {}}
        res = evaluate_tape(trigger=float(setup["trigger"]), now=now, books=self.host.tape_books(sym),
                            prints=self.host.tape_prints(sym), p=self.p.gate, flow=self.flow(sym, now))
        res["line"] = self.host.tape_line(sym)
        return res

    def flow(self, sym: str, now: float) -> dict:
        """The tape flow at ``now`` under this template's numbers (``lane_flow.flow``)."""
        return lane_flow.flow(self, sym, now)

    def read_trades(self, now: float) -> None:
        """Each trade on: read its flow and let the template's flush exit act (``lane_flow.read_trades``)."""
        lane_flow.read_trades(self, now)

    def gate(self, now: float) -> None:
        wanted = self.watching()
        for sym in list(self.tape_view):
            if sym not in wanted:
                self.tape_view.pop(sym, None)
        for sym in wanted:
            res = self.evaluate(sym, now)
            self.tape_view[sym] = res
            sid = self.active_id.get(sym)
            if sid and self._tape_said.get(sid) != res["verdict"]:
                self._tape_said[sid] = res["verdict"]
                self.journal("tape", sym, setup_id=sid, verdict=res["verdict"], reasons=res.get("reasons"),
                             metrics=res.get("metrics"), line=res.get("line"), last=self.det[sym].last_price)
            prop = self.proposals.get(sid) if sid else None
            if prop is not None and prop["status"] == "open":
                prop["tape_now"] = res["verdict"]
            elif (sid and self.playing and self.det[sym].state == SETUP_STATE_NEAR
                  and res["verdict"] == TAPE_VERDICT_GO and self.host.can_propose(self.p.setup)):
                # No open proposal: none yet, or the last one was withdrawn when the
                # setup re-armed at new levels or was disarmed and armed again.
                self._propose(sym, sid, res, now)
        self.read_trades(now)

    def _propose(self, sym: str, sid: str, res: dict, now: float) -> None:
        row = self.rows.get(sid) or {}
        prop = {"id": str(uuid.uuid4()), "setup_id": sid, "symbol": sym, "kind": row.get("kind"),
                "trigger": row.get("trigger"), "entry": row.get("entry_planned"), "stop": row.get("stop"),
                "target1": row.get("target1"), "risk": row.get("risk"), "grade": row.get("grade"),
                "reasons": res.get("reasons"), "created_at": now, "status": "open", "tape_now": res["verdict"],
                "template_id": self.p.template_id, "template_name": self.p.name, "source": self.host.source,
                "setup_type": self.p.setup}
        self.proposals[sid] = prop
        self.alerts.append(prop)
        row["proposal_id"] = prop["id"]
        self.host.save(row)
        self.journal("proposal", sym, setup_id=sid, status="proposed", proposal=prop)
        self.host.audit(action="setup_proposal", outcome="proposed",
                        reason=(f"{str(prop['kind'] or 'setup').replace('_', ' ')} on {sym}: trigger "
                                f"{prop['trigger']}, stop {prop['stop']} -- tape go"),
                        inputs=prop)

    def _announce_trigger(self, sym: str, sid: str, setup: dict, tape: dict, ts: float) -> None:
        """The playing lane tells its host a setup triggered (ADR 030); a replay host has no ear for it."""
        notify = getattr(self.host, "on_trigger", None)
        if not self.playing or notify is None:
            return
        notify({"symbol": sym, "setup_id": sid, "setup": dict(setup), "tape": slim(tape), "ts": ts,
                "template_id": self.p.template_id, "template_rev": self.p.template_rev,
                "template_name": self.p.name, "setup_type": self.p.setup})

    def _close_proposal(self, sid: str, status: str) -> None:
        prop = self.proposals.get(sid)
        if prop is not None and prop["status"] == "open":
            prop["status"] = status
            prop["closed_at"] = self.host.clock()
            self.journal("proposal", prop["symbol"], setup_id=sid, status=status,
                         reason=PROPOSAL_CLOSE_REASONS.get(status, status))
            # The close is on the audit stream too: a re-arm replaces this entry.
            self.host.audit(action="setup_proposal", outcome=status,
                            reason=PROPOSAL_CLOSE_REASONS.get(status, status), inputs=dict(prop))

    def withdraw_all(self, status: str = "template") -> None:
        for sid in list(self.proposals):
            self._close_proposal(sid, status)

    # -- board (setup_scanner/lane_view.py) --------------------------------------------
    def board_rows(self, now: float) -> list[dict[str, Any]]:
        return lane_view.board_rows(self, now)

    def open_proposals(self) -> list[dict]:
        return [p for p in self.proposals.values() if p.get("status") == "open"]

    def counts(self) -> dict[str, int]:
        return lane_view.counts(self)
