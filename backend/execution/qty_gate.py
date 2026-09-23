"""MASTER TEST QTY GATE -- Live sends at most ``IBKR_FORCE_ONE_SHARE_QTY`` shares.

INTENTIONAL safety clamp (see ``IBKR_FORCE_ONE_SHARE`` in ``constants_ibkr.py``).
Not a sizing bug. Flip the constant to False to restore normal quantities; do
not remove this module silently.

History: until 2026-09-22 the gate forced every order to exactly one share. The
operator then made it a cap of 10 on every venue, and the same day settled #444
(option 1): the cap binds the **Live** venue only -- the one that places to IBKR
with real money -- at one share by default, so a fat-fingered size can never
reach the real account. Paper and Sim are Nova's practice accounts (fake money,
buying power enforced), so they send the size asked. The names stay so the
execution record's ``forced_one_share`` stamp and its readers are unchanged.

The clamp never touches a protective order (``flatten`` / ``kill`` /
``cancel_working``): those size themselves from the held position to get the
account flat. Clamping them made an Emergency KILL sell 1 share of a 2-share
position and report success (QA R6, 2026-09-22); AGENTS.md sec. 5 says a desk
must always be able to get flat.
"""
from __future__ import annotations

import logging
import os
from dataclasses import replace

from constants import IBKR_FORCE_ONE_SHARE, IBKR_FORCE_ONE_SHARE_QTY, IBKR_QTY_CAP_ENV
from execution.models import ExecutionCommand
from ibkr.safety import PROTECTIVE_SOURCES

logger = logging.getLogger(__name__)

__all__ = ["apply_force_one_share", "live_cap_refusal", "qty_cap"]

_CAPPED_OPERATIONS = ("place", "bracket")


def _cap_shares() -> float:
    """The one place the Live cap comes from: ``IBKR_QTY_CAP`` in the desk .env when it
    is a whole number >= 1, else the ``IBKR_FORCE_ONE_SHARE_QTY`` default. Everything
    else -- the clamp, the IBKR send check, ``/api/ibkr/status`` ``qty_cap``, the
    ticket's copy -- reads this."""
    raw = (os.environ.get(IBKR_QTY_CAP_ENV) or "").strip()
    if raw:
        try:
            value = float(raw)
            if value >= 1:
                return float(int(value))
        except ValueError:  # maintainer: allow-swallow falls through to the warning below
            pass
        logger.warning("%s=%r is not a whole number >= 1; using the default %s",
                       IBKR_QTY_CAP_ENV, raw, IBKR_FORCE_ONE_SHARE_QTY)
    return float(IBKR_FORCE_ONE_SHARE_QTY)


def _practice_venue() -> bool:
    """Paper or Sim. A venue that cannot be read counts as Live: the cap fails closed."""
    try:
        from sim.mode import is_practice_venue

        return is_practice_venue()
    except Exception:
        logger.exception("qty gate: desk venue unreadable -- applying the Live cap")
        return False


def _exempt(cmd: ExecutionCommand) -> bool:
    """Cancel / replace (replace reuses the open order's qty) and every protective source."""
    return cmd.operation not in _CAPPED_OPERATIONS or (cmd.source or "") in PROTECTIVE_SOURCES


def qty_cap() -> float | None:
    """The cap in shares on the desk's venue (what the ticket states): Live's while the
    gate is on, None on Paper and Sim or with the gate off."""
    if not IBKR_FORCE_ONE_SHARE or _practice_venue():
        return None
    return _cap_shares()


def apply_force_one_share(cmd: ExecutionCommand) -> ExecutionCommand:
    """Return ``cmd`` with place/bracket qty+shares capped on the Live venue.

    Paper and Sim pass through as asked, and so does every exempt command
    (cancel, replace, a protective flatten that closes the whole position).
    """
    if _exempt(cmd):
        return cmd
    cap = qty_cap()
    if cap is None:
        return cmd

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
        "IBKR_FORCE_ONE_SHARE: capping Live %s %s qty=%s shares=%s → %s "
        "(MASTER TEST GATE — IBKR_QTY_CAP in .env changes it)",
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


def live_cap_refusal(cmd: ExecutionCommand, shares: float | None) -> str | None:
    """The IBKR send's own check: why ``shares`` may not go to IBKR, or None.

    ``apply_force_one_share`` already cut the size on Live. This is the last
    word at the IBKR door, and it refuses rather than guesses: a size can
    still arrive above the cap when the venue changed from Paper to Live after
    the clamp ran, or when a bracket with no size is sized at the send from
    strategy risk. No venue check -- whatever reaches the IBKR send is real.
    """
    if not IBKR_FORCE_ONE_SHARE or _exempt(cmd) or shares is None:
        return None
    cap = _cap_shares()
    if float(shares) <= cap:
        return None
    return (
        f"Live sends at most {int(cap)} share{'s' if cap != 1 else ''} per order "
        f"({float(shares):g} asked) -- the test quantity gate; "
        f"{IBKR_QTY_CAP_ENV} in .env changes it"
    )
