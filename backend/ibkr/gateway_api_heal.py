"""A Gateway logged in but refusing its API port restarts itself through IBC -- no phone login.

2026-10-02: the desk's Wi-Fi was down from 12:12 to about 12:45 ET. When it came back, IB
Gateway was logged in with both data farms ON and port 4001 LISTENING, yet it refused every
connection (WinError 1225 / 10061) -- its API listener was wedged. Nova retried every 12 s and
said "finish the login on the desktop", which was not the problem, so nothing healed until the
port was rebound by hand at 12:57.

The rule (owner of the stuck clock and the restart): when Nova's connects to the Gateway's API
port are refused for ``IBKR_GATEWAY_API_STUCK_SEC`` without a break, while that port is LISTENING,
a Gateway process runs and the internet answers, Nova sends IBC's ``RESTART`` command. IBC's
restart reuses the current session's credentials, so no 2FA is needed (IBC user guide, "IBC
commands"); the Gateway is gone for about a minute and Nova attaches when it is back. At most
one restart every ``IBKR_GATEWAY_API_HEAL_COOLDOWN_SEC``. A refusal with the port not listening
is a Gateway that is not up (logged out, starting): not this rule's to touch.

IBC listens for commands only when config.ini sets ``CommandServerPort`` -- this module turns it
on, on this PC only (``ensure_command_server``), which takes effect at the Gateway's next start.
Until then a restart cannot be sent, and the view says so.
"""
from __future__ import annotations

import asyncio
import logging
import re
import socket
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from constants_ibkr import (
    IBKR_GATEWAY_API_HEAL_COOLDOWN_SEC,
    IBKR_GATEWAY_API_STUCK_SEC,
    IBKR_GATEWAY_INTERNET_PROBE_HOST,
    IBKR_IBC_COMMAND_HOST,
    IBKR_IBC_COMMAND_PORT,
    IBKR_IBC_COMMAND_TIMEOUT_SEC,
    IBKR_RECONNECT_DELAY_SEC,
)

logger = logging.getLogger(__name__)

# A gap this long between refusals means the streak is over (the dialer retries every few seconds).
_STREAK_GAP_SEC = max(60.0, 6.0 * float(IBKR_RECONNECT_DELAY_SEC))

WAIT = "wait"            # not refused long enough yet
NOT_LISTENING = "not_listening"
NO_GATEWAY = "no_gateway"
NO_INTERNET = "no_internet"
COOLDOWN = "cooldown"
RESTART = "restart"


@dataclass
class Facts:
    """What the decision reads, gathered off the loop."""

    listening: bool
    gateway_running: bool
    internet: bool


_first_refused: float | None = None
_last_refused: float | None = None
_last_restart_at: float | None = None
_state: dict[str, Any] = {"state": "ok", "text": None, "since": None, "last_restart": None}


def reset_for_tests() -> None:
    global _first_refused, _last_refused, _last_restart_at
    _first_refused = _last_refused = _last_restart_at = None
    _state.update({"state": "ok", "text": None, "since": None, "last_restart": None})


def decide(now: float, *, first_refused: float, facts: Facts, last_restart_at: float | None) -> str:
    """Pure: what to do about a streak of refusals that began at ``first_refused``."""
    if now - first_refused < IBKR_GATEWAY_API_STUCK_SEC:
        return WAIT
    if not facts.gateway_running:
        return NO_GATEWAY
    if not facts.listening:
        return NOT_LISTENING
    if not facts.internet:
        return NO_INTERNET
    if last_restart_at is not None and now - last_restart_at < IBKR_GATEWAY_API_HEAL_COOLDOWN_SEC:
        return COOLDOWN
    return RESTART


def listening_ports(netstat_text: str) -> set[int]:
    """Local TCP ports in LISTENING state in ``netstat -ano -p TCP`` output (pure)."""
    ports: set[int] = set()
    for line in netstat_text.splitlines():
        parts = line.split()
        if len(parts) >= 4 and parts[0].upper() == "TCP" and parts[3].upper() == "LISTENING":
            m = re.search(r":(\d+)$", parts[1])
            if m:
                ports.add(int(m.group(1)))
    return ports


def _port_listening(port: int) -> bool:
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    done = subprocess.run(["netstat", "-ano", "-p", "TCP"], capture_output=True, text=True,
                          timeout=10, check=False, creationflags=flags)
    return port in listening_ports(done.stdout or "")


def _internet_up() -> bool:
    try:
        with socket.create_connection((IBKR_GATEWAY_INTERNET_PROBE_HOST, 443), timeout=4.0):
            return True
    except OSError:
        return False


def gather(port: int) -> Facts:
    """Blocking: read the facts (call from a worker thread)."""
    from ibkr import gateway_process

    try:
        listening = _port_listening(port)
    except (OSError, subprocess.SubprocessError):
        logger.warning("IBKR: could not read the listening ports", exc_info=True)
        listening = False
    return Facts(listening=listening, gateway_running=gateway_process.running(), internet=_internet_up())


