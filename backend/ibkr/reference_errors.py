"""IBKR errors on reference contracts: futures, indexes, forex, crypto (ADR 053).

Nova trades and streams only stocks. A ``FUT`` / ``CONTFUT`` / ``IND`` / ``CASH`` / ``CRYPTO`` contract is asked
for by a read-only reference page (the Market page's tiles, the Cryptos page's listing check), so an error on one
belongs to that page's tile -- never to the stock session. ``session_errors`` hands such errors here before any of
its session flags can be set: a 10089 ("requires an additional subscription") on ES must not move the stock desk
to delayed quotes, and a 101 on a snapshot must not teach the scanner's line planner a cap.

Owner: this module; in memory only (the last error per contract, newest wins). Readers ask by ``conId`` or by
``(secType, symbol)``.
"""
from __future__ import annotations

import threading
import time
from typing import Any

REFERENCE_SEC_TYPES = frozenset({"FUT", "CONTFUT", "IND", "CASH", "CRYPTO"})
_MAX_KEPT = 256

_lock = threading.Lock()
_by_key: dict[str, dict[str, Any]] = {}


def is_reference(contract: Any) -> bool:
    """True for a contract Nova only ever reads for a reference page (never a stock)."""
    return str(getattr(contract, "secType", "") or "").upper() in REFERENCE_SEC_TYPES


def _keys(contract: Any) -> list[str]:
    keys = []
    con_id = getattr(contract, "conId", 0) or 0
    if con_id:
        keys.append(f"id:{int(con_id)}")
    sec = str(getattr(contract, "secType", "") or "").upper()
    sym = str(getattr(contract, "symbol", "") or "").upper()
    if sym:
        keys.append(f"sym:{sec}:{sym}")
    return keys


def note(req_id: int, code: int, message: str, contract: Any, now: float | None = None) -> None:
    """Record IBKR's error for this reference contract (called from the errorEvent hook: no IB requests here)."""
    entry = {"req_id": int(req_id), "code": int(code), "message": (message or "").strip(),
             "at": time.time() if now is None else float(now)}
    with _lock:
        for key in _keys(contract):
            _by_key[key] = entry
        if len(_by_key) > _MAX_KEPT:
            for key in sorted(_by_key, key=lambda k: _by_key[k]["at"])[: len(_by_key) - _MAX_KEPT]:
                del _by_key[key]


def last_error(*, con_id: int | None = None, sec_type: str | None = None, symbol: str | None = None,
               since: float | None = None) -> dict[str, Any] | None:
    """The newest error recorded for the contract (by conId first, else secType + symbol), at or after ``since``."""
    keys = []
    if con_id:
        keys.append(f"id:{int(con_id)}")
    if sec_type and symbol:
        keys.append(f"sym:{sec_type.upper()}:{symbol.upper()}")
    with _lock:
        found = [_by_key[k] for k in keys if k in _by_key]
    if not found:
        return None
    best = max(found, key=lambda e: e["at"])
    if since is not None and best["at"] < since:
        return None
    return dict(best)


def describe(entry: dict[str, Any] | None) -> str | None:
    """"10089: Requested market data requires additional subscription" -- IBKR's code, then its words."""
    if not entry:
        return None
    return f"{entry['code']}: {entry['message']}"[:200] if entry.get("message") else str(entry["code"])


def reset_for_tests() -> None:
    with _lock:
        _by_key.clear()
