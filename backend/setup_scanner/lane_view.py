"""A lane's board rows and today's counts (ADR 022, ADR 031): what the Setups board
and a setup's card draw from one lane. Pure: reads the lane, writes nothing.

Moved out of ``lane.py`` so the lane keeps one concern -- turning detector events
into rows, tape reads and proposals.
"""
from __future__ import annotations

from typing import Any

from constants_setups import (
    SETUP_STATE_ARMED,
    SETUP_STATE_FAILED,
    SETUP_STATE_LEG,
    SETUP_STATE_NEAR,
    SETUP_STATE_PULLBACK,
    SETUP_STATE_TRIGGERED,
    SETUPS_BOARD_MAX_ROWS,
)

WATCH_STATES = (SETUP_STATE_ARMED, SETUP_STATE_NEAR)
FORMING_STATES = (SETUP_STATE_LEG, SETUP_STATE_PULLBACK)
STATE_FILTERED = "filtered"          # a board / journal state only: the detector never holds it
ORDER = {SETUP_STATE_NEAR: 0, SETUP_STATE_ARMED: 1, SETUP_STATE_TRIGGERED: 2, SETUP_STATE_PULLBACK: 3,
         SETUP_STATE_LEG: 4, STATE_FILTERED: 5, SETUP_STATE_FAILED: 6}
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
TRIGGERED_SHOW_SEC = 30 * 60
FAILED_SHOW_SEC = 5 * 60
# The detector state an eyes' journal line says the symbol is in after it (a ``state`` line
# names its own). The lane writes a ``state`` line whenever the detector differs from what
# its last line implied, so a playback of the journal (``eyes/playback.py``) folds to the
# state the card showed. A line not named here leaves the state as it was.
JOURNAL_EVENT_STATES = {"leg": SETUP_STATE_LEG, "armed": SETUP_STATE_ARMED, STATE_FILTERED: SETUP_STATE_ARMED,
                        "rearmed": SETUP_STATE_ARMED, "near": SETUP_STATE_NEAR,
                        "triggered": SETUP_STATE_TRIGGERED, "failed": SETUP_STATE_FAILED,
                        "disarmed": SETUP_STATE_PULLBACK}


def board_rows(lane: Any, now: float) -> list[dict[str, Any]]:
    """One row per symbol worth looking at, nearest its trigger first."""
    rows: list[dict[str, Any]] = []
    for sym, det in lane.det.items():
        if det.state not in ORDER:
            continue
        sid, row, state, reason, phase = _current(lane, sym, det)
        if state == STATE_FILTERED:
            # Kept on the card, greyed, while the pattern is in reach and for the triggered rows' window.
            at = float((det.view().get("setup") or {}).get("triggered_at") or 0)
            if phase == SETUP_STATE_TRIGGERED and now - at > TRIGGERED_SHOW_SEC:
                continue
        elif state == SETUP_STATE_TRIGGERED:
            if not row or now - float(row.get("triggered_at") or 0) > TRIGGERED_SHOW_SEC:
                continue
        elif state == SETUP_STATE_FAILED:
            if not row or now - float(row.get("failed_at") or 0) > FAILED_SHOW_SEC:
                continue
        rows.append(_payload(lane, sym, det.view(), sid, row, state, reason, phase))
    rows.sort(key=lambda r: (ORDER.get(r["state"], 9),
                             r["distance"] if r["distance"] is not None else 9e9, r["symbol"]))
    return rows[:SETUPS_BOARD_MAX_ROWS]


def symbol_row(lane: Any, sym: str) -> dict[str, Any] | None:
    """One symbol's row whatever its state (``watching`` too), with the forming levels and the
    lane's own indicators (ADR 036); None when the lane has no detector for it yet."""
    det = lane.det.get(sym)
    if det is None:
        return None
    sid, row, state, reason, phase = _current(lane, sym, det)
    view = det.symbol_view()
    return {**_payload(lane, sym, view, sid, row, state, reason, phase), "forming": view["forming"],
            "series": view["series"]}


def _current(lane: Any, sym: str, det: Any) -> tuple[str | None, dict | None, str, str, str | None]:
    """The symbol's live row (None when a new leg made the last one history), its shown state and
    reason, and -- under a ``filtered`` row -- where the pattern itself stands."""
    sid = lane.active_id.get(sym)
    row = lane.rows.get(sid) if sid else None
    if row is not None and row.get("leg_t") != det.view().get("setup_key"):
        row, sid = None, None          # a new leg: the last setup's row is history
    state, reason, phase = det.state, det.reason, None
    if sid in lane.filtered and state in WATCH_STATES + (SETUP_STATE_TRIGGERED,):
        state, reason, phase = STATE_FILTERED, f"filtered: {lane.filtered[sid]}", state
    return sid, row, state, reason, phase


