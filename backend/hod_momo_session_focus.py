"""Session-focus sticky L1 — keep evaluated / alerted names on the tape.

Warrior HOD names that cool off the gainer table (TRT-class) must not lose
their snap the moment they drop out of TOP_PERC_GAIN. Sticky membership is
driven only by Nova's own IBKR evaluations and today's alerts — never Warrior
rows.

Capacity rule: sticky length == reserved session_focus slots. Hot soft-block
names still on the mover tables are ranked *after* cooled stickies so they
cannot starve TRT-class empty snaps.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import hod_momo_state as _state
from constants import (
    HOD_MOMO_FORMER_MOMO_STRATEGY_ID,
    HOD_MOMO_SESSION_FOCUS_MAX,
)
from paths import cache_dir

logger = logging.getLogger(__name__)

_sticky: list[str] = []
_sticky_date: str = ""
_STICKY_FILE = "hod-momo-session-focus.json"


def _path() -> Path:
    return cache_dir() / _STICKY_FILE


def _sticky_cap() -> int:
    return max(1, int(HOD_MOMO_SESSION_FOCUS_MAX))


def _mover_covered_symbols() -> set[str]:
    """Symbols that already have a mover-table path to L1 (need sticky less)."""
    try:
        from runtime_state import get_runtime_state

        st = get_runtime_state()
    except Exception:
        return set()
    out: set[str] = set()
    for rows in (
        getattr(st, "gainer_cache", None),
        getattr(st, "gapper_cache", None),
        getattr(st, "afterhours_cache", None),
        getattr(st, "loser_cache", None),
    ):
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            sym = (row.get("symbol") or "").strip().upper()
            if sym:
                out.add(sym)
    return out


def _rank_sticky(symbols: list[str]) -> list[str]:
    """Cooled stickies first — they are the ones that otherwise get empty snaps."""
    covered = _mover_covered_symbols()
    cooled: list[str] = []
    hot: list[str] = []
    seen: set[str] = set()
    for raw in symbols:
        sym = (raw or "").strip().upper()
        if not sym or sym in seen:
            continue
        seen.add(sym)
        if sym in covered:
            hot.append(sym)
        else:
            cooled.append(sym)
    return cooled + hot


def clear_session_focus(*, persist: bool = True) -> None:
    """Drop sticky symbols (session rollover / tests)."""
    global _sticky, _sticky_date
    from hod_momo_session import current_date_et

    _sticky = []
    # Mark today as loaded-empty so _ensure_loaded will not revive disk.
    _sticky_date = current_date_et()
    if persist:
        _save()


def sticky_symbols() -> list[str]:
    _ensure_loaded()
    return _rank_sticky(list(_sticky))[: _sticky_cap()]


def remember_session_focus(symbol: str, *, persist: bool = True) -> bool:
    """Pin symbol for reserved session-focus L1. Returns True if newly added."""
    global _sticky
    sym = (symbol or "").strip().upper()
    if not sym:
        return False
    _ensure_loaded()
    already = sym in _sticky
    # Newest soft-block goes first among its cohort; cooled-first re-rank + cap
    # keeps TRT-class off-table names ahead of hot mover soft-blocks.
    merged = [sym, *[s for s in _sticky if s != sym]]
    _sticky = _rank_sticky(merged)[: _sticky_cap()]
    if persist:
        _save()
    return not already


def session_focus_extra_symbols() -> list[str]:
    """Keep alerted + sticky names in the focus *universe* (not just active)."""
    out: list[str] = []
    seen: set[str] = set()

    def _add(sym: str) -> None:
        s = (sym or "").strip().upper()
        if s and s not in seen:
            seen.add(s)
            out.append(s)

    state = _state.get_state()
    for alert in state.today_alerts:
        _add(getattr(alert, "ticker", None) or "")
    for sym in sticky_symbols():
        _add(sym)
    cfg = state.configs.get(HOD_MOMO_FORMER_MOMO_STRATEGY_ID)
    for raw in (cfg.former_momo_list if cfg else []) or []:
        _add(raw)
    return out


def session_focus_active_priority() -> list[str]:
    """Ranked reserved L1 pool: cooled sticky, hot sticky, alerts, Former.

    Cooled sticky first — TRT-class left the gainer table and otherwise goes
    empty-snap. Hot sticky (still on movers) already compete for mover/seed
    slots; ranking them first starved cooled L1. Alerts next, Former last
    (strategy off by default).
    """
    out: list[str] = []
    seen: set[str] = set()

    def _add(sym: str) -> None:
        s = (sym or "").strip().upper()
        if s and s not in seen:
            seen.add(s)
            out.append(s)

    state = _state.get_state()
    for sym in sticky_symbols():
        _add(sym)
    # Newest alerts first among the alert cohort.
    for alert in reversed(list(state.today_alerts)):
        _add(getattr(alert, "ticker", None) or "")
    cfg = state.configs.get(HOD_MOMO_FORMER_MOMO_STRATEGY_ID)
    for raw in (cfg.former_momo_list if cfg else []) or []:
        _add(raw)
    return out


def _ensure_loaded() -> None:
    global _sticky, _sticky_date
    from hod_momo_session import current_date_et

    today = current_date_et()
    if _sticky_date == today and _sticky is not None:
        return
    _sticky_date = today
    _sticky = []
    path = _path()
    if not path.is_file():
        return
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("HOD Momo: session-focus sticky load failed: %s", exc)
        return
    if str(raw.get("date") or "") != today:
        return
    seen: set[str] = set()
    ordered: list[str] = []
    for item in raw.get("symbols") or []:
        sym = str(item or "").strip().upper()
        if sym and sym not in seen:
            seen.add(sym)
            ordered.append(sym)
    # Rank then cap — do not truncate disk order before cooled-first, or TRT
    # at the end of a flooded sticky file never recovers a slot.
    _sticky = _rank_sticky(ordered)[: _sticky_cap()]


def _save() -> None:
    from hod_momo_session import current_date_et

    global _sticky_date
    _sticky_date = current_date_et()
    payload = {"date": _sticky_date, "symbols": list(_sticky)}
    try:
        _path().write_text(json.dumps(payload), encoding="utf-8")
    except OSError as exc:
        logger.warning("HOD Momo: session-focus sticky save failed: %s", exc)


