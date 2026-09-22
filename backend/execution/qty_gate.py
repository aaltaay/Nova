"""MASTER TEST QTY GATE — cap place/bracket size at ``IBKR_FORCE_ONE_SHARE_QTY`` shares.

INTENTIONAL safety clamp for testing (see ``IBKR_FORCE_ONE_SHARE`` in
``constants_ibkr.py``). Not a sizing bug. Flip the constant to False to
restore normal quantities; do not remove this module silently.

Until 2026-09-22 the gate forced every order to exactly one share. The operator
raised it to a cap (#444): a size at or under the cap is sent as asked, a larger
one is cut to the cap, on every venue. The names stay so the execution record's
``forced_one_share`` stamp and its readers are unchanged.

The clamp stops a fat-fingered size from reaching the broker. It never touches
a protective order (``flatten`` / ``kill`` / ``cancel_working``): those size
themselves from the held position to get the account flat. Clamping them made
an Emergency KILL sell 1 share of a 2-share position and report success
(QA R6, 2026-09-22); AGENTS.md sec. 5 says a desk must always be able to get flat.
"""
from __future__ import annotations

import logging
import os
from dataclasses import replace

from constants import IBKR_FORCE_ONE_SHARE, IBKR_FORCE_ONE_SHARE_QTY, IBKR_QTY_CAP_ENV
from execution.models import ExecutionCommand
from ibkr.safety import PROTECTIVE_SOURCES

logger = logging.getLogger(__name__)

__all__ = ["apply_force_one_share", "qty_cap"]


def _cap_shares() -> float:
    """The one place the cap comes from: ``IBKR_QTY_CAP`` in the desk .env when it is a
    positive number, else the ``IBKR_FORCE_ONE_SHARE_QTY`` default. Everything else --
    the clamp, ``/api/ibkr/status`` ``qty_cap``, the ticket's copy -- reads this."""
    raw = (os.environ.get(IBKR_QTY_CAP_ENV) or "").strip()
    if raw:
        try:
            value = float(raw)
            if value >= 1:
                return float(int(value))
        except ValueError:
            pass
        logger.warning("%s=%r is not a whole number >= 1; using the default %s",
                       IBKR_QTY_CAP_ENV, raw, IBKR_FORCE_ONE_SHARE_QTY)
    return float(IBKR_FORCE_ONE_SHARE_QTY)


def qty_cap() -> float | None:
    """The cap in shares while the gate is on, else None (what the ticket states)."""
    return _cap_shares() if IBKR_FORCE_ONE_SHARE else None


def apply_force_one_share(cmd: ExecutionCommand) -> ExecutionCommand:
    """Return ``cmd`` with place/bracket qty+shares capped when the gate is on.

    Cancel/replace are untouched (replace reuses the open order's qty), and so
    is every protective source: a flatten closes the whole held position.
    """
    if not IBKR_FORCE_ONE_SHARE:
        return cmd
    if cmd.operation not in ("place", "bracket"):
        return cmd
    if (cmd.source or "") in PROTECTIVE_SOURCES:
        return cmd

    cap = _cap_shares()
    cap_shares = int(cap)
    qty = cmd.qty
    shares = cmd.shares
    if qty is None and shares is None:
        return cmd

    over_qty = qty is not None and float(qty) > cap
    over_shares = shares is not None and int(shares) > cap_shares
    if not over_qty and not over_shares:
        return cmd

    logger.warning(
        "IBKR_FORCE_ONE_SHARE: capping %s %s qty=%s shares=%s → %s "
        "(MASTER TEST GATE — flip IBKR_FORCE_ONE_SHARE=False to disable)",
        cmd.operation,
        (cmd.side or "").upper() or "?",
        qty,
        shares,
        cap_shares,
    )
    return replace(
        cmd,
        qty=cap if over_qty else qty,
        shares=cap_shares if over_shares else shares,
    )
