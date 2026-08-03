"""MASTER TEST QTY GATE — force place/bracket size to one share.

INTENTIONAL safety clamp for testing (see ``IBKR_FORCE_ONE_SHARE`` in
``constants_ibkr.py``). Not a sizing bug. Flip the constant to False to
restore normal quantities; do not remove this module silently.
"""
from __future__ import annotations

import logging
from dataclasses import replace

from constants import IBKR_FORCE_ONE_SHARE, IBKR_FORCE_ONE_SHARE_QTY
from execution.models import ExecutionCommand

logger = logging.getLogger(__name__)

__all__ = ["apply_force_one_share"]


def apply_force_one_share(cmd: ExecutionCommand) -> ExecutionCommand:
    """Return ``cmd`` with place/bracket qty+shares forced when the gate is on.

    Cancel/replace are untouched (replace reuses the open order's qty).
    """
    if not IBKR_FORCE_ONE_SHARE:
        return cmd
    if cmd.operation not in ("place", "bracket"):
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
