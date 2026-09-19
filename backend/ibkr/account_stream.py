"""Ensure IBKR accountValue / updatePortfolio push is subscribed.

ib_async ``connectAsync`` already starts ``reqAccountUpdates`` when it knows
the account id. This is the defensive second call after earn_usable so a
multi-account or empty-account connect still keeps ``accountValues()`` and
``portfolio()`` live. Singleton request -- safe to call again.
"""
from __future__ import annotations

import inspect
import logging
from typing import Any

from ibkr.errors import describe_exc
from ibkr.ib_await import await_ib_request

logger = logging.getLogger(__name__)


async def ensure_account_updates(ib: Any | None = None) -> bool:
    """Subscribe account/portfolio push. Returns True when the request was sent."""
    if ib is None:
        from ibkr import client as _client

        ib = _client.get_ib()
    if ib is None:
        return False
    req = getattr(ib, "reqAccountUpdatesAsync", None)
    if req is None:
        return False
    account = _first_managed_account(ib)
    try:
        from constants_ibkr import IBKR_ACCOUNT_UPDATES_TIMEOUT_SEC

        result = req(account)
        if inspect.isawaitable(result):
            await await_ib_request(
                result,
                timeout=float(IBKR_ACCOUNT_UPDATES_TIMEOUT_SEC),
            )
        logger.info("IBKR: account updates subscription live (account=%s)", account or "*")
        return True
    except Exception as exc:
        logger.warning(
            "IBKR: account updates subscribe failed (cache reads still used): %s",
            describe_exc(exc),
        )
        return False


def _first_managed_account(ib: Any) -> str:
    managed = getattr(ib, "managedAccounts", None)
    if not callable(managed):
        return ""
    try:
        accs = managed()
    except Exception:
        return ""
    if not accs:
        return ""
    return str(accs[0] or "")
