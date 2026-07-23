"""
IBKR session readiness state machine (Nova-side, not raw socket status).

Raw ``IB.isConnected()`` only reports transport/TCP handshake state. It goes
True the moment ``connectAsync()`` completes — before Nova has validated the
managed-account kind or warmed the positions/completed-orders caches. Every
background task, discovery scanner, and detail-panel bridge that gates on
``ibkr.client.get_ib()`` used to go live the instant the socket connected,
which let lifespan-spawned tasks hit a still-synchronizing session (see
PROBLEM_LOG 2026-07-23).

This module tracks Nova's own opinion of readiness, in five states:
  DISCONNECTED   -- no session, or explicitly torn down
  CONNECTING     -- attempt_connect() in flight
  SYNCHRONIZING  -- transport connected, account/session validation running
  READY          -- account-kind accepted + positions/orders caches warm
  DEGRADED       -- was READY, transport dropped before a clean disconnect

Every transition *into* READY bumps ``generation`` — an incrementing int
callers can capture before starting IBKR work and compare afterward to
detect "the session I was using got torn down mid-call" (see
``ibkr.client.run_coro``). Generation only ever increases; it is not reset
by DEGRADED/DISCONNECTED so a stale comparison always stays stale.
"""
from __future__ import annotations

DISCONNECTED = "disconnected"
CONNECTING = "connecting"
SYNCHRONIZING = "synchronizing"
READY = "ready"
DEGRADED = "degraded"

_state: str = DISCONNECTED
_generation: int = 0


def state() -> str:
    return _state


def generation() -> int:
    return _generation


def is_ready() -> bool:
    return _state == READY


def set_connecting() -> None:
    global _state
    _state = CONNECTING


def set_synchronizing() -> None:
    global _state
    _state = SYNCHRONIZING


def set_ready() -> int:
    """Mark the session usable and bump the generation. Returns the new generation."""
    global _state, _generation
    _state = READY
    _generation += 1
    return _generation


def set_degraded() -> None:
    global _state
    _state = DEGRADED


def set_disconnected() -> None:
    global _state
    _state = DISCONNECTED


def reset_for_testing() -> None:
    """Test isolation only — production code never resets generation to 0."""
    global _state, _generation
    _state = DISCONNECTED
    _generation = 0
