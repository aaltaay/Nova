"""
Classify IBKR managed account ids as paper vs live.

IBKR paper/demo accounts are conventionally ``DU…`` / ``DF…``. Live individual
accounts are typically ``U…`` (not prefixed with D). Used so a connected
session's account kind must match the mode being established (paper or live).

Also owns post-connect accept helpers (read managedAccounts + kind match)
so ``ibkr.client`` stays under the file-size limit.

Spend authority stays in ``ibkr.safety`` -- classification/accept only.
"""

from __future__ import annotations

import logging
from typing import Any, Literal

logger = logging.getLogger(__name__)

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


def read_managed_account_ids(ib: Any) -> list[str]:
    """Normalize ib_async managedAccounts() to a list of account id strings."""
    try:
        raw = ib.managedAccounts()
    except Exception:  # maintainer: allow-swallow [] classifies as unknown and the session is refused (fail-closed)
        logger.warning("IBKR: managedAccounts() failed", exc_info=True)
        return []
    if raw is None:
        return []
    if isinstance(raw, str):
        return [p.strip() for p in raw.replace(";", ",").split(",") if p.strip()]
    if isinstance(raw, (list, tuple)):
        return [str(a).strip() for a in raw if str(a).strip()]
    s = str(raw).strip()
    return [s] if s else []


def _follow_paper_account_if_needed(kind: BrokerAccountKind, mode_label: str) -> str:
    """If Gateway is paper and Nova asked live, persist paper and keep the socket.

    Safe demote only -- never auto-promote a live account into live mode.
    Unattended attach (no Live click in flight) may follow a DU/DF login on
    4001 so scanners work. An explicit Live click must not follow paper
    (ADR 013) -- that was the capsule snap-back.
    """
    requested = "live" if str(mode_label).strip().lower() == "live" else "paper"
    if kind != "paper" or requested != "live":
        return requested
    from ibkr import gateway_heal as _heal
    from ibkr.mode_identity import follow_paper_allowed

    if not follow_paper_allowed(
        requested_mode=requested,
        intentional=_heal.intentional_mode(),
    ):
        from ibkr.gateway_trail import append_event as _trail

        _trail(
            actor="ibkr",
            event="refused_follow_paper",
            requested="live",
            kind_after="paper",
            switched=False,
            note="Live click in flight -- will not attach as paper",
        )
        logger.warning(
            "IBKR: paper account on a live request while Live click is in "
            "flight -- not following paper (ADR 013)"
        )
        return requested

    _heal.persist_gateway_mode("paper")
    _heal.apply_runtime_gateway_mode("paper")
    _heal.clear_intentional_mode(reason="follow paper account")
    from ibkr.gateway_trail import append_event as _trail

    _trail(
        actor="ibkr",
        event="follow_paper",
        requested="live",
        kind_after="paper",
        switched=True,
        note="unattended attach as paper (no Live click in flight)",
    )
    logger.warning(
        "IBKR: Gateway managedAccounts are paper while Nova asked live -- "
        "attaching as paper on this socket (spend gates unchanged)"
    )
    return "paper"


def accept_connected_session(ib: Any, mode_label: str) -> tuple[bool, str]:
    """
    Classify managedAccounts; require kind to match ``mode_label``.
    Paper-on-live-request follows to paper (keeps TCP) unless a Live click
    is in flight. Live-on-paper still refuses. Updates
    ``client._broker_account_kind``. Returns (ok, reason).
    On failure caller must disconnect.
    """
    from ibkr import client as _client

    ids = read_managed_account_ids(ib)
    kind = classify_managed_accounts(ids)
    _client._broker_account_kind = kind
    _client._managed_account_ids = list(ids)
    effective = _follow_paper_account_if_needed(kind, mode_label)
    ok, reason = accounts_match_mode(kind, effective)
    from ibkr.gateway_trail import append_event as _trail

    if not ok:
        _trail(
            actor="ibkr",
            event="refused",
            requested=effective,
            kind_after=kind,
            switched=False,
            note=(reason or "")[:240],
        )
        logger.error(
            "IBKR: refusing session -- %s (accounts=%s mode=%s)",
            reason,
            ids,
            effective,
        )
        return False, reason
    _trail(
        actor="ibkr",
        event="attached",
        requested=effective,
        kind_after=kind,
        switched=True,
    )
    logger.info(
        "IBKR: session accounts kind=%s ids=%s mode=%s",
        kind,
        ids,
        effective,
    )
    return True, ""
