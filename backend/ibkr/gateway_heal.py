"""
Self-heal IBKR Gateway port mismatch — **bidirectional auto-detect**.

When the preferred Gateway port (from IBKR_GATEWAY_MODE) is hard-refused but
the alternate port accepts, flip runtime mode to the reachable port, persist
``.env``, and reconnect. Account kind must match the mode being established
(``account_kind.accounts_match_mode``).

Heal fires only on hard **refused** (not ambiguous timeout / Error 326).

Intentional user switches (Stock View Paper/Live capsule) set a **sticky**
requested mode that blocks silent heal until the user switches again or the
requested mode actually connects — never a fixed timer.

Never unlocks orders / live confirmation — safety.py remains SSOT for spend.
Never auto-logins Gateway — if **neither** port is reachable, stay disconnected
and warn (loud).
"""
from __future__ import annotations

import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Literal

from constants import (
    IBKR_GATEWAY_SELF_HEAL_DEFAULT,
    IBKR_LIVE_PORT,
    IBKR_PAPER_PORT,
)

logger = logging.getLogger(__name__)

GatewayMode = Literal["paper", "live"]
ConnectResult = Literal["connected", "failed", "healed", "idle"]

_GATEWAY_MODE_LINE = re.compile(
    r"^\s*IBKR_GATEWAY_MODE\s*=\s*\S+",
    re.IGNORECASE,
)

# Last successful heal (for /api/ibkr/status); cleared on preferred connect.
_last_heal: dict[str, Any] | None = None

# Sticky user-initiated mode request (Paper/Live capsule). Blocks self-heal
# while unresolved — survives past the old ~18s suppress window.
_intentional_mode: GatewayMode | None = None
_intentional_at: float = 0.0

# Last connect outcome (status-visible; survives page reload).
_last_result: ConnectResult = "idle"
_last_reason: str | None = None


def self_heal_enabled() -> bool:
    raw = os.environ.get("IBKR_GATEWAY_SELF_HEAL")
    if raw is None:
        return IBKR_GATEWAY_SELF_HEAL_DEFAULT
    return raw.strip().lower() in ("1", "true", "yes")


def alternate_mode(mode: str) -> GatewayMode:
    return "paper" if mode == "live" else "live"


def heal_target_allowed(*, from_mode: str, to_mode: str) -> bool:
    """True when from/to are opposite paper/live modes (bidirectional heal)."""
    if from_mode == to_mode:
        return False
    return {from_mode, to_mode} == {"paper", "live"}


def set_intentional_mode(mode: GatewayMode) -> None:
    """Record a user-initiated Paper↔Live switch (sticky until resolved)."""
    global _intentional_mode, _intentional_at
    _intentional_mode = mode
    _intentional_at = time.time()
    logger.info("IBKR: intentional gateway mode request → %s (sticky)", mode)


def clear_intentional_mode(*, reason: str = "") -> None:
    global _intentional_mode, _intentional_at
    if _intentional_mode is None:
        return
    logger.info(
        "IBKR: clearing intentional mode %s (%s)",
        _intentional_mode,
        reason or "resolved",
    )
    _intentional_mode = None
    _intentional_at = 0.0


def intentional_mode() -> GatewayMode | None:
    return _intentional_mode


def self_heal_suppressed() -> bool:
    """True while an unresolved intentional switch blocks automatic heal."""
    return _intentional_mode is not None


def suppress_self_heal(seconds: float) -> None:
    """
    Backward-compat shim for tests/callers that still pass a duration.

    Duration is ignored — intentional Live/Paper intent is sticky. Prefer
    ``set_intentional_mode`` from product code.
    """
    del seconds  # sticky; duration no longer applies
    # Default sticky to live when only suppress is called (legacy tests).
    if _intentional_mode is None:
        set_intentional_mode("live")


def port_for_mode(mode: str) -> int:
    if mode == "live":
        return int(os.environ.get("IBKR_LIVE_PORT", str(IBKR_LIVE_PORT)))
    return int(os.environ.get("IBKR_PAPER_PORT", str(IBKR_PAPER_PORT)))


