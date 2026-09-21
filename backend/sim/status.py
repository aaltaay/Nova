"""Overlay /api/ibkr/status for the desk venue (ADR 020). Tab Record is a side flag only.

Live adds ``venue: "live"`` and changes nothing else. Paper and Sim answer as
Nova's practice account: ``mode`` / ``venue`` name the venue, ``account_id``
is ``NOVA-PAPER`` / ``NOVA-SIM``, spend reads the ADR 018 arm latch alone
(``paper_armed`` / ``sim_armed`` or ``locked_disarmed``) and never the IBKR
env gates. Sim is usable without a Gateway, so it forces ``connected``; Paper
needs the live feed, so its ``connected`` is the live client's real state.
"""
from __future__ import annotations

import logging
from typing import Any

from constants_practice import PRACTICE_ACCOUNT_ID_PAPER, PRACTICE_ACCOUNT_ID_SIM
from constants_sim import DESK_VENUE_LIVE, DESK_VENUE_SIM

logger = logging.getLogger(__name__)


def _recording_fields() -> dict[str, Any]:
    persistence: dict[str, Any] = {"capture_sessions": [], "capture_resume": [], "capture_stopped": []}
    try:
        from capture import keepalive
        from capture.mode import status_payload as capture_status_payload
        from capture.recorder import status as recorder_status

        capture = capture_status_payload()
        recording = bool(capture["capture"])
        record_symbol = capture["capture_symbol"]
        record_symbols = list(capture.get("capture_symbols") or [])
        record_error = capture.get("error")
        persistence = keepalive.status_fields(recorder_status(), record_symbols)
    except Exception:
        logger.exception("RECORD: capture status unavailable")
        record_error = "Recording status unavailable"
        recording = False
        record_symbol = None
        record_symbols = []
    return {
        "capture": recording,
        "capture_symbol": record_symbol,
        "capture_symbols": record_symbols,
        "recording": recording,
        "capture_error": record_error,
        **persistence,
    }


def _practice_fields(current: str) -> dict[str, Any]:
    """What a practice venue overrides on the IBKR status payload."""
    from ibkr.safety import DISARMED_REASON, armed as _armed_now
    from sim.mode import practice_spend_status, status_payload as venue_status_payload

    is_armed = _armed_now()
    sim = current == DESK_VENUE_SIM
    out: dict[str, Any] = dict(venue_status_payload())
    out["mode"] = current
    out["venue"] = current
    out["sim"] = sim
    out["account_id"] = PRACTICE_ACCOUNT_ID_SIM if sim else PRACTICE_ACCOUNT_ID_PAPER
    out["account_ids"] = [out["account_id"]]
    # ADR 018: the arm latch is about the *process*, not the door, so the
    # practice venues read it too -- otherwise the venue would be answering
    # "may I place", which is exactly the coupling ADR 018 breaks. Fake money
    # needs no .env permission (ADR 020 decision 4), only the arm.
    out["armed"] = is_armed
    out["spend_status"] = practice_spend_status(current, is_armed)
    out["spend_locked_reason"] = None if is_armed else DISARMED_REASON
    out["spend_permitted"] = True
    out["spend_permitted_status"] = practice_spend_status(current, True)
    out["spend_permitted_reason"] = None
    out["armed_for_account_kind"] = None
    out["trading_allowed"] = is_armed
    out["trading_allowed_reason"] = None if is_armed else DISARMED_REASON
    if sim:
        # Sim is usable without a Gateway: the replay is the market.
        out["connected"] = True
        out["enabled"] = True
        out["session_state"] = "ready"
        out["session_reason"] = "ok"
    else:
        # Paper needs the feed: `connected` stays the live client's real state.
        out["broker_account_kind"] = current
    return out


def overlay_ibkr_status(payload: dict[str, Any]) -> dict[str, Any]:
    """Force desk-usable practice fields. Gateway transport stays honest."""
    try:
        from sim.mode import is_practice_venue, venue
    except Exception:
        logger.exception("SIM: desk venue unavailable -- status answers as Live")
        is_practice_venue = lambda: False  # noqa: E731
        venue = lambda: DESK_VENUE_LIVE  # noqa: E731

    recording = _recording_fields()
    out = dict(payload)
    current = venue()
    if is_practice_venue():
        out.update(_practice_fields(current))
        out.update(recording)
        return out

    out["venue"] = current
    out.setdefault("sim", False)
    out.update(recording)
    # Tab Record must NOT rewrite mode or trading_allowed -- Live stays itself.
    return out
