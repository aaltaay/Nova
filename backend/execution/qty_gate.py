"""MASTER TEST QTY GATE — force place/bracket size to one share.

INTENTIONAL safety clamp for testing (see ``IBKR_FORCE_ONE_SHARE`` in
``constants_ibkr.py``). Not a sizing bug. Flip the constant to False to
restore normal quantities; do not remove this module silently.

The clamp stops a fat-fingered size from reaching the broker. It never touches
a protective order (``flatten`` / ``kill`` / ``cancel_working``): those size
themselves from the held position to get the account flat. Clamping them made
an Emergency KILL sell 1 share of a 2-share position and report success
(QA R6, 2026-09-22); AGENTS.md sec. 5 says a desk must always be able to get flat.
"""
from __future__ import annotations

import logging
from dataclasses import replace

from constants import IBKR_FORCE_ONE_SHARE, IBKR_FORCE_ONE_SHARE_QTY
from execution.models import ExecutionCommand
from ibkr.safety import PROTECTIVE_SOURCES

logger = logging.getLogger(__name__)

__all__ = ["apply_force_one_share"]


def apply_force_one_share(cmd: ExecutionCommand) -> ExecutionCommand:
    """Return ``cmd`` with place/bracket qty+shares forced when the gate is on.

    Cancel/replace are untouched (replace reuses the open order's qty), and so
    is every protective source: a flatten closes the whole held position.
    """
    if not IBKR_FORCE_ONE_SHARE:
        return cmd
    if cmd.operation not in ("place", "bracket"):
        return cmd
    if (cmd.source or "") in PROTECTIVE_SOURCES:
        return cmd

    forced = float(IBKR_FORCE_ONE_SHARE_QTY)
    forced_shares = int(forced)
    qty = cmd.qty
    shares = cmd.shares
    if qty is None and shares is None:
        return cmd

    already = True
    if qty is not None and float(qty) != forced:
        already = False
    if shares is not None and int(shares) != forced_shares:
        already = False
    if already:
        return cmd

    logger.warning(
        "IBKR_FORCE_ONE_SHARE: clamping %s %s qty=%s shares=%s → %s "
        "(MASTER TEST GATE — flip IBKR_FORCE_ONE_SHARE=False to disable)",
        cmd.operation,
        (cmd.side or "").upper() or "?",
        qty,
        shares,
        forced_shares,
    )
    return replace(
        cmd,
        qty=forced if qty is not None else None,
        shares=forced_shares if shares is not None else None,
    )
