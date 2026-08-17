"""Session-level IBKR errorEvent handler (G1/G4 + usable-session SoT).

Installed once per ``IB()`` instance from ``client`` after READY. Covers
connectivity (1100/1101/1102), data-farm notices (2104/2106/2108),
max-tickers (101), delayed-data (10167), and MD-subscription-required (10089).

Handlers MUST NOT issue new IB requests (ib_async forbids it). Connectivity
codes only observe + classify + enqueue; ``reconnect_loop`` acts via
``earn_usable`` / force-reconnect. Error 10089 sets a flag;
``client.maybe_fallback_to_delayed_market_data`` applies ``reqMarketDataType(3)``.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Literal

from constants import (
    IBKR_ERROR_CONNECTIVITY_CODES,
    IBKR_ERROR_CONNECTIVITY_LOST,
    IBKR_ERROR_CONNECTIVITY_RESTORED_DATA_KEPT,
    IBKR_ERROR_CONNECTIVITY_RESTORED_DATA_LOST,
    IBKR_ERROR_DATA_FARM_CODES,
    IBKR_ERROR_DELAYED_DATA_NOTICE,
    IBKR_ERROR_MAX_TICKERS,
    IBKR_ERROR_MD_REQUIRES_SUBSCRIPTION,
)
from ibkr import session_state as _session

logger = logging.getLogger(__name__)

RestoreKind = Literal["data_lost", "data_kept"]

_error_hooked_ib_ids: set[int] = set()
_delayed_data = False
# True after Error 10089 — live API MD not entitled on this session (paper
# without shared live subscriptions). Client should reqMarketDataType(delayed).
_live_md_blocked = False
_data_farm_status: str | None = None
_data_farm_status_ts: float = 0.0
_max_tickers_hit = False
_max_tickers_ts: float = 0.0

_unusable_since: float | None = None
_last_connectivity_code: int | None = None
_last_connectivity_ts: float = 0.0
_restore_pending: RestoreKind | None = None


def is_delayed_data() -> bool:
    return _delayed_data


def live_market_data_blocked() -> bool:
    """True when IB rejected live API quotes (Error 10089) this session."""
    return _live_md_blocked


def get_data_farm_status() -> dict[str, Any]:
    return {
        "status": _data_farm_status,
        "ts": _data_farm_status_ts or None,
    }


def max_tickers_hit() -> bool:
    return _max_tickers_hit


def unusable_since() -> float | None:
    return _unusable_since


def last_connectivity_code() -> int | None:
    return _last_connectivity_code


def last_connectivity_ts() -> float | None:
    return _last_connectivity_ts or None


def peek_restore_pending() -> RestoreKind | None:
    return _restore_pending


def take_restore_pending() -> RestoreKind | None:
    """Consume the 1101/1102 restore flag (one-shot for reconnect_loop)."""
    global _restore_pending
    kind = _restore_pending
    _restore_pending = None
    return kind


def clear_unusable_stamp() -> None:
    """Clear watchdog stamp after a successful earn_usable."""
    global _unusable_since
    _unusable_since = None


def stamp_unusable(*, code: int | None = None) -> None:
    """Mark session unusable for the stuck-socket watchdog (idempotent ts)."""
    global _unusable_since, _last_connectivity_code, _last_connectivity_ts
    now = time.time()
    first = _unusable_since is None
    if first:
        _unusable_since = now
    if code is not None:
        _last_connectivity_code = int(code)
        _last_connectivity_ts = now
    if first:
        try:
            from observability import capture_session_unusable

            capture_session_unusable(code=code)
        except Exception:
            logger.debug("session_errors: session_unusable capture skipped", exc_info=True)


def reset_session_md_flags() -> None:
    """Clear delayed / live-MD-blocked flags (call on READY before req type 1)."""
    global _delayed_data, _live_md_blocked
    _delayed_data = False
    _live_md_blocked = False


def reset_for_tests() -> None:
    """Clear module flags + hook set (unit tests only)."""
    global _delayed_data, _live_md_blocked, _data_farm_status, _data_farm_status_ts
    global _max_tickers_hit, _max_tickers_ts
    global _unusable_since, _last_connectivity_code, _last_connectivity_ts
    global _restore_pending
    _error_hooked_ib_ids.clear()
    _delayed_data = False
    _live_md_blocked = False
    _data_farm_status = None
    _data_farm_status_ts = 0.0
    _max_tickers_hit = False
    _max_tickers_ts = 0.0
    _unusable_since = None
    _last_connectivity_code = None
    _last_connectivity_ts = 0.0
    _restore_pending = None


def install_error_hook(ib: Any) -> None:
    if ib is None:
        return
    ib_id = id(ib)
    if ib_id in _error_hooked_ib_ids:
        return
    ib.errorEvent += _on_ib_error
    _error_hooked_ib_ids.add(ib_id)
    logger.info("IBKR session_errors: errorEvent hook installed")


def _wake_reconnect() -> None:
    try:
        from ibkr.client import wake_reconnect_loop

        wake_reconnect_loop()
    except Exception:
        logger.debug("session_errors: wake_reconnect_loop failed", exc_info=True)


def _publish_reason(reason: str) -> None:
    try:
        from ibkr.client import set_session_reason

        set_session_reason(reason)
    except Exception:
        logger.debug("session_errors: set_session_reason failed", exc_info=True)


def _on_ib_error(
    reqId: int,
    errorCode: int,
    errorString: str,
    contract: Any = None,
) -> None:
    global _delayed_data, _live_md_blocked, _data_farm_status, _data_farm_status_ts
    global _max_tickers_hit, _max_tickers_ts
    global _restore_pending, _last_connectivity_code, _last_connectivity_ts

    code = int(errorCode)
    msg = (errorString or "").strip()
    now = time.time()

    if code == IBKR_ERROR_CONNECTIVITY_LOST:
        # WARNING: expected Gateway churn; ops-once Sentry via stamp_unusable.
        logger.warning(
            "IBKR session_errors: connectivity lost (Error %s) — %s",
            code, msg or "no detail",
        )
        _last_connectivity_code = code
        _last_connectivity_ts = now
        _restore_pending = None
        stamp_unusable(code=code)
        try:
            _session.set_degraded()
        except Exception:
            logger.debug("session_errors: set_degraded failed", exc_info=True)
        _publish_reason("connectivity_lost")
        _wake_reconnect()
        return

    if code == IBKR_ERROR_CONNECTIVITY_RESTORED_DATA_LOST:
        logger.info(
            "IBKR session_errors: connectivity restored data lost (Error %s) — %s",
            code, msg or "no detail",
        )
        _last_connectivity_code = code
        _last_connectivity_ts = now
        _restore_pending = "data_lost"
        _publish_reason("connectivity_data_lost")
        _wake_reconnect()
        return

    if code == IBKR_ERROR_CONNECTIVITY_RESTORED_DATA_KEPT:
        logger.info(
            "IBKR session_errors: connectivity restored data kept (Error %s) — %s",
            code, msg or "no detail",
        )
        _last_connectivity_code = code
        _last_connectivity_ts = now
        _restore_pending = "data_kept"
        _publish_reason("connectivity_restored")
        _wake_reconnect()
        return

    if code in IBKR_ERROR_CONNECTIVITY_CODES:
        # Named 1100/1101/1102 handled above; keep a defensive log for drift.
        logger.info(
            "IBKR session_errors: connectivity notice (Error %s) — %s",
            code, msg or "no detail",
        )
        _wake_reconnect()
        return

    if code in IBKR_ERROR_DATA_FARM_CODES:
        _data_farm_status = msg or f"farm code {code}"
        _data_farm_status_ts = now
        logger.warning(
            "IBKR session_errors: data farm notice (Error %s) — %s",
            code, _data_farm_status,
        )
        return

    if code == IBKR_ERROR_MAX_TICKERS:
        _max_tickers_hit = True
        _max_tickers_ts = now
        # WARNING locally + one fingerprinted Sentry ops-once (avoids ERROR log flood).
        logger.warning(
            "IBKR session_errors: max tickers reached (Error %s) — %s",
            code, msg or "capacity oversubscription",
        )
        try:
            from observability import capture_max_tickers

            capture_max_tickers(detail=msg or "")
        except Exception:
            logger.debug("session_errors: max_tickers capture skipped", exc_info=True)
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

    if code == IBKR_ERROR_MD_REQUIRES_SUBSCRIPTION:
        _live_md_blocked = True
        _delayed_data = True
        logger.warning(
            "IBKR session_errors: live API market data not entitled (Error %s) — "
            "will fall back to delayed; share live MD with paper in Account "
            "Management if you pay for live. %s",
            code, msg or "",
        )
        return
