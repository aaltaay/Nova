"""What IBKR lets this desk hold, and how much of it is in use: the capacity strip's one read. Memory reads only.

Four caps (architecture/schema/desk-ops.md, "IBKR capacity on the desk"): Level 1 quote lines, Level 2 books,
historical requests in IBKR's 10-minute window, Time & Sales lines. Each is ``used`` of ``cap`` with who uses it.
A part that cannot be read raises: the route says why, and the strip never shows a guessed count.
"""
from __future__ import annotations

import time
from typing import Any

from constants import IBKR_L1_STREAM_BUDGET, IBKR_L1_STREAM_RESERVE


def _l1() -> dict[str, Any]:
    from ibkr import ticks

    st = ticks.ticker_budget_status()
    learned = st.get("reqMktData_cap")
    limit = int(st.get("reqMktData_limit") or IBKR_L1_STREAM_BUDGET)
    cap = limit if learned is None else min(limit, int(learned))
    return {"used": int(st["reqMktData_lines"]), "cap": cap, "cap_learned": learned is not None,
            "reserve": int(IBKR_L1_STREAM_RESERVE), "refused": int(st.get("reqMktData_refused") or 0),
            "by_owner": {k: int(v) for k, v in (st.get("reqMktData_by_owner") or {}).items() if v}}


def _l2() -> dict[str, Any]:
    """Level 2 lines in use, each with the lanes on it (ADR 071): ``held_by`` is ``you`` / ``claude`` / ``bots`` joined
    with ``+``, ``replay`` for a Sim replay slot, or ``no lane`` for a live line no lane holds (the idle guard's)."""
    from constants_ibkr import IBKR_MAX_DEPTH_SYMBOLS
    from ibkr import depth
    from line_lanes import lanes

    table = lanes.table()
    lines = [{"symbol": sym, "held_by": "+".join(table.owners_of(sym)) or ("no lane" if depth.is_live(sym) else "replay")}
             for sym in sorted(depth.subscribed_symbols())]
    return {"used": len(lines), "cap": int(IBKR_MAX_DEPTH_SYMBOLS), "symbols": lines}


def _history() -> dict[str, Any]:
    from ibkr.historical_service import pacing_snapshot

    snap = pacing_snapshot()
    return {"used": int(snap["window_used"]), "cap": int(snap["window_max"]), "window_sec": float(snap["window_sec"]),
            "next_free_sec": float(snap.get("next_token_wait_sec") or 0.0), "by_kind": dict(snap.get("by_kind") or {})}


def _tape() -> dict[str, Any]:
    from ibkr import tape_admission

    got = tape_admission.view()
    symbols = sorted({*(got.get("active") or ()), *(got.get("pending") or ()), *(got.get("uncertain") or ())})
    return {"used": int(got.get("used") or 0), "cap": got.get("limit"), "symbols": symbols}


def view(now: float | None = None) -> dict[str, Any]:
    return {"schema_version": 1, "generated_at": time.time() if now is None else now,
            "l1": _l1(), "l2": _l2(), "history": _history(), "tape": _tape()}
