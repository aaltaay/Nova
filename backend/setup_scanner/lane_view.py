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
STATE_FILTERED = "filtered"          # a board / journal state only: the detector never holds it
ORDER = {SETUP_STATE_NEAR: 0, SETUP_STATE_ARMED: 1, SETUP_STATE_TRIGGERED: 2, SETUP_STATE_PULLBACK: 3,
         SETUP_STATE_LEG: 4, STATE_FILTERED: 5, SETUP_STATE_FAILED: 6}
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
        sid = lane.active_id.get(sym)
        row = lane.rows.get(sid) if sid else None
        view = det.view()
        if row is not None and row.get("leg_t") != view.get("setup_key"):
            row, sid = None, None          # a new leg: the last setup's row is history
        state, reason = det.state, det.reason
        if sid in lane.filtered and state in WATCH_STATES + (SETUP_STATE_TRIGGERED,):
            state, reason = STATE_FILTERED, f"filtered: {lane.filtered[sid]}"
            if now - float(row.get("armed_at") or now) > FAILED_SHOW_SEC:
                continue
        elif state == SETUP_STATE_TRIGGERED:
            if not row or now - float(row.get("triggered_at") or 0) > TRIGGERED_SHOW_SEC:
                continue
        elif state == SETUP_STATE_FAILED:
            if not row or now - float(row.get("failed_at") or 0) > FAILED_SHOW_SEC:
                continue
        setup = view.get("setup")
        last = view.get("last_price")
        distance = None
        if setup and last is not None and state in WATCH_STATES:
            distance = round(float(setup["trigger"]) - float(last), 4)
        prop = lane.proposals.get(sid) if sid else None
        tape = lane.tape_view.get(sym)
        rows.append({
            "symbol": sym, "setup_type": lane.p.setup, "state": state, "reason": reason, "kind": view.get("kind"),
            "nth": view.get("nth"), "setup_id": sid if row else None, "setup": setup,
            "leg": view.get("leg"), "last_price": last, "distance": distance,
            "grade": (row or {}).get("grade"), "pillars": (row or {}).get("pillars"),
            "tape": {"verdict": tape.get("verdict"), "reasons": tape.get("reasons"),
                     "line": tape.get("line"), "metrics": tape.get("metrics")} if tape else None,
            "proposal": prop if prop and prop.get("status") == "open" else None,
            "outcome": (row or {}).get("outcome"), "bar_r": (row or {}).get("bar_r"),
            "mfe": (row or {}).get("mfe"), "mae": (row or {}).get("mae"),
            "failed_at": (row or {}).get("failed_at"),
        })
    rows.sort(key=lambda r: (ORDER.get(r["state"], 9),
                             r["distance"] if r["distance"] is not None else 9e9, r["symbol"]))
    return rows[:SETUPS_BOARD_MAX_ROWS]


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
