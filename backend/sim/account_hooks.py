"""Practice-venue early-returns for ibkr.account and ibkr.orders -- keeps them under 400.

ADR 020: on Paper and Sim, ``/api/ibkr/account``, ``/api/ibkr/positions`` and
the orders endpoints answer from the venue's practice ledger
(``practice.broker.for_venue``), and every IBKR place / bracket / cancel is
refused in the venue's own words; on Live they fall through to IBKR. The
``*_if_sim`` names are kept for their callers; ``*_if_practice`` are the same
functions.
"""
from __future__ import annotations

from typing import Any


def practice_broker() -> Any | None:
    """The venue's practice broker on Paper / Sim, ``None`` on the IBKR door."""
    from sim.mode import is_practice_venue, venue

    if not is_practice_venue():
        return None
    from practice.broker import for_venue

    return for_venue(venue())


def practice_refusal(refusal: dict[str, Any]) -> dict[str, Any]:
    """A ``sim.guard`` refusal labelled with the practice venue that refused.

    Paper never places to IBKR any more than Sim does; only the words differ
    so the blotter names the venue the operator is actually on.
    """
    from constants_sim import DESK_PAPER_NO_IBKR_REASON, SIM_MODE_LABEL
    from sim.mode import venue

    current = venue()
    if current == SIM_MODE_LABEL:
        return refusal
    return {**refusal, "mode": current, "error": DESK_PAPER_NO_IBKR_REASON}


def positions_if_sim() -> list[dict[str, Any]] | None:
    broker = practice_broker()
    if broker is None:
        return None
    return broker.positions()


def summary_if_sim() -> dict[str, Any] | None:
    broker = practice_broker()
    if broker is None:
        return None
    return broker.account_summary()


positions_if_practice = positions_if_sim
summary_if_practice = summary_if_sim
