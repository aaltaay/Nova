"""The operator's daily loss limit setting: three lines, Warn me, No new buys, Auto sell (ADR 056, ADR 061).

The file ``loss-limit.json`` in the operator cache (``architecture/schema/loss-limit.md``):
``{schema_version: 2, limit_usd, you_usd, bots_usd, warn, no_new_buys, auto_sell, set_at}``.
``limit_usd`` is the Account line; ``you_usd`` and ``bots_usd`` are your trades' and the bots'
lines, null for no line. Owner: this module. Invalidation: rewritten whole on every change.

No file reads the defaults ($2,000 on the Account line, no You or Bots line, Warn me and No new
buys on, Auto sell off). A version 1 file -- the one line ADR 056 saved -- reads as that Account
line with its checkboxes unchanged and no You or Bots line; the next save writes version 2. An
unknown version or an unreadable file reads the defaults, logged and stated in ``error`` -- never
a silent guess -- and the next save writes a fresh file.
"""
from __future__ import annotations

import json
import logging
import math
import threading
import time
from pathlib import Path
from typing import Any

from constants_loss_limit import (
    LOSS_LIMIT_DEFAULT_AUTO_SELL,
    LOSS_LIMIT_DEFAULT_NO_NEW_BUYS,
    LOSS_LIMIT_DEFAULT_USD,
    LOSS_LIMIT_DEFAULT_WARN,
    LOSS_LIMIT_FILE,
    LOSS_LIMIT_LINE_ACCOUNT,
    LOSS_LIMIT_LINE_KEYS,
    LOSS_LIMIT_MAX_USD,
    LOSS_LIMIT_MIN_USD,
    LOSS_LIMIT_SCHEMA_VERSION,
    LOSS_LIMIT_SIDES,
)

logger = logging.getLogger(__name__)

FLAGS = ("warn", "no_new_buys", "auto_sell")
SIDE_KEYS = tuple(LOSS_LIMIT_LINE_KEYS[side] for side in LOSS_LIMIT_SIDES)    # you_usd, bots_usd
_KEYS = ("limit_usd", *SIDE_KEYS, *FLAGS)
_V1 = 1
_NAMES = {"limit_usd": "The daily loss limit", "you_usd": "Your trades' limit", "bots_usd": "The bots' limit"}

_lock = threading.Lock()
_loaded_from: Path | None = None
_saved: dict[str, Any] | None = None    # None with no file, or one this build cannot use
_error: str | None = None


class Invalid(ValueError):
    """A change this setting refuses; the message says the rule."""


def defaults() -> dict[str, Any]:
    return {"limit_usd": LOSS_LIMIT_DEFAULT_USD, **{key: None for key in SIDE_KEYS},
            "warn": LOSS_LIMIT_DEFAULT_WARN, "no_new_buys": LOSS_LIMIT_DEFAULT_NO_NEW_BUYS,
            "auto_sell": LOSS_LIMIT_DEFAULT_AUTO_SELL}


def line_limit(current: dict[str, Any], line: str) -> int | None:
    """``line``'s dollars in ``current`` (``current()``'s shape); None when that line is off."""
    value = current.get(LOSS_LIMIT_LINE_KEYS[line])
    return None if value is None else int(value)


def path() -> Path:
    from paths import cache_dir

    return cache_dir() / LOSS_LIMIT_FILE


def _limit_problem(value: Any, key: str = "limit_usd") -> str | None:
    name = _NAMES[key]
    if value is None and key != "limit_usd":
        return None                                  # no You or Bots line
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return f"{name} is a dollar amount" + ("" if key == "limit_usd" else ", or null for no line")
    if value != int(value):
        return f"{name} is whole dollars"
    if not LOSS_LIMIT_MIN_USD <= value <= LOSS_LIMIT_MAX_USD:
        return f"{name} is between ${LOSS_LIMIT_MIN_USD:,} and ${LOSS_LIMIT_MAX_USD:,}"
    return None


