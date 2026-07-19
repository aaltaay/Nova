"""
Classify IBKR managed account ids as paper vs live.

IBKR paper/demo accounts are conventionally ``DU…`` / ``DF…``. Live individual
accounts are typically ``U…`` (not prefixed with D). Used as a hard pin so a
paper-configured Nova process never spends on a live Gateway session.
"""

from __future__ import annotations

from typing import Literal

BrokerAccountKind = Literal["paper", "live", "unknown", "mixed"]


def is_paper_account_id(account_id: str) -> bool:
    a = (account_id or "").strip().upper()
    if not a:
        return False
    # Paper / demo: DU (US paper), DF (FA paper), DU* variants.
    return a.startswith("DU") or a.startswith("DF")


def is_live_account_id(account_id: str) -> bool:
    a = (account_id or "").strip().upper()
    if not a or is_paper_account_id(a):
        return False
    # Common live individual / advisor prefixes.
    return a.startswith("U") or a.startswith("F") or a.startswith("I")


def classify_managed_accounts(account_ids: list[str] | tuple[str, ...] | None) -> BrokerAccountKind:
    """Return paper | live | mixed | unknown from IB ``managedAccounts()``."""
    ids = [str(a).strip() for a in (account_ids or []) if str(a).strip()]
    if not ids:
        return "unknown"
    papers = [a for a in ids if is_paper_account_id(a)]
    lives = [a for a in ids if is_live_account_id(a)]
    if papers and lives:
        return "mixed"
    if papers:
        return "paper"
    if lives:
        return "live"
    return "unknown"


def paper_mode_accounts_ok(kind: BrokerAccountKind) -> tuple[bool, str]:
    """When Nova targets paper Gateway, only pure paper accounts are allowed."""
    if kind == "paper":
        return True, ""
    if kind == "live":
        return False, (
            "Connected Gateway reports LIVE account id(s) while "
            "IBKR_GATEWAY_MODE=paper — refusing session (paper pin)"
        )
    if kind == "mixed":
        return False, (
            "Connected Gateway reports mixed paper+live accounts while "
            "IBKR_GATEWAY_MODE=paper — refusing session (paper pin)"
        )
    return False, (
        "Could not classify IBKR managedAccounts as paper while "
        "IBKR_GATEWAY_MODE=paper — refusing session (paper pin)"
    )
