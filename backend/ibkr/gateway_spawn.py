"""Start IBC after a mode stop. Username/password come from local IBC config."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable

from constants_ibkr import (
    IBKR_LAUNCH_MISSING_CREDS_MSG,
    IBKR_LAUNCH_MISSING_IBC_MSG,
)
from ibkr.gateway_login_fill import load_ibc_credentials

logger = logging.getLogger(__name__)

StartFn = Callable[..., None]
FocusFn = Callable[[], bool]


def spawn_mode_gateway(
    target: str,
    *,
    ibc: Path | None,
    exe: Path | None,
    start: StartFn,
    focus: FocusFn,
    fill_login: Callable[[], None] | None = None,
) -> dict[str, Any]:
    """IBC fills username/password. IBKR Mobile 2FA stays on the operator.

    Open live/paper must not fall through to a raw ibgateway.exe. That path
    leaves the login form empty while the UI claimed IBC filled it.
    ``exe`` is accepted for callers/tests but is not started.
    """
    del exe
    creds = load_ibc_credentials()
    if creds is None:
        return {
            "ok": False,
            "action": "missing_credentials",
            "mode": target,
            "message": IBKR_LAUNCH_MISSING_CREDS_MSG,
        }
    if ibc is None:
        return {
            "ok": False,
            "action": "missing_ibc",
            "mode": target,
            "message": IBKR_LAUNCH_MISSING_IBC_MSG,
        }
    try:
        start(ibc, via_powershell=True, extra_args=["-TradingMode", target])
        logger.info("IBKR: launched IBC %s mode=%s", ibc, target)
        if fill_login is not None:
            fill_login()
        port = "4001" if target == "live" else "4002"
        return {
            "ok": True,
            "action": "launched_ibc",
            "mode": target,
            "path": str(ibc),
            "message": (
                f"Starting {target.upper()} Gateway (port {port}). "
                "IBC fills username/password. Watch the desktop for SECOND "
                "FACTOR / IBKR Mobile. The other door is closed so IBC does "
                "not hijack that window."
                if target == "live"
                else (
                    f"Starting {target.upper()} Gateway (port {port}). "
                    "IBC fills username/password. The other door is closed "
                    "so IBC can start this login."
                )
            ),
        }
    except Exception as exc:
        logger.warning("IBKR: IBC launcher failed: %s", exc)
        return {
            "ok": False,
            "action": "error",
            "mode": target,
            "message": f"IBC launcher failed: {exc}",
        }