def read(at: Path) -> tuple[dict[str, Any] | None, str | None]:
    """``(saved, error)``: ``(None, None)`` with no file; ``(None, why)`` for one this build cannot use."""
    try:
        doc = json.loads(at.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, None
    except (OSError, ValueError) as exc:
        logger.warning("LOSS LIMIT: %s is unreadable -- the defaults apply", at, exc_info=True)
        return None, f"Nova could not read the saved loss limit ({type(exc).__name__}), so the defaults apply"
    version = doc.get("schema_version") if isinstance(doc, dict) else None
    if version == _V1:
        # ADR 056's one line is the Account line, unchanged; no You or Bots line until the operator sets one.
        doc = {**doc, **{key: None for key in SIDE_KEYS}}
    elif version != LOSS_LIMIT_SCHEMA_VERSION:
        logger.warning("LOSS LIMIT: %s has schema_version %s; this build reads %s -- the defaults apply",
                       at, version, LOSS_LIMIT_SCHEMA_VERSION)
        return None, (f"The saved loss limit is version {version}; this Nova reads version "
                      f"{LOSS_LIMIT_SCHEMA_VERSION}, so the defaults apply")
    problem = any(_limit_problem(doc.get(key), key) for key in ("limit_usd", *SIDE_KEYS))
    if problem or any(not isinstance(doc.get(flag), bool) for flag in FLAGS):
        logger.warning("LOSS LIMIT: %s holds a value this build cannot use -- the defaults apply", at)
        return None, "The saved loss limit holds a value Nova cannot use, so the defaults apply"
    set_at = doc.get("set_at")
    return {"limit_usd": int(doc["limit_usd"]),
            **{key: None if doc.get(key) is None else int(doc[key]) for key in SIDE_KEYS},
            **{flag: doc[flag] for flag in FLAGS},
            "set_at": float(set_at) if isinstance(set_at, (int, float)) else None}, None


def ensure_loaded() -> None:
    global _loaded_from, _saved, _error
    target = path()
    if _loaded_from == target:
        return
    saved, error = read(target)
    with _lock:
        _loaded_from, _saved, _error = target, saved, error


def current() -> dict[str, Any]:
    """``{limit_usd, you_usd, bots_usd, warn, no_new_buys, auto_sell, set_at, source, error}``."""
    ensure_loaded()
    saved, error = _saved, _error
    if saved is None:
        return {**defaults(), "set_at": None, "source": "default", "error": error}
    return {**saved, "source": "operator", "error": None}


def update(patch: Any, now: float | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    """Apply ``{limit_usd?, you_usd?, bots_usd?, warn?, no_new_buys?, auto_sell?}`` and save; ``(before, after)``.

    ``Invalid`` for a value out of its rule; ``OSError`` when the file cannot be written --
    the setting is then unchanged. Blocking: call it off the event loop."""
    global _loaded_from, _saved, _error
    if not isinstance(patch, dict) or not patch:
        raise Invalid("Send {limit_usd?, you_usd?, bots_usd?, warn?, no_new_buys?, auto_sell?}")
    unknown = sorted(set(patch) - set(_KEYS))
    if unknown:
        raise Invalid(f"Unknown setting {', '.join(unknown)}")
    before = current()
    after = {key: before[key] for key in _KEYS}
    for key in ("limit_usd", *SIDE_KEYS):
        if key in patch:
            problem = _limit_problem(patch[key], key)
            if problem:
                raise Invalid(problem)
            after[key] = None if patch[key] is None else int(patch[key])
    for flag in FLAGS:
        if flag in patch:
            if not isinstance(patch[flag], bool):
                raise Invalid(f"{flag} is true or false")
            after[flag] = patch[flag]
    from capture.manifest_io import write_json_atomic

    ts = time.time() if now is None else float(now)
    target = path()
    write_json_atomic(target, {"schema_version": LOSS_LIMIT_SCHEMA_VERSION, **after, "set_at": ts})
    with _lock:
        _loaded_from, _saved, _error = target, {**after, "set_at": ts}, None
    logger.info("LOSS LIMIT: the operator set %s", after)
    return before, current()


def lines_on(current: dict[str, Any]) -> list[str]:
    """The lines set now: the Account line always, You and Bots when they have dollars."""
    return [LOSS_LIMIT_LINE_ACCOUNT, *(side for side in LOSS_LIMIT_SIDES if line_limit(current, side) is not None)]


def reset_for_tests() -> None:
    global _loaded_from, _saved, _error
    with _lock:
        _loaded_from, _saved, _error = None, None, None
