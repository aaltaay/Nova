"""The Live Trader bots' settings: each host's key, Entry / Exit and money rules, and the sell-all time.

Persisted: ``live-trader-bots.json`` in the operator cache (``LT_SETTINGS_FILE``). Owner: this module -- it reads
the file once and writes it through a temp file and a rename on every change. Invalidation: none by time (they are
the operator's choices); a ``schema_version`` other than ``LT_SETTINGS_SCHEMA_VERSION``, or a file that cannot be
read, is refused loud: every host reads key off (the bot opens nothing), the error is on the view, and writes
answer 409 ``LIVE_TRADER_SETTINGS_UNREADABLE`` instead of overwriting it. A host missing from the file reads key off
with the operator's defaults of 2026-10-14. Shapes: architecture/schema/bot.md ("The Live Trader bot").
"""
from __future__ import annotations

import json
import logging
import os
import re
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

from bot.live_trader.constants_live_trader import (
    LT_ADDS_CHOICES,
    LT_ALLOWANCE_USD_BOUNDS,
    LT_DEFAULT_ADDS,
    LT_DEFAULT_ALLOWANCE_USD,
    LT_DEFAULT_ENTRY,
    LT_DEFAULT_EXIT,
    LT_DEFAULT_KEY,
    LT_DEFAULT_LOT_USD,
    LT_DEFAULT_SELL_ALL_AT,
    LT_DEFAULT_SHORT_STOP_PCT,
    LT_DEFAULT_SIDES,
    LT_DEFAULT_STEP_USD,
    LT_DEFAULT_TAKE_OPEN,
    LT_ERR_INVALID,
    LT_ERR_SETTINGS_UNREADABLE,
    LT_LOT_USD_BOUNDS,
    LT_NAME_MAX,
    LT_SELL_ALL_BOUNDS,
    LT_SETTINGS_FILE,
    LT_SETTINGS_SCHEMA_VERSION,
    LT_SHORT_STOP_PCT_BOUNDS,
    LT_SIDES,
    LT_STEP_USD_BOUNDS,
)
from constants_stock_mode import STOCK_MODE_SIDES

logger = logging.getLogger(__name__)
NAME_RE = re.compile(rf"^[A-Z0-9]{{1,{LT_NAME_MAX}}}$")
HHMM_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
FIELDS = ("key", "entry", "exit", "step_usd", "adds", "allowance_usd", "sides", "short_stop_pct", "take_open",
          "lot_usd")

_lock = threading.Lock()
_state: dict[str, Any] | None = None       # the file as read: {"sell_all_at", "hosts"}
_error: str | None = None                  # why the file was refused, while it is


class SettingsError(Exception):
    def __init__(self, code: str, message: str, *, status: int = 400, field: str | None = None) -> None:
        super().__init__(message)
        self.code, self.message, self.status, self.field = code, message, status, field


def defaults() -> dict[str, Any]:
    return {"key": LT_DEFAULT_KEY, "entry": LT_DEFAULT_ENTRY, "exit": LT_DEFAULT_EXIT,
            "step_usd": LT_DEFAULT_STEP_USD, "adds": LT_DEFAULT_ADDS, "allowance_usd": LT_DEFAULT_ALLOWANCE_USD,
            "sides": LT_DEFAULT_SIDES, "short_stop_pct": LT_DEFAULT_SHORT_STOP_PCT,
            "take_open": LT_DEFAULT_TAKE_OPEN, "lot_usd": LT_DEFAULT_LOT_USD}


def bounds() -> dict[str, Any]:
    return {"step_usd": list(LT_STEP_USD_BOUNDS), "allowance_usd": list(LT_ALLOWANCE_USD_BOUNDS),
            "lot_usd": list(LT_LOT_USD_BOUNDS),
            "adds": list(LT_ADDS_CHOICES), "sides": list(LT_SIDES), "short_stop_pct": list(LT_SHORT_STOP_PCT_BOUNDS),
            "sell_all_at": list(LT_SELL_ALL_BOUNDS), "entry": list(STOCK_MODE_SIDES), "exit": list(STOCK_MODE_SIDES)}


def reset_for_tests() -> None:
    global _state, _error
    with _lock:
        _state, _error = None, None


def _path() -> Path:
    from paths import cache_dir

    return cache_dir() / LT_SETTINGS_FILE


def _load_locked() -> dict[str, Any]:
    global _state, _error
    if _state is not None:
        return _state
    _state, _error = {"sell_all_at": LT_DEFAULT_SELL_ALL_AT, "hosts": {}}, None
    path = _path()
    if not path.exists():
        return _state
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        _error = f"{path.name} could not be read ({type(exc).__name__}): every host reads off until it is fixed"
        logger.exception("Live Trader bot: %s", _error)
        return _state
    if not isinstance(raw, dict) or raw.get("schema_version") != LT_SETTINGS_SCHEMA_VERSION:
        version = raw.get("schema_version") if isinstance(raw, dict) else None
        _error = (f"{path.name} has schema_version {version!r}, not {LT_SETTINGS_SCHEMA_VERSION}: refused, "
                  "not overwritten -- every host reads off")
        logger.error("Live Trader bot: %s", _error)
        return _state
    hosts = {}
    for name, row in (raw.get("hosts") or {}).items():
        try:
            hosts[_name(name)] = _clean(row, field_prefix=name)
        except SettingsError as exc:
            logger.warning("Live Trader bot: %s's settings skipped (%s); its defaults stand", name, exc.message)
    sell = raw.get("sell_all_at")
    _state = {"sell_all_at": sell if _sell_all_ok(sell) else LT_DEFAULT_SELL_ALL_AT, "hosts": hosts}
    return _state


