"""Shared bot test setup: a held depth line, a practice venue, today's hot list file, the session's level.

ADR 072 retired the strategy bot, Activate and the bot list's writers, so nothing here turns a bot on. What stays
is what the bot API's door and the living tests still read: ``hold_depth_line`` (a reserved slot in
``ibkr.depth.state``, released by the autouse bot fixture in ``conftest.py``), ``on_practice``, ``list_hot``,
``set_symbols`` (the session's own fields, written directly), ``set_level`` and ``headers``.
"""
from __future__ import annotations

from types import ModuleType

from bot.persist import load_session, save_session

_HELD_DEPTH_LINES: set[str] = set()
# The real ``ibkr.depth.state``, captured when a line is held (see release).
_DEPTH_STATE: ModuleType | None = None


def hold_depth_line(*symbols: str) -> None:
    """Pretend a Trader Level 2 (or Session Record) holds these symbols' lines."""
    global _DEPTH_STATE
    from ibkr.depth import state as depth_state

    _DEPTH_STATE = depth_state
    for raw in symbols:
        sym = (raw or "").strip().upper()
        if not sym:
            continue
        depth_state.reserve_slot(sym)
        _HELD_DEPTH_LINES.add(sym)


def release_depth_lines() -> None:
    """Drop every line a test held so depth state cannot leak between tests.

    This runs from an autouse teardown after *every* test, so it must not
    import ``ibkr.depth`` itself: a test that stubs ``sys.modules["ibkr.depth"]``
    with a fake (``test_capture_feed_hold.py``) is still stubbed here, because
    pytest orders a conftest's autouse fixtures alphabetically and
    ``_isolate_operator_state`` -- which owns the shared ``monkeypatch`` -- is
    torn down after ``_reset_bot_persist``. Nothing held means nothing to do;
    otherwise the module captured at hold time is the real one.
    """
    if not _HELD_DEPTH_LINES:
        return
    assert _DEPTH_STATE is not None
    for sym in list(_HELD_DEPTH_LINES):
        _DEPTH_STATE.clear_symbol(sym)
    _HELD_DEPTH_LINES.clear()


def on_practice(venue: str = "paper") -> None:
    """Move the desk to a practice venue when it is on Live (the suite's default venue), keeping the
    padlock unlocked there (a venue change locks it)."""
    from ibkr import safety
    from sim.mode import set_venue, venue as desk_venue

    if desk_venue() in ("paper", "sim"):
        return
    set_venue(venue, persist=False)
    safety.set_armed(True, reason="test")


def list_hot(*symbols: str, how: str = "star", at: float | None = None) -> None:
    """Put these stocks on today's hot list, written as the contract's ``hot-list.json`` (schema 1) in the
    test's operator cache. With no stocks it only writes today's file."""
    import json
    import time

    from constants_hot_list import (
        HOT_LIST_AUTO_N_DEFAULT,
        HOT_LIST_FILE,
        HOT_LIST_SCHEMA_VERSION,
    )
    from hot_list import trading_day
    from paths import cache_dir

    path = cache_dir() / HOT_LIST_FILE
    day = trading_day()
    doc = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    if not isinstance(doc, dict) or doc.get("date") != day:
        doc = {"schema_version": HOT_LIST_SCHEMA_VERSION, "date": day, "auto_n": HOT_LIST_AUTO_N_DEFAULT,
               "entries": [], "yesterday": []}
    have = {e["symbol"] for e in doc["entries"]}
    stamp = time.time() if at is None else at
    for raw in symbols:
        sym = (raw or "").strip().upper()
        if sym and sym not in have:
            doc["entries"].append({"symbol": sym, "how": how, "at": stamp, "board": None, "rank": None,
                                   "change_pct": None})
            have.add(sym)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc), encoding="utf-8")


def set_symbols(*symbols: str) -> None:
    """Write this venue's bot list directly (and the Trader focus the Eyes gate reads): the session file's own
    fields, since nothing writes them any more (ADR 072)."""
    row = load_session()
    row["symbol_allowlist"] = [s.upper() for s in symbols]
    row["trader_live"] = [s.upper() for s in symbols]
    save_session(row)


def set_level(level: int) -> dict:
    """Write the desk venue's master ``level`` directly (its PATCH retired with the Bots page, ADR 072)."""
    row = load_session()
    row["level"] = int(level)
    return save_session(row)


def headers(api_key: str, *, brain: str | None = None) -> dict[str, str]:
    from constants import NOVA_API_KEY_HEADER

    out = {NOVA_API_KEY_HEADER: api_key}
    if brain:
        out["X-Nova-Brain-Session"] = brain
    return out


__all__ = [
    "headers",
    "hold_depth_line",
    "list_hot",
    "on_practice",
    "release_depth_lines",
    "set_level",
    "set_symbols",
]
