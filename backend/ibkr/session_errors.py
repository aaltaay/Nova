"""Session-level IBKR errorEvent handler (G1/G4 capture-audit remediation).

Installed once per ``IB()`` instance from ``client.reconnect_loop`` after
READY. Covers connectivity (1100/1101/1102), data-farm notices
(2104/2106/2108), max-tickers (101), and delayed-data (10167). Scoped
tape/depth handlers remain for their own codes; this module owns
session-wide honesty flags that status/UI can read.

Handlers MUST NOT issue new IB requests (ib_async forbids it).
"""
from __future__ import annotations

import logging
import time
from typing import Any

from constants import (
    IBKR_ERROR_CONNECTIVITY_CODES,
    IBKR_ERROR_CONNECTIVITY_LOST,
    IBKR_ERROR_DATA_FARM_CODES,
    IBKR_ERROR_DELAYED_DATA_NOTICE,
    IBKR_ERROR_MAX_TICKERS,
)
from ibkr import session_state as _session

logger = logging.getLogger(__name__)

_error_hooked_ib_ids: set[int] = set()
_delayed_data = False
_data_farm_status: str | None = None
_data_farm_status_ts: float = 0.0
_max_tickers_hit = False
_max_tickers_ts: float = 0.0


def is_delayed_data() -> bool:
    return _delayed_data


def get_data_farm_status() -> dict[str, Any]:
    return {
        "status": _data_farm_status,
        "ts": _data_farm_status_ts or None,
    }


def max_tickers_hit() -> bool:
    return _max_tickers_hit


def reset_for_tests() -> None:
    """Clear module flags + hook set (unit tests only)."""
    global _delayed_data, _data_farm_status, _data_farm_status_ts
    global _max_tickers_hit, _max_tickers_ts
    _error_hooked_ib_ids.clear()
    _delayed_data = False
    _data_farm_status = None
    _data_farm_status_ts = 0.0
    _max_tickers_hit = False
    _max_tickers_ts = 0.0


def install_error_hook(ib: Any) -> None:
    if ib is None:
        return
    ib_id = id(ib)
    if ib_id in _error_hooked_ib_ids:
        return
    ib.errorEvent += _on_ib_error
    _error_hooked_ib_ids.add(ib_id)
    logger.info("IBKR session_errors: errorEvent hook installed")


def _on_ib_error(
    reqId: int,
    errorCode: int,
    errorString: str,
    contract: Any = None,
) -> None:
    global _delayed_data, _data_farm_status, _data_farm_status_ts
    global _max_tickers_hit, _max_tickers_ts

    code = int(errorCode)
    msg = (errorString or "").strip()

    if code == IBKR_ERROR_CONNECTIVITY_LOST:
        logger.error(
            "IBKR session_errors: connectivity lost (Error %s) — %s",
            code, msg or "no detail",
        )
        try:
            _session.set_degraded()
        except Exception:
            logger.debug("session_errors: set_degraded failed", exc_info=True)
        return

    if code in IBKR_ERROR_CONNECTIVITY_CODES:
        logger.info(
            "IBKR session_errors: connectivity notice (Error %s) — %s",
            code, msg or "no detail",
        )
        return

    if code in IBKR_ERROR_DATA_FARM_CODES:
        _data_farm_status = msg or f"farm code {code}"
        _data_farm_status_ts = time.time()
        logger.warning(
            "IBKR session_errors: data farm notice (Error %s) — %s",
            code, _data_farm_status,
        )
        return

    if code == IBKR_ERROR_MAX_TICKERS:
        _max_tickers_hit = True
        _max_tickers_ts = time.time()
        logger.error(
            "IBKR session_errors: max tickers reached (Error %s) — %s",
            code, msg or "capacity oversubscription",
        )
        try:
            from ibkr import scanner_l1 as _l1

            _l1.note_capacity_error(
                f"IBKR Error {code}: max tickers reached"
                + (f" — {msg}" if msg else "")
            )
        except Exception:
            logger.debug("session_errors: scanner_l1 capacity note failed", exc_info=True)
        return

    if code == IBKR_ERROR_DELAYED_DATA_NOTICE:
        _delayed_data = True
        logger.warning(
            "IBKR session_errors: delayed market data (Error %s) — %s",
            code, msg or "displaying delayed data",
        )
        return
