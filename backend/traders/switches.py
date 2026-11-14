"""Claude's and the brain's On / Off switches (ADR 072 decision 6, ``traders.md`` "The switches").

The file ``trader-switches.json`` in the operator cache, rewritten whole and atomically: ``{schema_version: 1, day,
switches: {claude: {on, at, by}, brain: {on, at, by}}}``. Owner: this module. ``day`` is the desk day the switches
were set on (``market.session_key_for_ts``: 04:00 ET rolls it, a weekend belongs to Friday). A file from an earlier
desk day, a missing one, an unknown version or an unreadable one reads every switch Off -- the last two with
``error`` saying why. A restart within the day reads the file back, so a restart never hands a trade over by itself.

On is refused in words (``on_refusal``); Off never is (``traders.off`` does what Off means).
"""
from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any

from constants_owners import AI_TRADERS, OWNER_CLAUDE, OWNER_NAMES
from constants_traders import (
    TRADER_DAY_STOP,
    TRADER_LIVE,
    TRADER_PAST_FLAT_BY,
    TRADER_SWITCHES_FILE,
    TRADER_SWITCHES_SCHEMA_VERSION,
)

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_OFF: dict[str, Any] = {"on": False, "at": None, "by": None}


def path() -> Path:
    from paths import cache_dir

    return cache_dir() / TRADER_SWITCHES_FILE


def now_ts() -> float:
    """The desk's clock: Nova's ET clock (``market.now_et``), the one its trading day rolls on."""
    from market import now_et

    return now_et().timestamp()


def desk_day(now: float | None = None) -> str:
    from market import session_key_for_ts

    return session_key_for_ts(now_ts() if now is None else float(now))


def _read() -> tuple[dict[str, Any] | None, str | None]:
    try:
        doc = json.loads(path().read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, None
    except (OSError, ValueError) as exc:
        logger.warning("TRADERS: %s is unreadable -- every switch reads Off", path(), exc_info=True)
        return None, f"Nova could not read the switches ({type(exc).__name__}), so Claude and the brain read Off"
    version = doc.get("schema_version") if isinstance(doc, dict) else None
    if version != TRADER_SWITCHES_SCHEMA_VERSION:
        logger.warning("TRADERS: %s has schema_version %s -- every switch reads Off", path(), version)
        return None, (f"The saved switches are version {version}; this Nova reads version "
                      f"{TRADER_SWITCHES_SCHEMA_VERSION}, so Claude and the brain read Off")
    return doc, None


def _write(day: str, switches: dict[str, dict[str, Any]]) -> None:
    from capture.manifest_io import write_json_atomic

    write_json_atomic(path(), {"schema_version": TRADER_SWITCHES_SCHEMA_VERSION, "day": day, "switches": switches})


def current(now: float | None = None) -> tuple[dict[str, dict[str, Any]], str | None]:
    """``({trader: {on, at, by}}, error)`` for today's desk day. An earlier day's file reads Off: the 04:00 ET
    rollover writes every switch Off, handing what a trader still held (``handed.hand_held``)."""
    today = desk_day(now)
    with _lock:
        doc, error = _read()
        saved = (doc or {}).get("switches") if isinstance((doc or {}).get("switches"), dict) else {}
        stale = doc is not None and doc.get("day") != today
        out = {t: dict(_OFF) for t in AI_TRADERS}
        if not stale:
            for trader in AI_TRADERS:
                row = saved.get(trader) if isinstance(saved.get(trader), dict) else {}
                out[trader] = {"on": row.get("on") is True, "at": row.get("at"), "by": row.get("by")}
        rolled = [t for t in AI_TRADERS if stale and isinstance(saved.get(t), dict) and saved[t].get("on") is True]
        if stale:
            _write(today, out)
    for trader in rolled:
        logger.info("TRADERS: the desk day rolled to %s -- %s's switch is Off", today, trader)
        from traders import handed

        handed.hand_held(trader, now)
    return out, error


def is_on(trader: str, now: float | None = None) -> bool:
    return bool(current(now)[0].get(trader, {}).get("on"))


def on_refusal(trader: str, now: float | None = None) -> tuple[str, str] | None:
    """``(code, words)`` when ``trader``'s switch may not turn On now, else None."""
    from market import now_et
    from sim.mode import venue

    name = OWNER_NAMES.get(trader, trader)
    if venue() == "live":
        return TRADER_LIVE, f"The desk is on Live: {name} trades Paper and Sim only, so it stays Off."
    if trader == OWNER_CLAUDE and (why := _claude_day_stop()):
        return TRADER_DAY_STOP, why
    from traders import limits

    flat_by = str(limits.of(trader)["flat_by"])
    clock = now_et() if now is None else _et(now)
    if clock.weekday() < 5 and clock.strftime("%H:%M") >= flat_by:
        return TRADER_PAST_FLAT_BY, f"It is past {name}'s flat-by time ({flat_by} ET): it can turn On tomorrow."
    return None


def _et(ts: float) -> Any:
    from datetime import datetime

    from market import ET

    return datetime.fromtimestamp(float(ts), ET)


def _claude_day_stop() -> str | None:
    """Claude's day stop tripped today (its seat's rule until its loss line lands, batch 4); None when it has not, or
    when Paper cannot be read -- the seat refuses each entry itself then (``AGENT_STALE``)."""
    from agent_trader import ledger, rules

    try:
        return rules.day_refusal(0, ledger.day_pnl())
    except ledger.ReadError:
        logger.warning("TRADERS: Paper could not be read for Claude's day stop", exc_info=True)
        return None


def set_switch(trader: str, on: bool, by: str, now: float | None = None) -> dict[str, Any]:
    """Write ``trader``'s switch; returns its new ``{on, at, by}``. The caller has checked ``on_refusal``."""
    t = now_ts() if now is None else float(now)
    switches, _ = current(t)
    switches[trader] = {"on": bool(on), "at": t, "by": by}
    with _lock:
        _write(desk_day(t), switches)
    logger.info("TRADERS: %s's switch %s (%s)", trader, "On" if on else "Off", by)
    return switches[trader]
