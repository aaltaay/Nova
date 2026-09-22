"""The ``mode`` stamp an execution row carries (QA R38, 2026-09-22).

The venue on Paper / Sim, the Gateway port label (``paper`` / ``live`` /
``disconnected``) on Live -- the same stamp a practice send writes
(``sim/execution.py``) and the one ``execution/closed_blotter.py`` scopes rows
by. A refused practice order used to read ``disconnected`` (or ``live`` on a
connected desk) while its filled siblings read the venue, so a reader grouping
executions by ``mode`` misfiled every practice refusal.
"""
from __future__ import annotations

import logging

from ibkr import client as _client

logger = logging.getLogger(__name__)


def desk_mode() -> str:
    """The settled venue on a practice desk, else the Gateway session's label."""
    try:
        from sim.mode import is_practice_venue, venue

        if is_practice_venue():
            return venue()
    except Exception:
        logger.exception("execution: desk venue unreadable -- stamping the Gateway label")
    return _client.account_mode()
