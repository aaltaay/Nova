"""Bounded Gateway attach retry ledger (ADR 021 decision 2).

Owner: this module (process-local, never persisted -- a restart is a new
episode on purpose). Read by ``gateway_heal.heal_status`` (merged into
``/api/ibkr/status.attach``) and by the diagnostics gateway row.

The dialer calls ``record_attempt`` every time it tried to attach to a
Gateway whose API port answered TCP but whose session did not reach READY,
then sleeps ``next_delay_sec()``. The schedule is ``IBKR_ATTACH_BACKOFF_SEC``
(1, 2, 5, 10, 30 s). After ``IBKR_ATTACH_MAX_ATTEMPTS_PER_WINDOW`` attempts
inside ``IBKR_ATTACH_WINDOW_SEC`` -- or as soon as the reason is one Nova can
never fix on its own (a pending Second Factor prompt, another API holding the
clientId, a paper login beside a live session) -- the stall is a **human
step**: the dialer polls politely every ``IBKR_ATTACH_HUMAN_STEP_POLL_SEC``
and the status says what it is waiting for. ``clear`` on READY.

Pure enough to test with an injected clock. No IB calls, no logging of
credentials.
"""
from __future__ import annotations

import time
from typing import Any

from constants_diagnostics import (
    IBKR_ATTACH_BACKOFF_SEC,
    IBKR_ATTACH_CAP_REASON,
    IBKR_ATTACH_HUMAN_STEP_POLL_SEC,
    IBKR_ATTACH_HUMAN_STEP_REASONS,
    IBKR_ATTACH_LEDGER_MAX,
    IBKR_ATTACH_MAX_ATTEMPTS_PER_WINDOW,
    IBKR_ATTACH_WINDOW_SEC,
)

_attempts: list[dict[str, Any]] = []
_human_step_reason: str | None = None
_cleared_at: float | None = None
_cleared_reason: str | None = None


def reset_for_tests() -> None:
    global _human_step_reason, _cleared_at, _cleared_reason
    _attempts.clear()
    _human_step_reason = None
    _cleared_at = None
    _cleared_reason = None


def classify_reason(reason: str) -> str:
    """``human_step`` for reasons Nova can never fix by retrying, else ``retry``."""
    return "human_step" if (reason or "").strip() in IBKR_ATTACH_HUMAN_STEP_REASONS else "retry"


def _in_window(now: float) -> list[dict[str, Any]]:
    floor = now - float(IBKR_ATTACH_WINDOW_SEC)
    return [row for row in _attempts if float(row["ts"]) >= floor]


def record_attempt(
    reason: str,
    *,
    port: int | None = None,
    detail: str | None = None,
    now: float | None = None,
) -> dict[str, Any]:
    """Append one attach attempt and (re)judge whether this is a human step."""
    global _human_step_reason
    ts = time.time() if now is None else float(now)
    reason = (reason or "unknown").strip() or "unknown"
    row: dict[str, Any] = {
        "ts": ts,
        "reason": reason,
        "port": port,
        "detail": detail,
        "attempt": len(_in_window(ts)) + 1,
    }
    _attempts.append(row)
    if len(_attempts) > IBKR_ATTACH_LEDGER_MAX:
        del _attempts[: len(_attempts) - IBKR_ATTACH_LEDGER_MAX]
    if classify_reason(reason) == "human_step":
        _human_step_reason = reason
    elif row["attempt"] >= IBKR_ATTACH_MAX_ATTEMPTS_PER_WINDOW:
        _human_step_reason = IBKR_ATTACH_CAP_REASON
    return dict(row)


def clear(*, reason: str = "ready", now: float | None = None) -> None:
    """The session reached READY (or the operator changed the door): new episode."""
    global _human_step_reason, _cleared_at, _cleared_reason
    _attempts.clear()
    _human_step_reason = None
    _cleared_at = time.time() if now is None else float(now)
    _cleared_reason = reason


def human_step() -> str | None:
    """The human-step reason, or None while Nova is still retrying on its own."""
    return _human_step_reason


def next_delay_sec(now: float | None = None) -> float:
    """Seconds the dialer should wait before the next attach attempt."""
    if _human_step_reason is not None:
        return float(IBKR_ATTACH_HUMAN_STEP_POLL_SEC)
    ts = time.time() if now is None else float(now)
    made = len(_in_window(ts))
    if made <= 0:
        return float(IBKR_ATTACH_BACKOFF_SEC[0])
    idx = min(made, len(IBKR_ATTACH_BACKOFF_SEC)) - 1
    return float(IBKR_ATTACH_BACKOFF_SEC[idx])


def status(now: float | None = None) -> dict[str, Any]:
    """Fields merged into ``/api/ibkr/status.attach`` and the diagnostics row."""
    ts = time.time() if now is None else float(now)
    in_window = _in_window(ts)
    last = _attempts[-1] if _attempts else None
    return {
        "attempts_in_window": len(in_window),
        "window_sec": float(IBKR_ATTACH_WINDOW_SEC),
        "max_attempts_per_window": int(IBKR_ATTACH_MAX_ATTEMPTS_PER_WINDOW),
        "backoff_sec": list(IBKR_ATTACH_BACKOFF_SEC),
        "last_attempt": dict(last) if last else None,
        "next_delay_sec": next_delay_sec(ts),
        "human_step": _human_step_reason,
        "human_step_poll_sec": float(IBKR_ATTACH_HUMAN_STEP_POLL_SEC),
        "cleared_at": _cleared_at,
        "cleared_reason": _cleared_reason,
        "recent": [dict(row) for row in _attempts],
    }
