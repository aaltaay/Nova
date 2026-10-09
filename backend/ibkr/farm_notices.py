"""IBKR's data-farm and line notices, kept with their farm and time (#722).

2026-10-05 09:35:42 ET: the AllLast lines of SAIQ and VEEA stopped in the same instant while both
stocks' Level 1 kept counting trades and their books kept moving. From 09:38 IBKR's HMDS farm
flapped (2105 / 2106), but Nova recognised only the OK and idle codes, and the day's API log has
since rotated away, so nothing ties the silence to a farm event. Every notice below is now kept:

* a farm broken (2103 market data, 2105 HMDS, 2157 sec-def), OK again (2104 / 2106 / 2158) or
  inactive (2107 / 2108). The farm is the text after the last colon (``usfarm``, ``ushmds``);
* 316, market depth halted ("Please re-subscribe"), with the request id and symbol it names;
* 10197, no market data during a competing live session.

Each is logged (WARNING when something broke), kept in memory for ``/api/diagnostics`` and the tape
silence reading (``ibkr/tape_silence.py``), and written to the perf day file as
``kind: "ib_notice"``, which outlives the API log. Record and display only: nothing here
disconnects, reconnects or restarts the Gateway, which would also tear down the order channel.
``note`` runs inside ib_async's errorEvent, so it issues no IB request and only enqueues the write.
"""
from __future__ import annotations

import logging
import threading
import time
from collections import deque
from typing import Any

from constants_ibkr import (
    IBKR_ERROR_COMPETING_SESSION,
    IBKR_ERROR_DEPTH_HALTED,
    IBKR_FARM_BROKEN_CODES,
    IBKR_FARM_INACTIVE_CODES,
    IBKR_FARM_OK_CODES,
    IBKR_NOTICES_KEEP,
)

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1

BROKEN = "broken"
OK = "ok"
INACTIVE = "inactive"
DEPTH_HALTED = "depth_halted"
COMPETING_SESSION = "competing_session"
# Notices that say something stopped; OK and inactive are the all-clear and the idle state.
TROUBLE = frozenset({BROKEN, DEPTH_HALTED, COMPETING_SESSION})

_FARM_TYPES = {
    2103: "market data", 2104: "market data", 2108: "market data",
    2105: "HMDS", 2106: "HMDS", 2107: "HMDS",
    2157: "sec-def", 2158: "sec-def",
}
_IDLE_MARKER = "upon demand."

_lock = threading.Lock()
_recent: deque[dict[str, Any]] = deque(maxlen=IBKR_NOTICES_KEEP)
_farms: dict[str, dict[str, Any]] = {}


def reset_for_tests() -> None:
    with _lock:
        _recent.clear()
        _farms.clear()


def notice_of(code: int) -> str | None:
    """What a code says, or None for a code this module does not keep."""
    if code in IBKR_FARM_BROKEN_CODES:
        return BROKEN
    if code in IBKR_FARM_OK_CODES:
        return OK
    if code in IBKR_FARM_INACTIVE_CODES:
        return INACTIVE
    if code == IBKR_ERROR_DEPTH_HALTED:
        return DEPTH_HALTED
    if code == IBKR_ERROR_COMPETING_SESSION:
        return COMPETING_SESSION
    return None


def farm_name(message: str | None) -> str | None:
    """The farm a notice names: after the last colon, or after "upon demand." for 2107 / 2108."""
    text = (message or "").strip()
    if ":" in text:
        name = text.rsplit(":", 1)[1].strip()
    elif _IDLE_MARKER in text:
        name = text.rsplit(_IDLE_MARKER, 1)[1].strip()
    else:
        return None
    return name or None


def note(code: int, message: str | None, *, now: float | None = None, req_id: int | None = None,
         symbol: str | None = None) -> dict[str, Any] | None:
    """Keep one notice; the row kept, or None for a code this module does not keep. Never acts."""
    code = int(code)
    notice = notice_of(code)
    if notice is None:
        return None
    ts = time.time() if now is None else float(now)
    msg = (message or "").strip()
    farm = farm_name(msg) if code in _FARM_TYPES else None
    row = {
        "ts": round(ts, 3),
        "code": code,
        "notice": notice,
        "farm": farm,
        "farm_type": _FARM_TYPES.get(code),
        "message": msg,
        "req_id": req_id if req_id is not None and req_id >= 0 else None,
        "symbol": (symbol or "").strip().upper() or None,
    }
    with _lock:
        _recent.append(row)
        if farm:
            _farms[farm] = {"farm": farm, "farm_type": row["farm_type"], "state": notice, "code": code,
                            "since": row["ts"], "message": msg}
    level = logging.WARNING if notice in TROUBLE else logging.INFO
    logger.log(level, "IBKR notice %s (%s%s%s): %s", code, notice, f", farm {farm}" if farm else "",
               f", {row['symbol']}" if row["symbol"] else "", msg or "no detail")
    _persist(row)
    return row


def _persist(row: dict[str, Any]) -> None:
    """Into the perf day file beside the samples; the recorder's writer thread does the disk."""
    try:
        from constants_perf import PERF_SCHEMA_VERSION
        from perf import recorder

        recorder.persist({"schema_version": PERF_SCHEMA_VERSION, "kind": "ib_notice", **row})
    except Exception:
        logger.warning("IBKR notice %s: could not queue it for the perf record", row.get("code"), exc_info=True)


def view() -> dict[str, Any]:
    """Each farm's last word and the notices kept, newest last (memory only)."""
    with _lock:
        farms = sorted((dict(f) for f in _farms.values()), key=lambda f: f["farm"])
        recent = [dict(r) for r in _recent]
    return {
        "schema_version": SCHEMA_VERSION,
        "farms": farms,
        "broken": [f["farm"] for f in farms if f["state"] == BROKEN],
        "recent": recent,
    }


def trouble_since(ts: float, *, window: float) -> dict[str, Any] | None:
    """The newest notice that something stopped, from ``window`` seconds before ``ts`` on, else None."""
    floor = float(ts) - float(window)
    with _lock:
        for row in reversed(_recent):
            if row["ts"] < floor:
                return None
            if row["notice"] in TROUBLE:
                return {k: row[k] for k in ("ts", "code", "notice", "farm", "farm_type", "message", "symbol")}
    return None
