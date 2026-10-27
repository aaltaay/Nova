"""Who holds Claude's seat, its lease, its armed breaks, its note and recent events (ADR 068 decisions 1, 4, 9).

One holder at a time: ``claim`` returns a token, every later call names it, and a second claim is refused while the
first holder's lease is alive. The state is persisted to ``backend/.cache/agent-seat.json`` (written whole and
atomically) so a restart keeps the reservation and the armed breaks; spend arming is never persisted (ADR 018).

Pure state: no IBKR line, no order. ``agent_trader.lines`` holds the line, ``agent_trader.watcher`` acts on lapses.
"""
from __future__ import annotations

import json
import logging
import secrets
import threading
import uuid
from pathlib import Path
from typing import Any, NamedTuple

from agent_trader import clock
from agent_trader.constants_agent_trader import (
    AGENT_EVENTS_KEEP,
    AGENT_LEASE_SEC,
    AGENT_NOTE_MAX_CHARS,
    AGENT_SCHEMA_VERSION,
    AGENT_SEAT_FILE,
)

logger = logging.getLogger(__name__)
_lock = threading.RLock()
_state: dict[str, Any] | None = None


class Refusal(NamedTuple):
    """A seat call refused: ``code`` on the wire, ``text`` in words, ``status`` the HTTP status. A value, never an
    exception: what reaches the wire is these words alone."""

    code: str
    text: str
    status: int = 409


def _blank() -> dict[str, Any]:
    return {"schema_version": AGENT_SCHEMA_VERSION, "holder": None, "since": None, "beat_at": None,
            "yielded": False, "yielded_at": None, "symbol": None, "breaks": [], "note": None, "events": []}


def path() -> Path:
    from paths import cache_dir

    return cache_dir() / AGENT_SEAT_FILE


def _load() -> dict[str, Any]:
    global _state
    if _state is not None:
        return _state
    target = path()
    loaded = _blank()
    try:
        if target.exists():
            raw = json.loads(target.read_text(encoding="utf-8"))
            if not isinstance(raw, dict) or raw.get("schema_version") != AGENT_SCHEMA_VERSION:
                logger.error("AGENT seat: %s has schema %r, not %s -- starting with the seat off",
                             target, (raw or {}).get("schema_version") if isinstance(raw, dict) else None,
                             AGENT_SCHEMA_VERSION)
            else:
                loaded.update({k: raw[k] for k in loaded if k in raw})
    except (OSError, ValueError) as exc:
        logger.exception("AGENT seat: %s could not be read (%s) -- starting with the seat off", target, exc)
    _state = loaded
    return _state


def _save() -> None:
    from capture.manifest_io import write_json_atomic

    try:
        write_json_atomic(path(), _load())
    except OSError:
        logger.exception("AGENT seat: could not write %s", path())


def reset_for_tests() -> None:
    global _state
    with _lock:
        _state = None


def snapshot() -> dict[str, Any]:
    with _lock:
        return json.loads(json.dumps(_load()))


def holder() -> str | None:
    with _lock:
        return _load().get("holder")


def lapsed(now: float | None = None) -> bool:
    """A holder whose last check-in is older than the lease."""
    with _lock:
        st = _load()
        if not st.get("holder"):
            return False
        beat = float(st.get("beat_at") or 0.0)
        return (clock.now() if now is None else now) - beat > AGENT_LEASE_SEC


def is_on() -> bool:
    """Someone holds the seat (lapsed or not -- the watcher ends a lapsed one)."""
    return holder() is not None


def reserves_line() -> bool:
    """The seat keeps one Level 2 line for Claude: on and not given up to the operator."""
    with _lock:
        st = _load()
        return bool(st.get("holder")) and not st.get("yielded")


def is_yielded() -> bool:
    with _lock:
        return bool(_load().get("yielded"))


def symbol() -> str | None:
    with _lock:
        return _load().get("symbol")


def refusal(token: str | None) -> Refusal | None:
    """Why ``token`` does not hold the seat now, or None."""
    from agent_trader.constants_agent_trader import AGENT_NOT_HOLDER, AGENT_SEAT_OFF

    with _lock:
        held = _load().get("holder")
    if not held:
        return Refusal(AGENT_SEAT_OFF, "Claude's seat is off: claim it first.")
    if not token or not secrets.compare_digest(str(token), str(held)):
        return Refusal(AGENT_NOT_HOLDER, "Another session holds Claude's seat.", 403)
    return None


