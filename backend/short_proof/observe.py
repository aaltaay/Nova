"""The Live short proof's observer (ADR 048 step 6): Paper's ledger and IBKR's session, read as they move.

``pass_once`` runs on the short runner's loop (``short_sale.runner``), every second: it watches IBKR's
session for a drop while Paper holds a short, and, at most every ``SHORT_PROOF_OBSERVE_SEC`` and only when
the Paper ledger changed, records its filled short entries (the short days) and the covers Flatten and the
day cover made (``evidence``). ``note_freeze`` is the kill switch's hook: it runs right after a trip's
sweep, with what the sweep kept. Nothing here places, cancels or holds an order, and a failure only ever
loses a record, logged -- never the trip, the pass or the order.
"""
from __future__ import annotations

import logging
import time
from typing import Any

from constants_shorts import SHORT_PROOF_OBSERVE_SEC
from short_proof import evidence, store

logger = logging.getLogger(__name__)

_DRILL_ORIGINS = (("flatten", "ticket_flatten"), ("day_cover", "day_cover"))
_DRILL_WORDS = {
    "flatten": "Flatten covered {qty:g} {symbol} short on Paper",
    "day_cover": "The 15:55 cover covered {qty:g} {symbol} short on Paper",
}
# The ledger last scanned (its identity and event count), IBKR's session at the last pass, an open drop.
_state: dict[str, Any] = {"ledger": None, "events": -1, "scanned_at": 0.0, "up": None, "drop": None}


def _paper() -> Any:
    from practice.broker import for_venue

    return for_venue("paper")


def _held(broker: Any) -> dict[str, float]:
    ledger = broker.ledger
    return {sym: float(ledger.held_qty(sym)) for sym in ledger.held_symbols()}


def _scan(broker: Any) -> None:
    """Record the ledger's short fills and drill covers once the ledger changed."""
    ledger = broker.ledger
    key = (id(ledger), float(ledger.created_ts))
    count = len(ledger.events)
    if _state["ledger"] == key and _state["events"] == count:
        return
    rows = ledger.closed_orders()
    store.record_short_fills(evidence.short_fills(rows))
    for name, origin in _DRILL_ORIGINS:
        runs = evidence.covers(rows, origin)
        if runs:
            run = runs[0]
            store.record_drill(name, True, {**run, "detail": _DRILL_WORDS[name].format(**run)})
    _state["ledger"], _state["events"] = key, count


def _session_up() -> bool:
    from ibkr import client as _client

    return bool(_client.is_connected() and _client.get_ib() is not None)


def _gateway(broker: Any, now: float) -> None:
    """A drop of IBKR's session with a Paper short open, judged when the session is back."""
    up = _session_up()
    was, _state["up"] = _state["up"], up
    drop = _state["drop"]
    if was and not up and drop is None:
        shorts = evidence.shorts_held(_held(broker))
        if shorts:
            _state["drop"] = {"since": now, "shorts": shorts}
        return
    if up and drop is not None:
        _state["drop"] = None
        passed, run = evidence.gateway_back(drop["since"], now, drop["shorts"], _held(broker),
                                            broker.working_orders())
        store.record_drill("gateway_drop", passed, run)


def pass_once(now: float | None = None) -> None:
    """One look; never raises (the short runner's closes come first)."""
    now = time.time() if now is None else float(now)
    try:
        broker = _paper()
        _gateway(broker, now)
        if time.monotonic() - _state["scanned_at"] >= SHORT_PROOF_OBSERVE_SEC:
            _state["scanned_at"] = time.monotonic()
            _scan(broker)
    except Exception:
        logger.exception("short proof: the observer's pass failed -- nothing was recorded this pass")


def note_freeze(sweep: list[dict[str, Any]], *, now: float | None = None) -> None:
    """The kill switch tripped: the freeze drill, from Paper's shorts and what its sweep kept."""
    try:
        paper = next((v for v in sweep if v.get("venue") == "paper"), None)
        if paper is None:
            return
        got = evidence.freeze(time.time() if now is None else float(now),
                              evidence.shorts_held(_held(_paper())), list(paper.get("kept") or []))
        if got is not None:
            store.record_drill("freeze", got[0], got[1])
    except Exception:
        logger.exception("short proof: the freeze drill could not be recorded -- the trip itself stands")


def reset_for_tests() -> None:
    _state.update(ledger=None, events=-1, scanned_at=0.0, up=None, drop=None)
