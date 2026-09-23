"""Shared bot test setup -- Activate + L2 + optional claim/heartbeat.

``ready_l2`` pins the first-pullback read-out to passed and the venue clock
inside the entry window (ADR 027) -- tests about those gates set their own.
It also holds a depth line for each symbol (a reserved slot in
``ibkr.depth.state``), because a bot fires only on an allowlisted symbol whose
line the backend holds (``BOT_NO_DEPTH_LINE``, ADR 020 second pass). Lines are
released by the autouse bot fixture in ``conftest.py``.
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


def ready_l2(
    *,
    brain: str | None = "brain-1",
    heartbeat: bool = True,
    symbols: tuple[str, ...] = ("ABCD",),
    depth_line: bool = True,
    readout_passed: bool = True,
) -> str:
    if readout_passed:
        pass_readout()
    open_entry_window()
    token = issue_arm_token()
    apply_patch({"level": 2}, desk=True, arm_token=token)
    row = load_session()
    row["symbol_allowlist"] = list(symbols)
    row["trader_live"] = list(symbols)
    save_session(row)
    if depth_line:
        hold_depth_line(*symbols)
    if brain:
        require_l2_brain(brain, claim=True)
        if heartbeat:
            record_heartbeat(brain)
    return token


def pass_readout() -> None:
    from bot.gates import passed_readout_for_tests, set_readout_for_tests

    set_readout_for_tests(passed_readout_for_tests())


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
    "open_entry_window",
    "pass_readout",
    "ready_l2",
    "release_depth_lines",
]