def _save_locked(state: dict[str, Any]) -> None:
    path = _path()
    payload = {"schema_version": LT_SETTINGS_SCHEMA_VERSION, "sell_all_at": state["sell_all_at"],
               "hosts": state["hosts"]}
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=1)
        os.replace(tmp, path)
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            logger.warning("Live Trader bot: the temp file %s was not removed", tmp)
        raise


def error() -> str | None:
    with _lock:
        _load_locked()
        return _error


def of(name: str) -> dict[str, Any]:
    """A host's settings: the file's, else the defaults (key off). A refused file reads every key off."""
    with _lock:
        state = _load_locked()
        row = dict(defaults(), **state["hosts"].get(name, {}))
        if _error is not None:
            row["key"] = False
        return row


def sell_all_at() -> str:
    with _lock:
        return str(_load_locked()["sell_all_at"])


def hosts_on() -> list[str]:
    """The hosts whose key is on."""
    with _lock:
        state = _load_locked()
        return [] if _error is not None else [n for n, row in state["hosts"].items() if row.get("key")]


def named() -> list[str]:
    """Every host with settings in the file."""
    with _lock:
        return list(_load_locked()["hosts"])


def _name(raw: Any) -> str:
    name = str(raw or "").strip().upper()
    if not NAME_RE.match(name):
        raise SettingsError(LT_ERR_INVALID, f"a host's name is 1 to {LT_NAME_MAX} of A-Z and 0-9", field="name")
    return name


def _number(row: dict[str, Any], key: str, lo: float, hi: float) -> float:
    value = row.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not lo <= float(value) <= hi:
        raise SettingsError(LT_ERR_INVALID, f"{key} is a number from {lo:g} to {hi:g}", field=key)
    return float(value)


def _clean(row: Any, *, field_prefix: str = "") -> dict[str, Any]:
    """A stored host row, every field checked; the missing ones are the defaults."""
    if not isinstance(row, dict):
        raise SettingsError(LT_ERR_INVALID, f"{field_prefix or 'a host'}'s settings are not an object")
    out = defaults()
    out.update({k: row[k] for k in FIELDS if k in row})
    return {**_checked(out), "updated_at": row.get("updated_at")}


def _checked(row: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(row["key"], bool) or not isinstance(row["take_open"], bool):
        raise SettingsError(LT_ERR_INVALID, "key and take_open are true or false", field="key")
    for side in ("entry", "exit"):
        if row[side] not in STOCK_MODE_SIDES:
            raise SettingsError(LT_ERR_INVALID, f"{side} is 'you' or 'nova'", field=side)
    if row["sides"] not in LT_SIDES:
        raise SettingsError(LT_ERR_INVALID, "sides is 'long' or 'both'", field="sides")
    if row["adds"] not in LT_ADDS_CHOICES or isinstance(row["adds"], bool):
        raise SettingsError(LT_ERR_INVALID, "adds is 0, 2, 4 or null (every add)", field="adds")
    return {**row, "step_usd": _number(row, "step_usd", *LT_STEP_USD_BOUNDS),
            "allowance_usd": _number(row, "allowance_usd", *LT_ALLOWANCE_USD_BOUNDS),
            "short_stop_pct": _number(row, "short_stop_pct", *LT_SHORT_STOP_PCT_BOUNDS),
            "lot_usd": _number(row, "lot_usd", *LT_LOT_USD_BOUNDS)}


def _sell_all_ok(value: Any) -> bool:
    lo, hi = LT_SELL_ALL_BOUNDS
    return isinstance(value, str) and bool(HHMM_RE.match(value)) and lo <= value <= hi


def _writable_locked() -> dict[str, Any]:
    state = _load_locked()
    if _error is not None:
        raise SettingsError(LT_ERR_SETTINGS_UNREADABLE, _error, status=409)
    return state


def patch_host(name: str, body: dict[str, Any], *, now: float | None = None) -> tuple[dict, dict]:
    """``(before, after)`` for one host; raises ``SettingsError`` and changes nothing on any bad field."""
    global _state
    host = _name(name)
    unknown = sorted(set(body) - set(FIELDS))
    if unknown:
        raise SettingsError(LT_ERR_INVALID, f"unknown field {unknown[0]!r}", field=unknown[0])
    with _lock:
        state = _writable_locked()
        before = dict(defaults(), **state["hosts"].get(host, {}))
        after = _checked({**before, **body})
        after["updated_at"] = round(time.time() if now is None else now, 3)
        hosts = dict(state["hosts"])
        hosts[host] = {k: after[k] for k in (*FIELDS, "updated_at")}
        new_state = {**state, "hosts": hosts}
        _save_locked(new_state)
        _state = new_state
        return before, dict(after)


def patch_sell_all(value: Any) -> tuple[str, str]:
    global _state
    if not _sell_all_ok(value):
        lo, hi = LT_SELL_ALL_BOUNDS
        raise SettingsError(LT_ERR_INVALID, f"sell_all_at is HH:MM ET from {lo} to {hi}", field="sell_all_at")
    with _lock:
        state = _writable_locked()
        before = state["sell_all_at"]
        new_state = {**state, "sell_all_at": value}
        _save_locked(new_state)
        _state = new_state
        return before, value
