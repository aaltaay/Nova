"""HOD active-set refresh hooks after scanner roster commits (audit G8)."""
from __future__ import annotations

import logging

from ibkr import scanner_session as _ss

logger = logging.getLogger(__name__)


def on_hod_roster_commit(table: str) -> None:
    """After a HOD-eligible roster write: rebuild active set + wake L1.

    Losers and shadow commits are ignored -- they are not HOD admission inputs.
    """
    table_key = (table or "").strip().lower()
    if table_key not in (
        _ss.TABLE_GAPPERS,
        _ss.TABLE_GAINERS,
        _ss.TABLE_AFTERHOURS,
    ):
        return
    try:
        import ibkr_bridge as _bridge

        _bridge.refresh_hod_active_set()
    except Exception:
        logger.exception("HOD roster commit: refresh_hod_active_set failed (%s)", table_key)
    try:
        from ibkr import scanner_l1 as _scanner_l1

        _scanner_l1.request_reconcile()
    except Exception:
        logger.exception("HOD roster commit: request_reconcile failed (%s)", table_key)
