"""Setups that ended (ADR 036 amendment, operator ask 2026-09-29): a day's eyes'
journal read back as episodes -- one per setup's life on a symbol.

"after it fails to form ... it says 'pole' with a gray square. Eventually, it
removes itself from the chart ... we could probably go back and study them": the
chart draws each lane's current state only; the journal holds every line the lanes
wrote (``setup_scanner/lane_journal.py``). ``EpisodeFold`` folds a day's live lines
of each setup's template in play (``playing: true``), in order:

- an episode opens at the first line that leaves ``watching`` and grows while its
  leg only extends -- the same leg, or a later one whose high is at or over it;
- it ends when the lane goes back to ``watching``, when a failed or triggered
  setup is followed by a new attempt, when a lower or an earlier leg replaces it,
  or at a ``session`` line (Nova restarted: ``cut``);
- a failed episode keeps the first rule it broke, never a later one; a faded one
  keeps what it was waiting on or blocked by when it ended.

The episode's shape is AGENTS.md §3 "Setups that ended stay on the chart". Pure:
lines in, episodes out; ``after`` is filled by ``eyes/aftermath.py``. Nothing is
recomputed with today's rules.
"""
from __future__ import annotations

import re
from typing import Any

from constants_bot import BOT_SETUP_FIRST_PULLBACK
from constants_eyes import EYES_EPISODE_BAR_CLOSE_SEC
from constants_setups import (
    SETUP_STATE_ARMED,
    SETUP_STATE_FAILED,
    SETUP_STATE_LEG,
    SETUP_STATE_NEAR,
    SETUP_STATE_PULLBACK,
    SETUP_STATE_TRIGGERED,
    SETUP_STATE_WATCHING,
    SETUPS_FIVE_MINUTE_STRATEGIES,
)
from setup_scanner.bars import minute_start
from setup_scanner.lane_view import JOURNAL_EVENT_STATES

END_FAILED = "failed"
END_FADED = "faded"
END_TRIGGERED = "triggered"
END_CUT = "cut"
LADDER = {SETUP_STATE_LEG: 1, SETUP_STATE_PULLBACK: 2, SETUP_STATE_ARMED: 3, SETUP_STATE_NEAR: 4,
          SETUP_STATE_TRIGGERED: 5}
PUBLIC = ("id", "symbol", "setup_type", "template", "rev", "started_at", "ended_at", "end", "died_at",
          "died_bar_t", "reason", "reason_key", "ended_by", "reached", "leg", "setup", "setup_id", "filtered",
          "triggered_at", "trigger_price", "score", "after")
NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")
EPS = 1e-9


def reason_key(text: str | None) -> str | None:
    """A reason with every number replaced by ``#``: one row per rule in a report."""
    if not text:
        return None
    return NUMBER.sub("#", text.strip())


