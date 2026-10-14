"""A dead Time & Sales line makes Nova ask IB Gateway for its market data back (#722).

ADR 045 amendment 2026-10-14. At 09:25:11 ET the AllLast lines of GENK, BEZ and MXCT stopped in the
same second and IBKR's chart history stopped answering, while every Level 1 and Level 2 line kept
updating. Nova read GENK's line dead at 09:25:21 and only said so on the badge. Nothing came back
until IBKR reset its chart-history farm itself at 09:28:24 (2105 broken, 2106 OK); prints followed
0.8 s later. RAMZ, whose recording re-asked its own line at 09:26:48, came back 44 s after the lines
nobody re-asked: inside such a stall a new request does not help.

So when a line reads dead (``ibkr.tape_silence.reading``), Nova sends IBC's ``RECONNECTDATA`` -- the
Gateway's Reconnect Data (Ctrl-Alt-F), which re-opens the data-farm connections only; the order
connection stays -- at most once every ``IBKR_RECONNECT_DATA_COOLDOWN_SEC``, and only to a Gateway Nova
is connected to. ``IBKR_RECONNECT_DATA_VERIFY_SEC`` later it records which of the dead lines printed
again. Each attempt goes to the log and the perf day file (``kind: "tape_recovery"``, a ``sent`` row
and a ``verified`` row) and its words join the dead line's reading. Whether it shortens a stall is
measured on each incident, never claimed. ``NOVA_TAPE_RECONNECT_DATA=0`` turns it off.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from collections import deque
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from constants_ibkr import (
    IBKR_RECONNECT_DATA_COMMAND,
    IBKR_RECONNECT_DATA_COOLDOWN_SEC,
    IBKR_RECONNECT_DATA_VERIFY_SEC,
)

logger = logging.getLogger(__name__)

ET = ZoneInfo("America/New_York")
ENV_SWITCH = "NOVA_TAPE_RECONNECT_DATA"
_KEEP = 20

_lock = threading.Lock()
_last_sent: float | None = None
_attempts: deque[dict[str, Any]] = deque(maxlen=_KEEP)


def reset_for_tests() -> None:
    global _last_sent
    with _lock:
        _last_sent = None
        _attempts.clear()


def enabled() -> bool:
    return os.environ.get(ENV_SWITCH, "1").strip().lower() not in ("0", "false", "no", "off")


def _clock(ts: float) -> str:
    return datetime.fromtimestamp(ts, ET).strftime("%H:%M:%S ET")


def _connected() -> bool:
    try:
        from ibkr import client
        from sim.mode import is_replay_desk

        return bool(client.is_ready()) and not is_replay_desk()
    except Exception:
        logger.exception("IBKR tape recovery: could not tell whether the Gateway is connected")
        return False


def attempts() -> list[dict[str, Any]]:
    """The recent attempts, newest last (memory only)."""
    with _lock:
        return [dict(a) for a in _attempts]


def line_dead(symbol: str, reading: dict[str, Any], *, now: float | None = None) -> dict[str, Any] | None:
    """A line read dead: ask IB Gateway to reconnect its data, unless asked within the cooldown.

    Returns the attempt it started, else None. The command goes out on a thread of its own: IBC's
    command server answers within seconds, and the caller is a socket or the matcher's loop.
    """
    global _last_sent
    if not enabled():
        return None
    ts = time.time() if now is None else float(now)
    with _lock:
        if _last_sent is not None and ts - _last_sent < IBKR_RECONNECT_DATA_COOLDOWN_SEC:
            return None
        if not _connected():
            return None
        _last_sent = ts
        lines = sorted({(symbol or "").strip().upper(), *(reading.get("pipeline") or [])})
        attempt: dict[str, Any] = {
            "ts": round(ts, 3), "trigger": (symbol or "").strip().upper(), "lines": lines,
            "silence_since": reading.get("since"), "history_unanswered_since": reading.get("history_unanswered_since"),
            "command": IBKR_RECONNECT_DATA_COMMAND, "sent": None, "error": None, "back": None, "still_dead": None,
        }
        _attempts.append(attempt)
    threading.Thread(target=_run, args=(attempt,), name="ibkr-tape-recovery", daemon=True).start()
    return dict(attempt)


def _run(attempt: dict[str, Any]) -> None:
    from ibkr.gateway_api_heal import send_ibc_command

    lines = ", ".join(attempt["lines"])
    try:
        error = send_ibc_command(IBKR_RECONNECT_DATA_COMMAND)
    except Exception as exc:
        logger.exception("IBKR tape recovery: sending %s failed", IBKR_RECONNECT_DATA_COMMAND)
        error = str(exc)
    with _lock:
        attempt["sent"] = error is None
        attempt["error"] = error
    if error is not None:
        logger.error("IBKR tape: %s's Time & Sales is dead (with %s) and Nova could not ask IB Gateway to "
                     "reconnect its data: %s", attempt["trigger"], lines, error)
        _persist("sent", attempt)
        return
    logger.warning("IBKR tape: asked IB Gateway to reconnect its market data (IBC %s) -- Time & Sales dead on %s",
                   IBKR_RECONNECT_DATA_COMMAND, lines)
    _persist("sent", attempt)
    time.sleep(IBKR_RECONNECT_DATA_VERIFY_SEC)
    _verify(attempt)


def _verify(attempt: dict[str, Any]) -> None:
    from ibkr.tape_recording import producer_status

    back, dead = [], []
    for sym in attempt["lines"]:
        last = producer_status(sym).get("last_print_ts")
        (back if isinstance(last, (int, float)) and last > attempt["ts"] else dead).append(sym)
    with _lock:
        attempt["back"], attempt["still_dead"] = back, dead
    logger.warning("IBKR tape: %.0f s after Reconnect Data, prints are back on %s; still none on %s",
                   IBKR_RECONNECT_DATA_VERIFY_SEC, ", ".join(back) or "no line", ", ".join(dead) or "no line")
    _persist("verified", attempt)


def words_since(since: float | None) -> str | None:
    """What Nova did about a silence that began at ``since``, for the dead line's reading; None when nothing."""
    if not since:
        return None
    with _lock:
        mine = [a for a in _attempts if a["ts"] >= float(since)]
    if not mine:
        return None
    last = mine[-1]
    when = _clock(last["ts"])
    if last["sent"] is None:
        return f"Nova is asking IB Gateway to reconnect its market data ({when})."
    if not last["sent"]:
        return f"Nova could not ask IB Gateway to reconnect its market data at {when}: {last['error']}."
    if last["back"] is None:
        return f"Nova asked IB Gateway to reconnect its market data at {when}."
    return (f"Nova asked IB Gateway to reconnect its market data at {when}; "
            f"{IBKR_RECONNECT_DATA_VERIFY_SEC:.0f} s later prints were back on {', '.join(last['back']) or 'no line'}.")


def _persist(phase: str, attempt: dict[str, Any]) -> None:
    try:
        from constants_perf import PERF_SCHEMA_VERSION
        from perf import recorder

        with _lock:
            row = dict(attempt)
        recorder.persist({"schema_version": PERF_SCHEMA_VERSION, "kind": "tape_recovery", "phase": phase,
                          **row, "ts": round(time.time(), 3), "asked_ts": row["ts"]})
    except Exception:
        logger.warning("IBKR tape recovery: the %s row was not queued for the perf record", phase, exc_info=True)
