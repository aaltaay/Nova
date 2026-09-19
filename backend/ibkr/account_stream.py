"""Ensure IBKR accountValue / updatePortfolio push is subscribed.

ib_async ``connectAsync`` already starts ``reqAccountUpdates`` when it knows
the account id. This is the defensive second call after earn_usable so a
multi-account or empty-account connect (or a 1101 data-lost restore) still
keeps ``accountValues()`` and ``portfolio()`` live.

Fire-and-forget on the wire: IB sends ``accountDownloadEnd`` only for the
first subscription on a connection, so awaiting it after connectAsync had
already subscribed waited the full timeout on every connect (live probe
2026-09-19: the re-subscribe never answered in 30s). Values still land in
ib_async's caches through updateAccountValue / updatePortfolio either way.
"""
from __future__ import annotations

import logging
from typing import Any

from ibkr.errors import describe_exc

logger = logging.getLogger(__name__)


async def ensure_account_updates(ib: Any | None = None) -> bool:
    """Subscribe account/portfolio push. Returns True when the request was sent."""
    if ib is None:
        from ibkr import client as _client

        ib = _client.get_ib()
    if ib is None:
        return False
    send = getattr(getattr(ib, "client", None), "reqAccountUpdates", None)
    if send is None:
        return False
    account = _first_managed_account(ib)
    try:
        send(True, account)
        logger.info("IBKR: account updates subscription sent (account=%s)", account or "*")
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
