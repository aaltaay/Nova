"""A lane's tape flow (ADR 034): the reading at a tape read, and a trade's after its trigger.

``flow`` is the tape flow at a moment under the lane's template numbers -- the
host's shared, cached reading when it has one (``LaneHost.flow``,
``EyesReplay.flow``), else summed here from the host's prints and books.

``trades`` lists the setups inside their scoring window. ADR 072 (2026-11-13): the strategies read Level 1, so the
tape's flush no longer acts on a setup's scoring and no trade's flow is read after its trigger (``read_trades`` and
the flush exit it drove are gone). Nothing here places an order.
"""
from __future__ import annotations

from typing import Any

from constants_setups import TAPE_FLOW_BURST, TAPE_FLOW_FLUSH
from setup_scanner import tape_flow

LOUD = (TAPE_FLOW_BURST, TAPE_FLOW_FLUSH)


def flow(lane: Any, sym: str, now: float) -> dict:
    shared = getattr(lane.host, "flow", None)
    if shared is not None:
        return shared(sym, now, lane.p.flow)
    since = getattr(lane.host, "tape_since", None)
    return tape_flow.evaluate(now=now, books=lane.host.tape_books(sym), prints=lane.host.tape_prints(sym),
                              p=lane.p.flow, history_from=since(sym) if since else None)


def trades(lane: Any, now: float) -> list[str]:
    """Setup ids whose trade is inside its scoring window."""
    return [sid for sid, tr in lane.trackers.items()
            if sid in lane.rows and tr.triggered_at <= now <= tr.triggered_at + tr.window_min * 60]
