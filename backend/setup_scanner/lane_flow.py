"""A lane's tape flow (ADR 034): the reading at a tape read, and a trade's after its trigger.

``flow`` is the tape flow at a moment under the lane's template numbers -- the
host's shared, cached reading when it has one (``LaneHost.flow``,
``EyesReplay.flow``), else summed here from the host's prints and books.

``read_trades`` reads every trade inside its scoring window every
``TAPE_FLOW_EVAL_SEC``: the template's flush exit acts on the scoring
(``ScoreTracker.on_flow``), the newest reading is kept for Nova's bot
(``lane.flow_last``), and a turn into or out of a burst or a flush is journalled
as ``flow`` (what a flush did, as ``flush``). Nothing here places an order.
"""
from __future__ import annotations

from typing import Any

from constants_setups import SETUPS_SCORE_WINDOW_MIN, TAPE_FLOW_BURST, TAPE_FLOW_EVAL_SEC, TAPE_FLOW_FLUSH
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
            if sid in lane.rows and tr.triggered_at <= now <= tr.triggered_at + SETUPS_SCORE_WINDOW_MIN * 60]


def read_trades(lane: Any, now: float) -> None:
    for sid in trades(lane, now):
        if now < lane._flow_next.get(sid, 0.0):
            continue
        lane._flow_next[sid] = now + TAPE_FLOW_EVAL_SEC
        row, tr = lane.rows[sid], lane.trackers[sid]
        sym = row["symbol"]
        det = lane.det.get(sym)
        reading = flow(lane, sym, now)
        price = det.last_price if det is not None else None
        bid = (reading.get("metrics") or {}).get("best_bid")
        label, score = reading.get("label"), reading.get("score")
        lane.flow_last[sid] = {"ts": now, "label": label, "score": score, "price": price, "bid": bid,
                               "readings": reading.get("readings")}
        was = lane._flow_said.get(sid)
        if label != was and (label in LOUD or was in LOUD):
            lane.journal("flow", sym, setup_id=sid, label=label, was=was, score=score,
                         readings=reading.get("readings"), price=price,
                         since_trigger=round(now - tr.triggered_at, 1))
        lane._flow_said[sid] = label
        act = tr.on_flow(label=label, price=price, bid=bid, ts=now)
        if act is not None:
            lane.journal("flush", sym, setup_id=sid, action=act, score=score, price=price, bid=bid,
                         stop=tr.bar_stop, exit_px=tr.exit_px, mode=lane.p.flush.mode)
            lane._score(sid)
