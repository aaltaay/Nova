"""Shared bot test setup -- the master at Strategy, setups at Strategy, Activate, optional claim/heartbeat.

``ready_l2`` pins the venue clock inside the entry window (ADR 027) -- tests about
that gate set their own. It puts the named setups at Strategy (ADR 042: the master
is a ceiling, each setup has its own level), writes this venue's bot list directly
(tests bypass stock mode's one-owner path; the routes go through it) and lists the
stocks on today's hot list (ADR 044: Nova buys only listed stocks), and holds a
depth line for each symbol (a reserved slot in ``ibkr.depth.state``), because a bot
fires only on a listed symbol whose line the backend holds (``BOT_NO_DEPTH_LINE``,
ADR 020 second pass). Lines are released by the autouse bot fixture in ``conftest.py``.
"""
from __future__ import annotations

from types import ModuleType

from bot.arming import issue_arm_token, record_heartbeat
from bot.autonomy import apply_desk_level, apply_patch
from bot.persist import load_session, save_session
from bot.session import require_l2_brain

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
    """Put these stocks on today's hot list (ADR 044: Nova buys only listed stocks), written as the
    contract's ``hot-list.json`` (schema 1) in the test's operator cache."""
    import json
    import time

    from constants_hot_list import (
        HOT_LIST_AUTO_N_DEFAULT,
        HOT_LIST_DEFAULT_SIDE,
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
               "default": {"buy": HOT_LIST_DEFAULT_SIDE, "sell": HOT_LIST_DEFAULT_SIDE}, "entries": [],
               "yesterday": []}
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
    """Write this venue's bot list directly (and the Trader focus the Eyes gate reads), and list the
    stocks on today's hot list: Nova buys only listed stocks (ADR 044)."""
    row = load_session()
    row["symbol_allowlist"] = [s.upper() for s in symbols]
    row["trader_live"] = [s.upper() for s in symbols]
    save_session(row)
    list_hot(*symbols)


def ready_l2(
    *,
    brain: str | None = "brain-1",
    heartbeat: bool = True,
    symbols: tuple[str, ...] = ("ABCD",),
    depth_line: bool = True,
    setups: tuple[str, ...] = ("first_pullback",),
    activate: bool = True,
) -> str | None:
    """On a practice venue (Paper unless the test chose Sim; ADR 042: Nova's bot never trades Live), the
    master and ``setups`` at Strategy, ``symbols`` on the bot list, Activate on (its token)."""
    on_practice()
    open_entry_window()
    apply_patch({"level": 2, "setup_levels": {s: 2 for s in setups}}, desk=True)
    set_symbols(*symbols)
    token = issue_arm_token() if activate else None
    if depth_line:
        hold_depth_line(*symbols)
    if brain:
        require_l2_brain(brain, claim=True)
        if heartbeat:
            record_heartbeat(brain)
    return token


def open_entry_window(hour: int = 9, minute: int = 0) -> None:
    """Pin the venue clock inside the material's 07:00-10:00 ET entry window."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from bot import entry_rules

    at = datetime.now(ZoneInfo("America/New_York")).replace(hour=hour, minute=minute, second=0, microsecond=0)
    entry_rules.set_clock_for_tests(lambda: at)


def headers(api_key: str, *, arm: str | None = None, brain: str | None = None) -> dict[str, str]:
    from constants import NOVA_API_KEY_HEADER
    from constants_bot import BOT_DESK_ARM_HEADER

    out = {NOVA_API_KEY_HEADER: api_key}
    if arm:
        out[BOT_DESK_ARM_HEADER] = arm
    if brain:
        out["X-Nova-Brain-Session"] = brain
    return out


__all__ = [
    "apply_desk_level",
    "headers",
    "hold_depth_line",
    "list_hot",
    "open_entry_window",
    "ready_l2",
    "release_depth_lines",
    "set_symbols",
]
