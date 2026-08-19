"""User-initiated IB Gateway launch / focus (Windows). Credentials stay in local IBC config."""
import logging
import os
import re
import subprocess
from pathlib import Path

from constants_ibkr import (
    IBKR_GATEWAY_EXE_DEFAULT,
    IBKR_GATEWAY_ROOT,
    IBKR_HOST,
    IBKR_IBC_LAUNCHER_REL,
    IBKR_IBC_LIVE_AUTO_LOGOFF_TIME,
    IBKR_IBC_PAPER_AUTO_RESTART_TIME,
    IBKR_LIVE_PORT,
    IBKR_PAPER_PORT,
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
    renamed_default = default.with_name("ibgateway1.exe")
    if renamed_default.is_file():
        return renamed_default

    root = Path(IBKR_GATEWAY_ROOT)
    if not root.is_dir():
        return None
    found = sorted(
        list(root.glob("*/ibgateway.exe")) + list(root.glob("*/ibgateway1.exe")),
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


def _probe_api_port(port: int) -> bool:
    """True when the local Gateway API socket already accepts TCP."""
    from ibkr.port_diagnostics import probe_port

    host = (os.environ.get("IBKR_HOST") or IBKR_HOST).strip() or IBKR_HOST
    return probe_port(host, int(port))


def _mode_api_port(mode: str) -> int:
    return IBKR_LIVE_PORT if mode == "live" else IBKR_PAPER_PORT


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


def _ibc_dir() -> Path:
    return Path.home() / ".nova" / "ibc"


def _rewrite_ini_key(path: Path, key: str, value: str) -> bool:
    """Replace the first ``key=...`` line. Returns True if a line was rewritten."""
    if not path.is_file():
        return False
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(rf"^{re.escape(key)}=.*$", re.MULTILINE)
    if not pattern.search(text):
        return False
    path.write_text(pattern.sub(f"{key}={value}", text, count=1), encoding="utf-8")
    return True


def _align_ibc_trading_mode(mode: str) -> None:
    """Point local IBC at paper (4002) or live (4001). Never touches credentials.

    Live clears AutoRestart (writes AutoLogoff) so IBKR can send Mobile 2FA
    after IBC fills username/password. Paper restores the week-long token.
    """
    ini = _ibc_dir() / "config.ini"
    port = "4001" if mode == "live" else "4002"
    _rewrite_ini_key(ini, "TradingMode", mode)
    _rewrite_ini_key(ini, "OverrideTwsApiPort", port)
    from ibkr.gateway_login_fill import align_ibc_login_id

    align_ibc_login_id(ini, mode)
    if mode == "live":
        _rewrite_ini_key(ini, "AutoRestartTime", "")
        _rewrite_ini_key(ini, "AutoLogoffTime", IBKR_IBC_LIVE_AUTO_LOGOFF_TIME)
    else:
        _rewrite_ini_key(ini, "AutoRestartTime", IBKR_IBC_PAPER_AUTO_RESTART_TIME)
        _rewrite_ini_key(ini, "AutoLogoffTime", "")


def _apply_nova_gateway_mode(mode: str) -> None:
    from ibkr import client as client_mod
    from ibkr import gateway_heal as heal

    heal.persist_gateway_mode(mode)  # type: ignore[arg-type]
    heal.apply_runtime_gateway_mode(mode)  # type: ignore[arg-type]
    heal.set_intentional_mode(mode)  # type: ignore[arg-type]
    client_mod.wake_reconnect_loop()


def _stop_listen_ports(*ports: int) -> None:
    """Stop the process that owns Gateway API LISTEN sockets (often java.exe)."""
    if os.name != "nt":
        return
    for port in ports:
        ps = (
            f"Get-NetTCPConnection -LocalPort {int(port)} -State Listen "
            "-ErrorAction SilentlyContinue | ForEach-Object { "
            "Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }"
        )
        try:
            subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
        except Exception as exc:
            logger.warning("IBKR: stop listen port %s failed: %s", port, exc)


def _stop_gateway_process() -> bool:
    """Stop the IB Gateway windowed process only -- not every java.exe."""
    if os.name != "nt":
        return False
    ps = r"""
Get-Process | Where-Object {
  $_.MainWindowTitle -match 'IBKR Gateway|IB Gateway|Authenticating' -or
  $_.ProcessName -match '^ibgateway'
} | Stop-Process -Force -ErrorAction SilentlyContinue
"""
    try:
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        return completed.returncode == 0
    except Exception as exc:
        logger.warning("IBKR: stop Gateway failed: %s", exc)
        return False


def _start_process(
    path: Path,
    *,
    via_powershell: bool = False,
    extra_args: list[str] | None = None,
) -> None:
    extra = list(extra_args or [])
    if via_powershell:
        subprocess.Popen(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(path),
                *extra,
            ],
            cwd=str(path.parent),
            close_fds=True,
        )
        return
    subprocess.Popen(
        [str(path), *extra],
        cwd=str(path.parent),
        close_fds=True,
    )


def _normalize_launch_mode(mode: str | None) -> str | None:
    if mode is None:
        return None
    raw = str(mode).strip().lower()
    if raw in ("paper", "live"):
        return raw
    return ""


def launch_or_focus_gateway(
    mode: str | None = None,
    *,
    force_restart: bool = False,
) -> dict:
    if os.name != "nt":
        return {
            "ok": False,
            "action": "unsupported",
            "message": "Gateway launch is only supported on Windows.",
        }

    target = _normalize_launch_mode(mode)
    if mode is not None and target == "":
        return {
            "ok": False,
            "action": "invalid_mode",
            "message": f"invalid mode {mode!r} (must be paper or live)",
        }

    if target:
        want_port = _mode_api_port(target)
        if not force_restart and _probe_api_port(want_port):
            _apply_nova_gateway_mode(target)
            _align_ibc_trading_mode(target)
            _focus_gateway_window()
            return {
                "ok": True,
                "action": "already_listening",
                "mode": target,
                "message": (
                    f"{target.upper()} Gateway is already listening on port {want_port}. "
                    "Nova will attach -- Gateway was not restarted."
                ),
            }
        other_port = IBKR_PAPER_PORT if target == "live" else IBKR_LIVE_PORT
        if (
            not force_restart
            and _gateway_process_running()
            and not _probe_api_port(other_port)
        ):
            _apply_nova_gateway_mode(target)
            _align_ibc_trading_mode(target)
            _focus_gateway_window()
            return {
                "ok": True,
                "action": "focused_authenticating",
                "mode": target,
                "message": (
                    "Gateway is already running and the API port is not open yet. "
                    "Did not restart -- complete IBKR Mobile 2FA if prompted."
                ),
            }
        _apply_nova_gateway_mode(target)
        _align_ibc_trading_mode(target)
        if force_restart:
            # One IBC install is one Gateway. A new login must stop the other
            # door or IBC hijacks that window and live 2FA never appears.
            _stop_listen_ports(want_port, other_port)
        from ibkr.gateway_spawn import spawn_mode_gateway

        if target == "live":
            from ibkr.jts_ini import clear_restart_token

            clear_restart_token()
        return spawn_mode_gateway(
            target,
            ibc=_ibc_launcher(),
            exe=_resolve_gateway_exe(),
            start=_start_process,
            focus=_focus_gateway_window,
        )

    running = _gateway_process_running()
    if running and not target:
        focused = _focus_gateway_window()
        return {
            "ok": True,
            "action": "focused" if focused else "already_running",
            "message": (
                "IB Gateway is already running -- brought its window forward. "
                "Complete login / IBKR Mobile 2FA if prompted."
                if focused
                else "IB Gateway process is running -- check the taskbar for its window and complete login if needed."
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
                "Started IB Gateway -- look for its login window and complete "
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
