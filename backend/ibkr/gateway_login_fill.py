"""Fill Gateway Login without clicking Log In. Never logs secrets."""
from __future__ import annotations

import ctypes
import logging
import re
import sys
import time
from pathlib import Path
from typing import Callable, NamedTuple

logger = logging.getLogger(__name__)

_KEY_RE = re.compile(r"^(IbLoginId|IbPassword)=(.*)$")
_IBC_LOG_DIR = Path.home() / ".nova" / "ibc" / "Logs"

# SendInput / EnumWindows are Windows-only. Parse helpers below must stay
# importable on Linux CI (pytest collects this module on ubuntu-latest).
if sys.platform == "win32":
    from ctypes import wintypes

    user32 = ctypes.windll.user32

    class _KEYBDINPUT(ctypes.Structure):
        _fields_ = (
            ("wVk", wintypes.WORD),
            ("wScan", wintypes.WORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
        )

    class _INPUT(ctypes.Structure):
        _fields_ = (("type", wintypes.DWORD), ("ki", _KEYBDINPUT))
else:
    wintypes = None  # type: ignore[assignment]
    user32 = None
    _KEYBDINPUT = None  # type: ignore[assignment]
    _INPUT = None  # type: ignore[assignment]


class Credentials(NamedTuple):
    username: str
    password: str


def parse_ibc_credentials(text: str) -> Credentials | None:
    user = ""
    password = ""
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = _KEY_RE.match(line)
        if not match:
            continue
        key, val = match.group(1), match.group(2)
        if key == "IbLoginId" and not user:
            user = val
        elif key == "IbPassword" and not password:
            password = val
    if not user or not password:
        return None
    return Credentials(username=user, password=password)


def ibc_config_path() -> Path:
    return Path.home() / ".nova" / "ibc" / "config.ini"


def load_ibc_credentials(ini: Path | None = None) -> Credentials | None:
    path = ini or ibc_config_path()
    if not path.is_file():
        logger.warning("IBKR: IBC config.ini missing; cannot fill login")
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        logger.warning("IBKR: IBC config.ini unreadable", exc_info=True)
        return None
    creds = parse_ibc_credentials(text)
    if creds is None:
        logger.warning("IBKR: IBC config.ini has no IbLoginId/IbPassword")
    return creds


def write_ini_key(path: Path, key: str, value: str) -> bool:
    """Replace first key= line or append. Does not log values."""
    if not path.is_file():
        return False
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    out: list[str] = []
    done = False
    prefix = f"{key}="
    for line in lines:
        stripped = line.strip()
        if not done and stripped.startswith(prefix) and not stripped.startswith("#"):
            ending = "\n" if line.endswith("\n") else ""
            out.append(f"{key}={value}{ending}")
            done = True
        else:
            out.append(line)
    if not done:
        out.append(f"{key}={value}\n")
    path.write_text("".join(out), encoding="utf-8")
    return True


def read_ini_key(path: Path, key: str) -> str:
    if not path.is_file():
        return ""
    prefix = f"{key}="
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith(prefix) and not stripped.startswith("#"):
            return stripped[len(prefix) :]
    return ""


def align_ibc_login_id(path: Path, mode: str) -> None:
    """Copy IbLoginIdLive or IbLoginIdPaper onto IbLoginId. Local file only."""
    chosen = read_ini_key(path, "IbLoginIdLive" if mode == "live" else "IbLoginIdPaper")
    if not chosen:
        logger.warning("IBKR: missing IbLoginIdLive/IbLoginIdPaper in IBC config")
        return
    write_ini_key(path, "IbLoginId", chosen)
    logger.info("IBKR: IbLoginId set for %s", mode)


def write_ib_password(path: Path, password: str) -> bool:
    return write_ini_key(path, "IbPassword", password)


def blank_ib_password() -> str | None:
    creds = load_ibc_credentials()
    if creds is None:
        return None
    if not write_ib_password(ibc_config_path(), ""):
        logger.warning("IBKR: could not blank IbPassword")
        return None
    logger.info("IBKR: IbPassword blanked so IBC will not click Log In")
    return creds.password


def restore_ib_password(password: str | None) -> None:
    if password is None:
        return
    write_ib_password(ibc_config_path(), password)
    logger.info("IBKR: IbPassword restored on disk")


def classify_ibc_login_progress(text: str) -> str:
    """clicked_login | username_set | waiting. Does not log secrets."""
    low = text.lower()
    if "click button: log in" in low:
        return "clicked_login"
    if "setting user name" in low:
        return "username_set"
    return "waiting"


def snapshot_ibc_log(log_dir: Path | None = None) -> tuple[Path | None, int]:
    directory = log_dir or _IBC_LOG_DIR
    try:
        logs = sorted(directory.glob("IBC-*.txt"), key=lambda p: p.stat().st_mtime)
    except Exception:
        return None, 0
    if not logs:
        return None, 0
    newest = logs[-1]
    return newest, newest.stat().st_size


def _log_suffix(origin: tuple[Path | None, int], log_dir: Path | None) -> str:
    directory = log_dir or _IBC_LOG_DIR
    try:
        logs = sorted(directory.glob("IBC-*.txt"), key=lambda p: p.stat().st_mtime)
    except Exception:
        return ""
    if not logs:
        return ""
    newest = logs[-1]
    origin_path, origin_size = origin
    try:
        if origin_path is None or newest != origin_path:
            return newest.read_text(encoding="utf-8", errors="replace")
        data = newest.read_bytes()[max(0, origin_size) :]
        return data.decode("utf-8", errors="replace")
    except Exception:
        return ""


def wait_ibc_username_set(
    *,
    origin: tuple[Path | None, int] = (None, 0),
    log_dir: Path | None = None,
    timeout_sec: float = 25.0,
) -> str:
    deadline = time.time() + timeout_sec
    last = "waiting"
    while time.time() < deadline:
        last = classify_ibc_login_progress(_log_suffix(origin, log_dir))
        if last in ("username_set", "clicked_login"):
            return last
        time.sleep(0.4)
    return last


def type_password_only(password: str, *, delay_sec: float = 0.0) -> bool:
    if delay_sec > 0:
        time.sleep(delay_sec)
    hwnd = _find_gateway_hwnd()
    if not hwnd:
        logger.warning("IBKR: no Gateway window for password fill")
        return False
    try:
        _focus_hwnd(hwnd)
        time.sleep(0.4)
        _send_unicode(password)
    except Exception:
        logger.warning("IBKR: password fill failed", exc_info=True)
        return False
    logger.info("IBKR: typed password into Gateway; Log In not clicked")
    return True


def live_ibc_fill_hooks() -> tuple[str | None, Callable[[], None] | None]:
    origin = snapshot_ibc_log()
    saved = blank_ib_password()
    if not saved:
        return None, None

    def after() -> None:
        state = wait_ibc_username_set(origin=origin)
        if state == "clicked_login":
            logger.warning("IBKR: IBC already clicked Log In -- password was not blank in time")
            restore_ib_password(saved)
            return
        if state != "username_set":
            logger.warning("IBKR: IBC username fill timed out (%s)", state)
            restore_ib_password(saved)
            return
        time.sleep(0.6)
        type_password_only(saved)
        restore_ib_password(saved)

    return saved, after


def _find_gateway_hwnd() -> int:
    found: list[int] = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def _enum(hwnd: int, _lparam: int) -> bool:
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length < 1:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value or ""
        if re.search(r"IBKR Gateway|IB Gateway|^Login$|^New Login$", title, re.I):
            found.append(int(hwnd))
        return True

    user32.EnumWindows(_enum, 0)
    return found[0] if found else 0


def _focus_hwnd(hwnd: int) -> None:
    user32.ShowWindow(hwnd, 9)
    user32.SetForegroundWindow(hwnd)


def _send_unicode(text: str) -> None:
    extra = ctypes.c_ulong(0)
    for ch in text:
        inp = _INPUT()
        inp.type = 1
        inp.ki.wVk = 0
        inp.ki.wScan = ord(ch)
        inp.ki.dwFlags = 0x0004
        inp.ki.time = 0
        inp.ki.dwExtraInfo = ctypes.pointer(extra)
        user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))
        inp.ki.dwFlags = 0x0004 | 0x0002
        user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))