def send_ibc_command(command: str) -> str | None:
    """Send one command to IBC's command server; ``None`` on success, else why it failed."""
    try:
        with socket.create_connection((IBKR_IBC_COMMAND_HOST, IBKR_IBC_COMMAND_PORT),
                                      timeout=IBKR_IBC_COMMAND_TIMEOUT_SEC) as conn:
            conn.sendall(f"{command}\n".encode("ascii"))
            conn.settimeout(IBKR_IBC_COMMAND_TIMEOUT_SEC)
            try:
                reply = conn.recv(256).decode("ascii", "replace").strip()
            except socket.timeout:
                reply = ""
    except OSError as exc:
        return f"IBC's command server did not answer on {IBKR_IBC_COMMAND_HOST}:{IBKR_IBC_COMMAND_PORT} ({exc})"
    if reply and not reply.upper().startswith("OK"):
        return f"IBC answered {reply!r}"
    return None


def ensure_command_server(ini: Path) -> bool:
    """Turn on IBC's command server, on this PC only. True when config.ini changed (next start)."""
    if not ini.is_file():
        return False
    text = ini.read_text(encoding="utf-8")
    want = {
        "CommandServerPort": str(IBKR_IBC_COMMAND_PORT),
        "ControlFrom": IBKR_IBC_COMMAND_HOST,
        "BindAddress": IBKR_IBC_COMMAND_HOST,
    }
    changed = text
    for key, value in want.items():
        pattern = re.compile(rf"^{re.escape(key)}=.*$", re.MULTILINE)
        if pattern.search(changed):
            changed = pattern.sub(f"{key}={value}", changed, count=1)
        else:
            changed = changed.rstrip("\n") + f"\n{key}={value}\n"
    if changed == text:
        return False
    ini.write_text(changed, encoding="utf-8")
    logger.warning("IBKR: IBC command server turned on in %s (127.0.0.1:%s) -- from the Gateway's next start",
                   ini, IBKR_IBC_COMMAND_PORT)
    return True


def _ibc_ini() -> Path:
    return Path.home() / ".nova" / "ibc" / "config.ini"


def note_connected() -> None:
    """The API answered: the streak is over."""
    global _first_refused, _last_refused
    _first_refused = _last_refused = None
    if _state["state"] != "ok":
        _state.update({"state": "ok", "text": None, "since": None})


def _say(state: str, text: str | None, now: float) -> None:
    if _state["state"] != state:
        _state["since"] = now
    _state["state"], _state["text"] = state, text


async def after_refused(port: int, now: float | None = None) -> str:
    """The dialer's connect to ``port`` was refused: count it, and restart a stuck Gateway."""
    global _first_refused, _last_refused, _last_restart_at
    ts = time.time() if now is None else now
    if _last_refused is None or ts - _last_refused > _STREAK_GAP_SEC:
        _first_refused = ts
    _last_refused = ts
    assert _first_refused is not None
    if ts - _first_refused < IBKR_GATEWAY_API_STUCK_SEC:
        return WAIT
    facts = await asyncio.to_thread(gather, port)
    action = decide(ts, first_refused=_first_refused, facts=facts, last_restart_at=_last_restart_at)
    secs = int(ts - _first_refused)
    if action == NO_GATEWAY:
        _say(action, "No IB Gateway is running -- start it (Launch Gateway).", ts)
    elif action == NOT_LISTENING:
        _say(action, f"The Gateway is not listening on {port} yet -- it is starting or waiting for its login.", ts)
    elif action == NO_INTERNET:
        _say(action, f"The Gateway refused Nova for {secs}s and the internet is not answering -- "
                     "Nova restarts it once the internet is back.", ts)
    elif action == COOLDOWN:
        _say(action, "The Gateway still refuses Nova after Nova restarted it -- if it keeps on, close it "
                     "and start it again (Launch Gateway).", ts)
    elif action == RESTART:
        _last_restart_at = ts
        await asyncio.to_thread(ensure_command_server, _ibc_ini())
        error = await asyncio.to_thread(send_ibc_command, "RESTART")
        _state["last_restart"] = {"at": ts, "ok": error is None, "error": error}
        if error is None:
            logger.warning("IBKR: the Gateway refused its API port %s for %ss while logged in -- "
                           "sent IBC RESTART (saved login, no 2FA)", port, secs)
            _say(action, f"The Gateway refused Nova for {secs}s while logged in -- Nova restarted it on "
                         "its saved login (no phone needed). Back in about a minute.", ts)
        else:
            logger.error("IBKR: the Gateway's API port %s is stuck and IBC RESTART failed: %s", port, error)
            _say("restart_failed", f"The Gateway refused Nova for {secs}s while logged in, and Nova could not "
                                   f"restart it: {error}. Nova turned IBC's command server on for the "
                                   "Gateway's next start; until then reopen the API port by hand "
                                   "(Configure > Settings > API: change the port and back).", ts)
    return action


async def after_failed(reason: str, port: int) -> None:
    """The dialer's hook for every failed connect: only a refusal counts; a failure here never stops the dialer."""
    if reason != "refused":
        return
    try:
        await after_refused(port)
    except Exception:
        logger.exception("IBKR: the stuck-API-port heal failed")


def view() -> dict[str, Any]:
    """For ``/api/ibkr/status`` and the checklist: ``{state, text, since, last_restart, refused_since}``."""
    return {**_state, "refused_since": _first_refused}