def graded(row: dict | None, forming: dict | None, state: str) -> dict[str, Any]:
    """``grade`` / ``pillars`` / ``graded``: the armed setup's own read, else -- while the pattern forms --
    the read taken when its leg made its high (``lane.forming``)."""
    if row is not None:
        return {"grade": row.get("grade"), "pillars": row.get("pillars"), "graded": "armed"}
    if forming and state in FORMING_STATES:
        return {"grade": forming.get("grade"), "pillars": forming.get("pillars"), "graded": "forming"}
    return {"grade": None, "pillars": None, "graded": None}


def tf5_read(row: dict | None, forming: dict | None, state: str) -> dict[str, Any]:
    """``tf5`` / ``tf5_at``: the 5-minute chart's read (``five_minute.context``) at the moment that matters for
    the row -- at the trigger once it triggered, else when it armed, else (while the pattern forms) when its
    leg made its high. Trial T8 reads the trigger's."""
    if row is not None:
        if row.get("triggered_at"):
            return {"tf5": row.get("tf5_trigger"), "tf5_at": "trigger"}
        return {"tf5": row.get("tf5_armed"), "tf5_at": "armed"}
    if forming and state in FORMING_STATES:
        return {"tf5": forming.get("tf5"), "tf5_at": "forming"}
    return {"tf5": None, "tf5_at": None}


def tape_brief(tape: dict | None) -> dict[str, Any] | None:
    """A tape read as a row names it: the verdict and its reasons."""
    return {"verdict": tape.get("verdict"), "reasons": tape.get("reasons")} if isinstance(tape, dict) else None


def in_reach(state: str, phase: str | None) -> bool:
    """Armed or near -- a filtered row by its pattern's own state: its distance is shown."""
    return state in WATCH_STATES or (state == STATE_FILTERED and phase in WATCH_STATES)


def _payload(lane: Any, sym: str, view: dict, sid: str | None, row: dict | None, state: str,
             reason: str, phase: str | None) -> dict[str, Any]:
    setup = view.get("setup")
    last = view.get("last_price")
    distance = None
    if setup and last is not None and in_reach(state, phase):
        distance = round(float(setup["trigger"]) - float(last), 4)
    prop = lane.proposals.get(sid) if sid else None
    tape = lane.tape_view.get(sym)
    return {
        "symbol": sym, "setup_type": lane.p.setup, "state": state, "reason": reason, "kind": view.get("kind"),
        "nth": view.get("nth"), "setup_id": sid if row else None, "setup": setup,
        "leg": view.get("leg"), "last_price": last, "distance": distance,
        **graded(row, lane.forming.get(sym), state), **tf5_read(row, lane.forming.get(sym), state), "phase": phase,
        "tape": {"verdict": tape.get("verdict"), "reasons": tape.get("reasons"),
                 "line": tape.get("line"), "metrics": tape.get("metrics")} if tape else None,
        "trigger_tape": tape_brief((row or {}).get("trigger_tape")),
        "proposal": prop if prop and prop.get("status") == "open" else None,
        "outcome": (row or {}).get("outcome"), "outcome_at": (row or {}).get("outcome_at"),
        "bar_r": (row or {}).get("bar_r"), "mfe": (row or {}).get("mfe"), "mae": (row or {}).get("mae"),
        "failed_at": (row or {}).get("failed_at"),
    }


def counts(lane: Any) -> dict[str, int]:
    """Today's funnel for the setup card (ADR 031): the symbols followed and forming now,
    then today's rows -- armed (the filter's kept out), near, triggered, failed, proposed."""
    kept = [(sid, r) for sid, r in lane.rows.items() if sid not in lane.filtered]
    return {
        "watching": len(lane.det),
        "forming": sum(1 for d in lane.det.values() if d.state in (SETUP_STATE_LEG, SETUP_STATE_PULLBACK)),
        "armed": len(kept),
        "near": sum(1 for _, r in kept if r.get("near_at")),
        "triggered": sum(1 for _, r in kept if r.get("triggered_at")),
        "failed": sum(1 for _, r in kept if r.get("failed_at")),
        "filtered": len(lane.filtered),
        "proposed": sum(1 for _, r in kept if r.get("proposal_id")),
    }
