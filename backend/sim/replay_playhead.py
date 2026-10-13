"""The Sim playhead while the desk replays the past (operator report, 2026-10-12).

For reads that must show the replayed moment, never today's: the scanner quote
panel's pillars (``routes/strategy.py``) and its news (``catalysts/routes.py``).
On 2026-07-15's replay both showed today's GRML. ``None`` on a live desk -- Live,
Paper, or the Sim at its live edge, which reads the live feed (ADR 020).

Owner: this module (no state). Reads ``sim.mode`` and ``sim.session_clock``.
"""
from __future__ import annotations

import logging

from sim import mode

logger = logging.getLogger(__name__)


def replay_playhead() -> float | None:
    """The playhead (epoch s) off the live edge, else None.

    A live edge that cannot be read counts as a replay: today's facts never stand
    in for a past day's.
    """
    try:
        replaying = mode.is_replay_desk()
    except Exception:
        logger.warning("sim: the live edge is unreadable -- the desk counts as a replay", exc_info=True)
        replaying = True
    if not replaying:
        return None
    from sim import session_clock

    return session_clock.now_et().timestamp()
