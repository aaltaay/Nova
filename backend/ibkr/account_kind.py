"""
Classify IBKR managed account ids as paper vs live.

IBKR paper/demo accounts are conventionally ``DU…`` / ``DF…``. Live individual
accounts are typically ``U…`` (not prefixed with D). Used so a connected
session's account kind must match the mode being established (paper or live).

Spend authority stays in ``ibkr.safety`` — this module only classifies ids.
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


def accounts_match_mode(kind: BrokerAccountKind, mode_label: str) -> tuple[bool, str]:
    """True only when the classified account kind matches the mode being established."""
    mode = "live" if str(mode_label).strip().lower() == "live" else "paper"
    if kind == mode:
        return True, ""
    if kind == "mixed":
        return False, (
            f"Connected Gateway reports mixed paper+live accounts while "
            f"establishing {mode} mode — refusing session"
        )
    if kind == "unknown":
        return False, (
            f"Could not classify IBKR managedAccounts while "
            f"establishing {mode} mode — refusing session"
        )
    return False, (
        f"Connected Gateway reports {kind.upper()} account id(s) while "
        f"establishing {mode} mode — refusing session"
    )


def paper_mode_accounts_ok(kind: BrokerAccountKind) -> tuple[bool, str]:
    """Backward-compat wrapper — prefer ``accounts_match_mode``."""
    return accounts_match_mode(kind, "paper")