def classify_connect_failure(exc: BaseException | None, *, timed_out: bool) -> str:
    """Return refused | timeout | other for heal gating."""
    if timed_out:
        return "timeout"
    if exc is None:
        return "other"
    if isinstance(exc, ConnectionRefusedError):
        return "refused"
    msg = str(exc).lower()
    name = type(exc).__name__.lower()
    if "10061" in msg or "refused" in msg or "refused" in name:
        return "refused"
    if "timed out" in msg or "timeout" in msg:
        return "timeout"
    return "other"


def apply_runtime_gateway_mode(mode: GatewayMode) -> None:
    os.environ["IBKR_GATEWAY_MODE"] = mode


def persist_gateway_mode(mode: GatewayMode, env_path: Path | None = None) -> bool:
    """Rewrite IBKR_GATEWAY_MODE in .env (or append). Returns True on write."""
    from paths import env_file_path

    path = env_path if env_path is not None else env_file_path()
    try:
        text = path.read_text(encoding="utf-8") if path.is_file() else ""
        lines = text.splitlines(keepends=True)
        found = False
        out: list[str] = []
        for line in lines:
            bare = line.lstrip("\ufeff")
            if _GATEWAY_MODE_LINE.match(bare.rstrip("\r\n")):
                nl = "\r\n" if line.endswith("\r\n") else "\n"
                out.append(f"IBKR_GATEWAY_MODE={mode}{nl}")
                found = True
            else:
                out.append(line)
        if not found:
            if out and not out[-1].endswith(("\n", "\r")):
                out[-1] = out[-1] + "\n"
            out.append(f"IBKR_GATEWAY_MODE={mode}\n")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(out), encoding="utf-8")
        return True
    except OSError:
        logger.warning(
            "IBKR: could not persist IBKR_GATEWAY_MODE=%s to %s",
            mode,
            path,
            exc_info=True,
        )
        return False


def record_heal(
    *,
    from_mode: str,
    to_mode: GatewayMode,
    reason: str,
    preferred_port: int,
    healed_port: int,
    persisted: bool,
) -> dict[str, Any]:
    global _last_heal, _last_result, _last_reason
    _last_heal = {
        "from_mode": from_mode,
        "to_mode": to_mode,
        "reason": reason,
        "preferred_port": preferred_port,
        "healed_port": healed_port,
        "persisted": persisted,
    }
    _last_result = "healed"
    _last_reason = reason
    clear_intentional_mode(reason=f"self-healed to {to_mode}")
    logger.warning(
        "IBKR: self-healed gateway_mode %s→%s (preferred port %s failed: %s; "
        "connected on %s). Account display follows the logged-in Gateway; "
        "orders still gated by safety.py. persisted=%s",
        from_mode,
        to_mode,
        preferred_port,
        reason,
        healed_port,
        persisted,
    )
    return dict(_last_heal)


def clear_last_heal(*, reason: str = "") -> None:
    """Drop stale heal blob after a successful preferred (non-heal) connect."""
    global _last_heal
    if _last_heal is None:
        return
    logger.info("IBKR: clearing stale gateway_self_heal (%s)", reason or "preferred connect")
    _last_heal = None


def record_connect_outcome(
    result: ConnectResult,
    *,
    reason: str | None = None,
    mode: str | None = None,
) -> None:
    """Update last outcome; clear intentional when requested mode connects."""
    global _last_result, _last_reason
    _last_result = result
    _last_reason = reason
    if result == "connected" and mode and _intentional_mode == mode:
        clear_intentional_mode(reason=f"connected {mode}")
        clear_last_heal(reason=f"preferred {mode} connected")
    elif result == "connected" and mode:
        # Preferred env connect without an intentional switch — still clear stale heal.
        clear_last_heal(reason=f"preferred {mode} connected")


def heal_status() -> dict[str, Any]:
    """Fields merged into GET /api/ibkr/status."""
    return {
        "gateway_self_heal_enabled": self_heal_enabled(),
        "gateway_self_heal": _last_heal,
        "intentional_gateway_mode": _intentional_mode,
        "intentional_gateway_mode_at": _intentional_at or None,
        "connect_last_result": _last_result,
        "connect_last_reason": _last_reason,
    }


def clear_heal_status_for_tests() -> None:
    global _last_heal, _intentional_mode, _intentional_at, _last_result, _last_reason
    _last_heal = None
    _intentional_mode = None
    _intentional_at = 0.0
    _last_result = "idle"
    _last_reason = None
