"""What a lane writes to the eyes' journal (ADR 029; operator ask 2026-09-24).

A journal line read back at any moment (``eyes/playback.py``) must be the card
as it stood then, so a lane's lines say everything its card shows:

- ``line`` stamps every line with the lane (setup, template, revision, whether it
  plays), and every line about a symbol with the detector's last price and leg;
  it remembers the state each line implies (``lane_view.JOURNAL_EVENT_STATES``,
  or a ``state`` line's own).
- ``say_state`` writes a ``state`` line whenever the detector's state or reason
  differs from what the last line implied -- a disarm followed by a new state, a
  near-to-armed flip on a price -- never while it warms up.
- ``say_price`` writes a ``price`` line for a name within reach of the playing
  lane's trigger, at most every ``EYES_JOURNAL_PRICE_EVERY_SEC``, so a playback's
  "to go" is the card's.

Owner: ``setup_scanner/lane.py`` (the lane keeps ``_said`` / ``_priced``; nothing
is kept here).
"""
from __future__ import annotations

from typing import Any

from constants_eyes import EYES_JOURNAL_PRICE_EVERY_SEC
from setup_scanner.lane_view import JOURNAL_EVENT_STATES, WATCH_STATES


def line(lane: Any, event: str, sym: str | None, fields: dict[str, Any]) -> None:
    if sym is not None:
        det = lane.det.get(sym)
        if det is not None:
            if det.last_price is not None:
                fields.setdefault("last", det.last_price)
            fields.setdefault("leg", dict(det.leg) if det.leg else None)
        implied = fields.get("state") if event == "state" else JOURNAL_EVENT_STATES.get(event)
        if implied:
            lane._said[sym] = (implied, str(fields.get("reason") or ""))
    lane.host.journal({"event": event, "symbol": sym, "setup_type": lane.p.setup, "template": lane.p.template_id,
                       "rev": lane.p.template_rev, "playing": lane.playing, **fields})


def say_state(lane: Any, sym: str, det: Any) -> None:
    """A ``state`` line when the detector is not where the journal's lines left it."""
    if lane._said.get(sym) == (det.state, det.reason) or det.reason.startswith("warming up"):
        return
    view = det.view()
    lane.journal("state", sym, state=det.state, reason=det.reason, leg=view.get("leg"),
                 kind=view.get("kind"), nth=det.nth)


def say_price(lane: Any, sym: str, det: Any, ts: float) -> None:
    """The playing lane's price for a name within reach of its trigger."""
    if not lane.playing or det.state not in WATCH_STATES or det.last_price is None:
        return
    prev = lane._priced.get(sym)
    if prev is not None and (ts - prev[0] < EYES_JOURNAL_PRICE_EVERY_SEC or prev[1] == det.last_price):
        return
    lane._priced[sym] = (ts, det.last_price)
    lane.journal("price", sym)