def closed_bar_t(ts: float, bar_sec: int = 60) -> float:
    """The start of the candle a line at ``ts`` is about: the one that just closed when the line
    was written at a candle's start (a bar close), else the one forming. ``bar_sec`` is the lane's
    candle: a minute, or a 5-minute lane's five."""
    start = minute_start(ts) if bar_sec == 60 else float(int(ts // bar_sec) * bar_sec)
    return start - float(bar_sec) if ts - start < EYES_EPISODE_BAR_CLOSE_SEC else start


def _same_move(leg: dict[str, Any], new: dict[str, Any]) -> bool:
    """The same leg, or the same move extended to a later, higher (or equal) high."""
    t0, t1 = float(leg.get("t") or 0), float(new.get("t") or 0)
    if t1 == t0:
        return True
    return t1 > t0 and float(new.get("high") or 0) >= float(leg.get("high") or 0) - EPS


class EpisodeFold:
    """Every (symbol, setup) a day's lines name, folded line by line into episodes: the lines of each setup's
    template in play, or -- with ``template`` -- that template's (the 5-minute lanes': ``bar_sec`` 300). A fold
    reads the patterns on its own candles: the 5-minute flat top's template in play (a 1-minute lane whose
    pattern reads 5-minute candles, ADR 031 amendment 2026-10-06) is the 5-minute fold's, not the 1-minute's."""

    def __init__(self, template: str | None = None, bar_sec: int = 60) -> None:
        self.template, self.bar_sec = template, int(bar_sec)
        self.open: dict[tuple[str, str], dict[str, Any]] = {}
        self.ended: list[dict[str, Any]] = []
        self._by_setup_id: dict[str, dict[str, Any]] = {}

    # -- feed -----------------------------------------------------------------------------
    def _mine(self, line: dict[str, Any]) -> bool:
        five = line.get("setup_type") in SETUPS_FIVE_MINUTE_STRATEGIES and line.get("playing") is True
        if self.template:
            return line.get("template") == self.template or (five and self.bar_sec != 60)
        return line.get("playing") is True and not (five and self.bar_sec == 60)

    def apply(self, line: dict[str, Any]) -> None:
        ev = line.get("event")
        ts = float(line.get("ts") or 0.0)
        if ev == "session":                      # Nova started: every lane began again from nothing
            for key in list(self.open):
                self._end(key, ts, "Nova restarted: the eyes began again", cut=True)
            return
        sym = line.get("symbol")
        if not sym or not self._mine(line):
            return
        if ev == "scored":
            self._score(line)
            return
        state = line.get("state") if ev == "state" else JOURNAL_EVENT_STATES.get(str(ev))
        if not state:
            return
        key = (str(sym), str(line.get("setup_type") or BOT_SETUP_FIRST_PULLBACK))
        reason = str(line.get("reason") or "")
        cur = self.open.get(key)
        has_leg = "leg" in line
        leg = line.get("leg") if has_leg else (cur["leg"] if cur else None)
        if state == SETUP_STATE_WATCHING or (has_leg and leg is None and state != SETUP_STATE_TRIGGERED):
            if cur is not None:
                self._end(key, ts, reason)
            return
        if not isinstance(leg, dict):
            return
        if cur is not None and self._new_attempt(cur, state, leg):
            self._end(key, ts, f"a new attempt began: {reason}" if reason else "a new attempt began")
            cur = None
        if cur is None:
            cur = self._open(key, line, ts, leg)
        self._update(cur, str(ev), state, reason, leg, line, ts)

    @staticmethod
    def _new_attempt(cur: dict[str, Any], state: str, leg: dict[str, Any]) -> bool:
        was = cur["_state"]
        if was == SETUP_STATE_TRIGGERED:
            return state != SETUP_STATE_TRIGGERED       # a new setup after a trade
        if was == SETUP_STATE_FAILED and state != SETUP_STATE_FAILED:
            return True                                 # the failed one died; this is another try
        return not _same_move(cur["leg"], leg)

    def _open(self, key: tuple[str, str], line: dict[str, Any], ts: float, leg: dict[str, Any]) -> dict[str, Any]:
        sym, setup = key
        ep: dict[str, Any] = {
            "id": f"{sym}-{setup}-{int(round(ts * 1000))}", "symbol": sym, "setup_type": setup,
            "template": line.get("template"), "rev": line.get("rev"), "started_at": ts, "ended_at": None,
            "end": None, "died_at": None, "died_bar_t": None, "reason": None, "reason_key": None, "ended_by": None,
            "reached": SETUP_STATE_LEG, "leg": dict(leg), "setup": None, "setup_id": None, "filtered": None,
            "triggered_at": None, "trigger_price": None, "score": None, "after": None,
            "_state": SETUP_STATE_WATCHING, "_reason": "",
        }
        self.open[key] = ep
        return ep

    def _update(self, ep: dict[str, Any], ev: str, state: str, reason: str, leg: dict[str, Any],
                line: dict[str, Any], ts: float) -> None:
        ep["leg"] = dict(leg)
        if LADDER.get(state, 0) > LADDER.get(ep["reached"], 0):
            ep["reached"] = state
        if state == SETUP_STATE_FAILED and ep["died_at"] is None:
            ep["died_at"], ep["died_bar_t"], ep["reason"] = ts, closed_bar_t(ts, self.bar_sec), reason
        setup = line.get("setup")
        if ev in ("armed", "rearmed", "filtered", "triggered") and isinstance(setup, dict) and setup:
            ep["setup"] = dict(setup)
        if line.get("setup_id"):
            ep["setup_id"] = str(line["setup_id"])
            self._by_setup_id[ep["setup_id"]] = ep
        if ev == "filtered":
            ep["filtered"] = reason or None
        if ev == "triggered":
            ep["triggered_at"] = float((setup or {}).get("triggered_at") or ts)
            ep["trigger_price"] = line.get("price")
            ep["reason"] = reason or None
        ep["template"], ep["rev"] = line.get("template") or ep["template"], line.get("rev") or ep["rev"]
        ep["_state"], ep["_reason"] = state, reason

    def _end(self, key: tuple[str, str], ts: float, ended_by: str, *, cut: bool = False) -> None:
        ep = self.open.pop(key)
        ep["ended_at"], ep["ended_by"] = ts, ended_by or None
        if ep["triggered_at"] is not None:
            ep["end"] = END_TRIGGERED
        elif ep["died_at"] is not None:
            ep["end"] = END_FAILED               # it had failed before whatever ended it
        elif cut:
            ep["end"], ep["reason"] = END_CUT, ep["_reason"] or None   # how it would have ended is unknown
        else:
            ep["end"] = END_FADED
            ep["died_at"], ep["died_bar_t"] = ts, closed_bar_t(ts, self.bar_sec)
            ep["reason"] = ep["_reason"] or ended_by or None
        ep["reason_key"] = reason_key(ep["reason"])
        self.ended.append(ep)

    def _score(self, line: dict[str, Any]) -> None:
        ep = self._by_setup_id.get(str(line.get("setup_id") or ""))
        if ep is not None:
            ep["score"] = {"outcome": line.get("outcome"), "bar_r": line.get("bar_r"),
                           "exit_reason": line.get("exit_reason"), "mfe": line.get("mfe"), "mae": line.get("mae")}

    # -- read -----------------------------------------------------------------------------
    def episodes(self, symbol: str | None = None) -> list[dict[str, Any]]:
        """Copies of the ended and the open episodes (of ``symbol``), oldest first. An open one's
        ``reason`` is the rule it broke once it failed (the lane may show it a while longer), else what
        its lane says now."""
        sym = symbol.upper() if symbol else None
        out = []
        for ep in [*self.ended, *self.open.values()]:
            if sym is not None and ep["symbol"].upper() != sym:
                continue
            row = {k: ep[k] for k in PUBLIC}
            if ep["end"] is None:
                row["reason"] = ep["reason"] if ep["died_at"] is not None else (ep["_reason"] or None)
                row["reason_key"] = reason_key(row["reason"])
            row["leg"] = dict(ep["leg"])
            if ep["setup"] is not None:
                row["setup"] = dict(ep["setup"])
            if ep["score"] is not None:
                row["score"] = dict(ep["score"])
            out.append(row)
        out.sort(key=lambda e: e["started_at"])
        return out


def fold(lines: Any) -> EpisodeFold:
    """A fold over ``lines`` (an iterable of journal lines, in order)."""
    f = EpisodeFold()
    for line in lines:
        f.apply(line)
    return f
