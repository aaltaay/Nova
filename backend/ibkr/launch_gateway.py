"""
User-initiated IB Gateway launch / focus (Windows).

Does not store credentials and does not auto-login. Prefer local IBC script
when present; otherwise start ibgateway.exe and bring its window forward.
"""
from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path

from constants_ibkr import (
    IBKR_GATEWAY_EXE_DEFAULT,
    IBKR_GATEWAY_ROOT,
    IBKR_IBC_LAUNCHER_REL,
)

logger = logging.getLogger(__name__)


def _ibc_launcher() -> Path | None:
    home = Path.home()
    candidate = home / IBKR_IBC_LAUNCHER_REL
    return candidate if candidate.is_file() else None


def _resolve_gateway_exe() -> Path | None:
    override = (os.environ.get("IBKR_GATEWAY_EXE") or "").strip()
    if override:
        p = Path(override)
        return p if p.is_file() else None

    default = Path(IBKR_GATEWAY_EXE_DEFAULT)
    if default.is_file():
        return default

    root = Path(IBKR_GATEWAY_ROOT)
    if not root.is_dir():
        return None
    found = sorted(
        root.glob("*/ibgateway.exe"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return found[0] if found else None


def _focus_gateway_window() -> bool:
    """Bring an existing Gateway window to the foreground (best-effort)."""
    if os.name != "nt":
        return False
    ps = r"""
$procs = Get-Process | Where-Object {
  $_.MainWindowHandle -ne 0 -and (
    $_.ProcessName -match 'ibgateway|tws' -or
    $_.MainWindowTitle -match 'IBKR Gateway|IB Gateway|Authenticating'
  )
}
if (-not $procs) { exit 2 }
Add-Type @'
using System;
using System.Runtime.InteropServices;
public class NovaWin {
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
}
'@
foreach ($p in $procs) {
  [void][NovaWin]::ShowWindow($p.MainWindowHandle, 9)
  [void][NovaWin]::SetForegroundWindow($p.MainWindowHandle)
}
exit 0
"""
    try:
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
            capture_output=True,
            text=True,
            timeout=12,
            check=False,
        )
        return completed.returncode == 0
    except Exception as exc:
        logger.warning("IBKR: focus Gateway window failed: %s", exc)
        return False


def _gateway_process_running() -> bool:
    if os.name != "nt":
        return False
    try:
        completed = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "if (Get-Process -Name ibgateway,tws -ErrorAction SilentlyContinue) { exit 0 } else { exit 1 }",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        return completed.returncode == 0
    except Exception:
        return False


def _start_process(path: Path, *, via_powershell: bool = False) -> None:
    if via_powershell:
        subprocess.Popen(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(path),
            ],
            cwd=str(path.parent),
            close_fds=True,
        )
        return
    subprocess.Popen(
        [str(path)],
        cwd=str(path.parent),
        close_fds=True,
    )


def launch_or_focus_gateway() -> dict:
    """
    Launch IB Gateway (or IBC) and/or focus its window.

    Returns a JSON-serializable status dict for the route handler.
    """
    if os.name != "nt":
        return {
            "ok": False,
            "action": "unsupported",
            "message": "Gateway launch is only supported on Windows.",
        }

    running = _gateway_process_running()
    if running:
        focused = _focus_gateway_window()
        return {
            "ok": True,
            "action": "focused" if focused else "already_running",
            "message": (
                "IB Gateway is already running — brought its window forward. "
                "Complete login / IBKR Mobile 2FA if prompted."
                if focused
                else "IB Gateway process is running — check the taskbar for its window and complete login if needed."
            ),
        }

    ibc = _ibc_launcher()
    if ibc is not None:
        try:
            _start_process(ibc, via_powershell=True)
            logger.info("IBKR: launched IBC script %s", ibc)
            return {
                "ok": True,
                "action": "launched_ibc",
                "path": str(ibc),
                "message": (
                    "Started IB Gateway via your local IBC launcher. "
                    "Complete IBKR Mobile 2FA on your phone if prompted."
                ),
            }
        except Exception as exc:
            logger.warning("IBKR: IBC launcher failed (%s); trying exe", exc)

    exe = _resolve_gateway_exe()
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
        _start_process(exe)
        logger.info("IBKR: launched Gateway exe %s", exe)
        # Best-effort focus shortly after spawn (window may not exist yet).
        _focus_gateway_window()
        return {
            "ok": True,
            "action": "launched",
            "path": str(exe),
            "message": (
                "Started IB Gateway — look for its login window and complete "
                "username/password + IBKR Mobile 2FA if prompted."
            ),
        }
    except Exception as exc:
        logger.exception("IBKR: failed to launch Gateway")
        return {
            "ok": False,
            "action": "error",
            "message": f"Failed to start IB Gateway: {exc}",
        }
