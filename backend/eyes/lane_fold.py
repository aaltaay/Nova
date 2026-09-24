"""One lane's setup card, folded from its journal lines (operator ask, 2026-09-24).

``LaneFold`` is what ``lane_view.board_rows`` / ``lane_view.counts`` read off a
live lane -- each symbol's detector state, the rows armed, the filter's
verdicts, the tape in reach, the proposals -- rebuilt from the lines the lane
wrote (``setup_scanner/lane.py``). A line says what the detector's state became
(``lane_view.JOURNAL_EVENT_STATES``, or a ``state`` line's own), and carries the
detector's leg; ``eyes/playback.py`` feeds it the day's lines in order. Pure.

Owner: ``eyes/playback.py`` (a fold lives in its ``Playback``; no state here).
"""
from __future__ import annotations

from typing import Any

from constants_setups import (
    SETUP_STATE_FAILED,
    SETUP_STATE_LEG,
    SETUP_STATE_PULLBACK,
    SETUP_STATE_TRIGGERED,
    SETUP_STATE_WATCHING,
    SETUPS_BOARD_MAX_ROWS,
)
from setup_scanner.lane_view import (
    FAILED_SHOW_SEC,
    JOURNAL_EVENT_STATES,
    ORDER,
    STATE_FILTERED,
    TRIGGERED_SHOW_SEC,
    WATCH_STATES,
)

COUNT_KEYS = ("watching", "forming", "armed", "near", "triggered", "failed", "filtered", "proposed")


