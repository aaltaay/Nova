"""
Self-heal IBKR Gateway paper/live port mismatch.

When IBKR_GATEWAY_MODE points at a closed API port but the other Gateway
port accepts a connection, flip runtime mode (and persist .env) so Nova
reconnects without a manual edit.

Never unlocks orders / live confirmation — safety.py remains SSOT for spend.
Never auto-logins Gateway — if neither 4001 nor 4002 accepts, user/IBC still required.
"""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any, Literal

from constants import (
    IBKR_GATEWAY_SELF_HEAL_DEFAULT,
    IBKR_LIVE_PORT,
    IBKR_PAPER_PORT,
)

logger = logging.getLogger(__name__)

GatewayMode = Literal["paper", "live"]

_GATEWAY_MODE_LINE = re.compile(
    r"^\s*IBKR_GATEWAY_MODE\s*=\s*\S+",
    re.IGNORECASE,
)

# Last successful heal (for /api/ibkr/status); cleared only on process restart.
_last_heal: dict[str, Any] | None = None


def self_heal_enabled() -> bool:
    raw = os.environ.get("IBKR_GATEWAY_SELF_HEAL")
    if raw is None:
        return IBKR_GATEWAY_SELF_HEAL_DEFAULT
    return raw.strip().lower() in ("1", "true", "yes")


def alternate_mode(mode: str) -> GatewayMode:
    return "paper" if mode == "live" else "live"


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
    global _last_heal
    _last_heal = {
        "from_mode": from_mode,
        "to_mode": to_mode,
        "reason": reason,
        "preferred_port": preferred_port,
        "healed_port": healed_port,
        "persisted": persisted,
    }
    logger.warning(
        "IBKR: self-healed gateway_mode %s→%s (preferred port %s failed: %s; "
        "connected on %s). Orders still gated by safety.py. persisted=%s",
        from_mode,
        to_mode,
        preferred_port,
        reason,
        healed_port,
        persisted,
    )
    return dict(_last_heal)


def heal_status() -> dict[str, Any]:
    """Fields merged into GET /api/ibkr/status."""
    return {
        "gateway_self_heal_enabled": self_heal_enabled(),
        "gateway_self_heal": _last_heal,
    }


def clear_heal_status_for_tests() -> None:
    global _last_heal
    _last_heal = None