def claim(now: float | None = None) -> tuple[str | None, Refusal | None]:
    """Take the seat: ``(token, None)``, or ``(None, why)`` while another holder's lease is alive."""
    from agent_trader.constants_agent_trader import AGENT_SEAT_TAKEN

    t = clock.now() if now is None else now
    with _lock:
        st = _load()
        if st.get("holder") and not lapsed(t):
            return None, Refusal(AGENT_SEAT_TAKEN, "Claude's seat is already held by another session; it frees when "
                                 "that session lets go or goes quiet for 10 minutes.")
        token = uuid.uuid4().hex
        st.update(holder=token, since=t, beat_at=t, yielded=False, yielded_at=None)
        _event_locked(st, t, "on", "Claude took its seat")
        _save()
        return token, None


def beat(token: str | None, now: float | None = None) -> Refusal | None:
    """Renew the lease; why not, or None."""
    if why := refusal(token):
        return why
    with _lock:
        _load()["beat_at"] = clock.now() if now is None else now
        _save()
    return None


def turn_off(reason: str, now: float | None = None) -> None:
    """The seat off: no holder, no breaks, no stock. The caller has already closed what had to close."""
    t = clock.now() if now is None else now
    with _lock:
        st = _load()
        if not st.get("holder"):
            return
        st.update(holder=None, since=None, beat_at=None, yielded=False, yielded_at=None, symbol=None, breaks=[])
        _event_locked(st, t, "off", reason)
        _save()


def set_yielded(value: bool, text: str, now: float | None = None) -> None:
    t = clock.now() if now is None else now
    with _lock:
        st = _load()
        st["yielded"] = bool(value)
        st["yielded_at"] = t if value else None
        if value:
            st["breaks"] = []
        _event_locked(st, t, "yielded" if value else "line_back", text)
        _save()


def set_symbol(sym: str | None, now: float | None = None) -> None:
    t = clock.now() if now is None else now
    with _lock:
        st = _load()
        new = sym.upper() if sym else None
        if st.get("symbol") == new:
            return
        st["symbol"] = new
        _event_locked(st, t, "watch", f"watching {new}" if new else "watching nothing")
        _save()


def set_note(text: str, now: float | None = None) -> None:
    with _lock:
        _load()["note"] = {"text": str(text)[:AGENT_NOTE_MAX_CHARS], "at": clock.now() if now is None else now}
        _save()


def breaks() -> list[dict[str, Any]]:
    with _lock:
        return [dict(b) for b in _load().get("breaks") or []]


def add_break(row: dict[str, Any], now: float | None = None) -> dict[str, Any]:
    t = clock.now() if now is None else now
    with _lock:
        st = _load()
        made = {**row, "id": uuid.uuid4().hex[:12], "created_at": t}
        st["breaks"] = [*(st.get("breaks") or []), made]
        _event_locked(st, t, "break_set", f"set buy {made['qty']:g} {made['symbol']} on a print at "
                      f"{made['trigger']:g} (up to {made['top']:g}), stop {made['stop']:g}")
        _save()
        return dict(made)


def drop_break(break_id: str, text: str | None = None, now: float | None = None) -> dict[str, Any] | None:
    t = clock.now() if now is None else now
    with _lock:
        st = _load()
        kept, gone = [], None
        for row in st.get("breaks") or []:
            if row.get("id") == break_id and gone is None:
                gone = row
            else:
                kept.append(row)
        st["breaks"] = kept
        if gone is not None and text:
            _event_locked(st, t, "break_end", text)
        _save()
        return gone


def event(kind: str, text: str, now: float | None = None) -> None:
    with _lock:
        _event_locked(_load(), clock.now() if now is None else now, kind, text)
        _save()


def _event_locked(st: dict[str, Any], t: float, kind: str, text: str) -> None:
    rows = [*(st.get("events") or []), {"at": t, "kind": kind, "text": text}]
    st["events"] = rows[-AGENT_EVENTS_KEEP:]
    logger.info("AGENT seat: %s -- %s", kind, text)