class LaneFold:
    """One template's lane of one setup, as its journal lines left it."""

    def __init__(self, setup: str, template: str):
        self.setup, self.template = setup, template
        self.syms: dict[str, dict[str, Any]] = {}
        self.rows: dict[str, dict[str, Any]] = {}
        self.active: dict[str, str] = {}
        self.filtered: dict[str, str] = {}
        self.tape: dict[str, dict[str, Any]] = {}
        self.proposals: dict[str, dict[str, Any]] = {}

    def apply(self, ev: str, sym: str, line: dict[str, Any], ts: float) -> dict | None:
        """Fold one line; a proposal it raised, or None."""
        s = self.syms.setdefault(sym, {"state": SETUP_STATE_WATCHING, "reason": "", "leg": None, "kind": None,
                                       "nth": 0})
        sid = line.get("setup_id")
        row = self.rows.get(sid) if sid else None
        raised = None
        if ev in ("armed", STATE_FILTERED):
            setup = line.get("setup") or {}
            if row is None:
                row = self.rows[sid] = {"id": sid, "symbol": sym, "leg_t": setup.get("leg_t"),
                                        "armed_at": setup.get("armed_at") or ts, "grade": line.get("grade"),
                                        "pillars": line.get("pillars")}
            else:
                row["disarmed_at"] = row["failed_at"] = None      # the same setup armed again
            if setup:
                row["setup"] = setup
            self.active[sym] = sid
            if ev == STATE_FILTERED:
                self.filtered[sid] = line.get("reason") or "the template's stock filter"
        elif ev == "rearmed" and row is not None:
            row["setup"] = line.get("setup") or row.get("setup")
        elif ev == "near" and row is not None:
            row.setdefault("near_at", ts)
        elif ev == "triggered":
            setup = line.get("setup") or {}
            s["nth"] = setup.get("nth") or s["nth"]
            if row is not None:
                row.update(setup=setup or row.get("setup"), triggered_at=float(setup.get("triggered_at") or ts),
                           outcome="open")
        elif ev in ("failed", "disarmed") and row is not None and not row.get("triggered_at"):
            row["failed_at" if ev == "failed" else "disarmed_at"] = ts
        elif ev == "scored" and row is not None:
            row.update(outcome=line.get("outcome"), bar_r=line.get("bar_r"), mfe=line.get("mfe"),
                       mae=line.get("mae"))
        elif ev == "proposal" and sid:
            raised = self._proposal(sid, row, line, ts)
        if ev in ("near", "tape") and isinstance(line.get("tape" if ev == "near" else "verdict"), (dict, str)):
            tape = line["tape"] if ev == "near" else line
            self.tape[sym] = {"verdict": tape.get("verdict"), "reasons": tape.get("reasons"),
                              "line": tape.get("line"), "metrics": tape.get("metrics")}
        self._state(ev, s, line)
        if "leg" in line:
            s["leg"] = line["leg"]               # the detector's leg when the line was written
        if s["state"] not in WATCH_STATES:
            self.tape.pop(sym, None)            # the live gate forgets the tape once a setup leaves reach
        return raised

    @staticmethod
    def _state(ev: str, s: dict[str, Any], line: dict[str, Any]) -> None:
        state = line.get("state") if ev == "state" else JOURNAL_EVENT_STATES.get(ev)
        if not state:
            return
        s["state"] = state
        if ev == "triggered" and not line.get("reason"):
            setup = line.get("setup") or {}
            price, trig = line.get("price"), setup.get("trigger")
            s["reason"] = (f"traded {float(price):.2f} over the {float(trig):.2f} trigger"
                           if price is not None and trig is not None else "triggered")
        else:
            s["reason"] = line.get("reason") or ""
        for key in ("kind", "nth"):
            if line.get(key) is not None:
                s[key] = line[key]

    def _proposal(self, sid: str, row: dict | None, line: dict[str, Any], ts: float) -> dict | None:
        status = line.get("status")
        if status == "proposed":
            prop = {**(line.get("proposal") or {}), "status": "open"}
            self.proposals[sid] = prop
            if row is not None:
                row["proposal_id"] = prop.get("id")
            return dict(prop)
        prop = self.proposals.get(sid)
        if prop is not None and prop.get("status") == "open":
            prop.update(status=status, closed_at=ts)
        return None

    # -- the card --------------------------------------------------------------------
    def board_rows(self, at: float, last: dict[str, float]) -> list[dict[str, Any]]:
        """``lane_view.board_rows`` over the fold: one row per symbol worth looking at."""
        out: list[dict[str, Any]] = []
        for sym, s in self.syms.items():
            state, reason = s["state"], s["reason"]
            if state not in ORDER:
                continue
            sid = self.active.get(sym)
            row = self.rows.get(sid) if sid else None
            reach = state in WATCH_STATES or state == SETUP_STATE_TRIGGERED
            if row is not None and not reach:
                leg_t = (s.get("leg") or {}).get("t")
                if leg_t is None or int(float(leg_t)) != int(float(row.get("leg_t") or 0)):
                    row = None                  # a new leg: the last setup's row is history
            if row is None:
                sid = None
            if sid in self.filtered and reach:
                state, reason = STATE_FILTERED, f"filtered: {self.filtered[sid]}"
                if at - float(row.get("armed_at") or at) > FAILED_SHOW_SEC:
                    continue
            elif state == SETUP_STATE_TRIGGERED:
                if not row or at - float(row.get("triggered_at") or 0) > TRIGGERED_SHOW_SEC:
                    continue
            elif state == SETUP_STATE_FAILED:
                if not row or at - float(row.get("failed_at") or 0) > FAILED_SHOW_SEC:
                    continue
            setup = (row or {}).get("setup") if reach else None
            px = last.get(sym)
            distance = None
            if setup and px is not None and state in WATCH_STATES and setup.get("trigger") is not None:
                distance = round(float(setup["trigger"]) - float(px), 4)
            prop = self.proposals.get(sid) if sid else None
            out.append({
                "symbol": sym, "setup_type": self.setup, "state": state, "reason": reason,
                "kind": (setup or {}).get("kind") or s.get("kind"), "nth": s.get("nth") or 0,
                "setup_id": sid, "setup": setup, "leg": s.get("leg"), "last_price": px, "distance": distance,
                "grade": (row or {}).get("grade"), "pillars": (row or {}).get("pillars"),
                "tape": self.tape.get(sym), "proposal": prop if prop and prop.get("status") == "open" else None,
                "outcome": (row or {}).get("outcome"), "bar_r": (row or {}).get("bar_r"),
                "mfe": (row or {}).get("mfe"), "mae": (row or {}).get("mae"),
                "failed_at": (row or {}).get("failed_at"),
            })
        out.sort(key=lambda r: (ORDER.get(r["state"], 9),
                                r["distance"] if r["distance"] is not None else 9e9, r["symbol"]))
        return out[:SETUPS_BOARD_MAX_ROWS]

    def counts(self, watching: int) -> dict[str, int]:
        """``lane_view.counts`` over the fold: the funnel up to the moment."""
        kept = [(sid, r) for sid, r in self.rows.items() if sid not in self.filtered]
        return {
            "watching": watching,
            "forming": sum(1 for s in self.syms.values() if s["state"] in (SETUP_STATE_LEG, SETUP_STATE_PULLBACK)),
            "armed": len(kept),
            "near": sum(1 for _, r in kept if r.get("near_at")),
            "triggered": sum(1 for _, r in kept if r.get("triggered_at")),
            "failed": sum(1 for _, r in kept if r.get("failed_at")),
            "filtered": len(self.filtered),
            "proposed": sum(1 for _, r in kept if r.get("proposal_id")),
        }
