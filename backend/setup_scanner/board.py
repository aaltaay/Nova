"""The Setups board payload (ADR 022): one row per symbol worth looking at,
nearest-to-trigger first. Pure: reads the engine's state, writes nothing.

Row: ``{symbol, state, reason, kind, nth, setup_id, setup, last_price,
distance, grade, pillars, tape, proposal, outcome, bar_r, mfe, mae}``.
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
    SETUPS_SCHEMA_VERSION,
)

ORDER = {SETUP_STATE_NEAR: 0, SETUP_STATE_ARMED: 1, SETUP_STATE_TRIGGERED: 2,
         SETUP_STATE_PULLBACK: 3, SETUP_STATE_LEG: 4, SETUP_STATE_FAILED: 5}
TRIGGERED_SHOW_SEC = 30 * 60
FAILED_SHOW_SEC = 5 * 60


def build_board(engine: Any, now: float) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for sym, det in engine.det.items():
        if det.state not in ORDER:
            continue
        sid = engine.active_id.get(sym)
        row = engine.rows.get(sid) if sid else None
        if row is not None and row.get("leg_t") != det.view().get("setup_key"):
            row, sid = None, None          # a new leg: the last setup's row is history
        if det.state == SETUP_STATE_TRIGGERED:
            if not row or now - float(row.get("triggered_at") or 0) > TRIGGERED_SHOW_SEC:
                continue
        if det.state == SETUP_STATE_FAILED:
            if not row or now - float(row.get("failed_at") or 0) > FAILED_SHOW_SEC:
                continue
        view = det.view()
        setup = view.get("setup")
        last = view.get("last_price")
        distance = None
        if setup and last is not None and det.state in (SETUP_STATE_ARMED, SETUP_STATE_NEAR):
            distance = round(float(setup["trigger"]) - float(last), 4)
        prop = engine.proposals.get(sid) if sid else None
        tape = engine.tape_view.get(sym)
        rows.append({
            "symbol": sym, "state": det.state, "reason": det.reason, "kind": view.get("kind"),
            "nth": view.get("nth"), "setup_id": sid if row else None, "setup": setup,
            "leg": view.get("leg"), "last_price": last, "distance": distance,
            "grade": (row or {}).get("grade"), "pillars": (row or {}).get("pillars"),
            "tape": {"verdict": tape.get("verdict"), "reasons": tape.get("reasons"),
                     "line": tape.get("line"), "metrics": tape.get("metrics")} if tape else None,
            "proposal": prop if prop and prop.get("status") == "open" else None,
            "outcome": (row or {}).get("outcome"), "bar_r": (row or {}).get("bar_r"),
            "mfe": (row or {}).get("mfe"), "mae": (row or {}).get("mae"),
        })
    rows.sort(key=lambda r: (ORDER.get(r["state"], 9),
                             r["distance"] if r["distance"] is not None else 9e9, r["symbol"]))
    return {
        "schema_version": SETUPS_SCHEMA_VERSION,
        "generated_at": now,
        "session_date": engine.session,
        "universe": len(engine.universe),
        "seeding": len(engine.seeding),
        "scoreboard": engine.store_error is None,
        "scoreboard_error": engine.store_error,
        "proposing": not engine._replay_fn(),
        "rows": rows[:SETUPS_BOARD_MAX_ROWS],
        "proposals": [p for p in engine.proposals.values() if p.get("status") == "open"],
    }
