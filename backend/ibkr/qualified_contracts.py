"""Qualified Stock contracts reused across cold snapshot calls (an LRU, process memory).

``ibkr.discovery.snapshot_quotes`` qualifies a symbol once and reuses the contract, so the table
reprice loop does not pay ``qualifyContractsAsync`` every second for the same universe. A full
reconnect drops them (``ibkr.client``, D-024): a new ``IB()`` session owns its own contracts.
"""
from __future__ import annotations

import logging

from constants import IBKR_QUALIFIED_CONTRACTS_MAX

logger = logging.getLogger(__name__)

# Never rebound: ``ibkr.discovery`` and tests hold this same dict.
_qualified_contracts: dict[str, object] = {}


def qualified_contract_count() -> int:
    return len(_qualified_contracts)


def clear_qualified_contracts(*, reason: str = "") -> int:
    """Drop cached Stock contracts after a full reconnect (D-024)."""
    n = len(_qualified_contracts)
    _qualified_contracts.clear()
    if n:
        logger.info(
            "IBKR discovery: cleared %d qualified contracts (%s)",
            n,
            reason or "unspecified",
        )
    return n


def remember_qualified_contract(symbol: str, contract: object) -> None:
    """LRU-insert a qualified contract. Oldest keys drop past the cap."""
    sym = (symbol or "").strip().upper()
    if not sym or contract is None:
        return
    _qualified_contracts.pop(sym, None)
    _qualified_contracts[sym] = contract
    max_n = max(1, int(IBKR_QUALIFIED_CONTRACTS_MAX))
    while len(_qualified_contracts) > max_n:
        _qualified_contracts.pop(next(iter(_qualified_contracts)))


def take_qualified_contract(symbol: str):
    """Return a cached contract and mark it most-recently used."""
    contract = _qualified_contracts.pop(symbol, None)
    if contract is None:
        return None
    _qualified_contracts[symbol] = contract
    return contract
