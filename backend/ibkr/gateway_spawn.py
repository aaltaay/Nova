"""Start IBC or ibgateway.exe after a mode stop. No credentials here."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable

from constants_ibkr import IBKR_GATEWAY_ROOT

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
    """IBC fills username/password. IBKR Mobile 2FA stays on the operator."""
    if ibc is not None:
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
            logger.warning("IBKR: IBC launcher failed (%s); trying exe", exc)
    if exe is None:
        return {
            "ok": False,
            "action": "not_found",
            "message": (
                f"IB Gateway not found under {IBKR_GATEWAY_ROOT}. "
                "Install IB Gateway or set IBKR_GATEWAY_EXE in .env."
            ),
        }
    try:
        start(exe)
        focus()
        if fill_login is not None:
            fill_login()
        logger.info("IBKR: launched Gateway exe %s mode=%s", exe, target)
        port = "4001" if target == "live" else "4002"
        live_msg = (
            f"Started {target.upper()} Gateway (port {port}) without IBC. "
            "Look at the desktop login. Username/password are filled from local IBC "
            "config. Click Log In (Live Trading already). The same window should "
            "become SECOND FACTOR AUTHENTICATION -- type the code there."
        )
        paper_msg = (
            f"Started Gateway exe for {target} (port {port}). "
            "Complete login / IBKR Mobile 2FA if prompted."
        )
        return {
            "ok": True,
            "action": "launched",
            "mode": target,
            "path": str(exe),
            "message": live_msg if target == "live" else paper_msg,
        }
    except Exception as exc:
        logger.exception("IBKR: failed to launch Gateway")
        return {
            "ok": False,
            "action": "error",
            "message": f"Failed to start IB Gateway: {exc}",
        }
