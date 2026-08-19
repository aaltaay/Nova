"""Read IBC log lines into the gateway trail. Never stores passwords."""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from ibkr.gateway_trail import append_event

logger = logging.getLogger(__name__)

_IBC_LOG_DIR = Path.home() / ".nova" / "ibc" / "Logs"
_ACCOUNT_ID = re.compile(r"\bD[UF][A-Z0-9]+\b", re.IGNORECASE)


def parse_ibc_log_events(text: str) -> list[dict[str, Any]]:
    """Map IBC log text to trail rows. Skips credential lines."""
    found: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in text.splitlines():
        line = raw.strip()
        if not line or "IBC:" not in line:
            continue
        low = line.lower()
        if "password" in low:
            continue
        event = None
        note = None
        if "setting trading mode" in low:
            event = "ibc_trading_mode"
            note = _redact(line.split("IBC:", 1)[-1].strip())
        elif "click button: log in" in low:
            event = "ibc_clicked_login"
            note = "IBC clicked Log In (login screen does not stay up)"
        elif "authenticating" in low and "opened" in low:
            event = "ibc_authenticating"
            note = "Authenticating window opened (often only a few seconds)"
        elif "login has completed" in low:
            event = "ibc_login_completed"
            note = "IBC reports login completed"
        elif "simulated trading" in low and "opened" in low:
            event = "ibc_simulated_trading"
            note = "Gateway opened Simulated Trading (paper account)"
        elif "second factor" in low or "ibkr mobile" in low:
            event = "ibc_second_factor"
            note = _redact(line.split("IBC:", 1)[-1].strip())
        if not event or event in seen:
            continue
        seen.add(event)
        found.append({"actor": "ibc", "event": event, "note": note})
    return found


def record_recent_ibc_into_trail(
    *,
    requested: str,
    log_dir: Path | None = None,
    origin_size: int = -1,
) -> int:
    """Append parsed events from the newest IBC log. Returns how many written.

    ``origin_size`` is the log length before this door click. Only the suffix
    is harvested so an old live 2FA is not tagged onto a paper click.
    """
    directory = log_dir or _IBC_LOG_DIR
    try:
        logs = sorted(directory.glob("IBC-*.txt"), key=lambda p: p.stat().st_mtime)
    except Exception:
        logger.warning("IBKR: IBC log dir unreadable", exc_info=True)
        return 0
    if not logs:
        return 0
    newest = logs[-1]
    try:
        data = newest.read_bytes()
        if origin_size >= 0:
            text = data[max(0, origin_size) :].decode("utf-8", errors="replace")
        else:
            text = data.decode("utf-8", errors="replace")
            text = "\n".join(text.splitlines()[-120:])
    except Exception:
        logger.warning("IBKR: IBC log read failed", exc_info=True)
        return 0
    n = 0
    for ev in parse_ibc_log_events(text):
        append_event(
            actor="ibc",
            event=str(ev["event"]),
            requested=requested,
            note=ev.get("note"),
        )
        n += 1
    return n


def _redact(text: str) -> str:
    return _ACCOUNT_ID.sub("DU…", text)[:240]
