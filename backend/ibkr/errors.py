"""IBKR exception formatting — never emit empty error strings to logs/Sentry."""
from __future__ import annotations

import asyncio
from concurrent.futures import TimeoutError as FuturesTimeoutError


class IbkrDiscoveryError(RuntimeError):
    """Scanner/snapshot transport failure — not the same as an empty market."""


class IbkrScannerSlotExhaustedError(IbkrDiscoveryError):
    """IBKR Error 322 — no free scanner subscription slot for this request.

    Raised instead of silently returning an empty result: with
    ``RaiseRequestErrors=False`` (ib_async default) the request future
    resolves to ``[]`` on this error with no exception, which used to look
    identical to "market genuinely has 0 rows" (see PROBLEM_LOG 2026-07-23
    IBKR scanner subscription leak). Callers should recover leaked slots and
    retry once — see ``ibkr.discovery.recover_scanner_slots``.
    """


class IbkrAccountError(RuntimeError):
    """Positions/orders read failure — never disguise as a flat/empty account."""


class StaleIbkrSessionError(RuntimeError):
    """run_coro() result arrived from a connection generation that already
    disconnected/reconnected — the caller's IBKR session moved on mid-call,
    so the result must not be applied (see ibkr/session_state.py)."""


def describe_exc(exc: BaseException) -> str:
    """Human-readable exception text; falls back to type name when ``str(exc)`` is empty."""
    raw = str(exc).strip()
    name = type(exc).__name__
    if not raw:
        return name
    if raw.startswith(name):
        return raw
    return f"{name}: {raw}"


def is_transient_historical_failure(exc: BaseException) -> bool:
    """True for timeouts / cancelled historical queries (IBKR Error 162 family)."""
    if isinstance(exc, (TimeoutError, FuturesTimeoutError, asyncio.TimeoutError)):
        return True
    text = f"{type(exc).__name__} {exc}".lower()
    needles = (
        "timeout",
        "timed out",
        "cancelled",
        "canceled",
        "error 162",
        "historical data query cancelled",
        "pacing violation",
        "duplicate",
    )
    return any(n in text for n in needles)


def bars_failure_detail(symbol: str, exc: BaseException) -> str:
    """User-facing 503 detail for chart bars failures."""
    desc = describe_exc(exc)
    if is_transient_historical_failure(exc):
        return (
            f"IBKR historical bars unavailable for {symbol} "
            f"(request timed out or was cancelled by Gateway). "
            f"Retry shortly — Nova will not fall back to Alpaca. ({desc})"
        )
    return f"IBKR chart bars failed for {symbol}: {desc}"
