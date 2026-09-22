"""The historical Level 2 holds the replay depth slot a bot's gate reads (QA R44, 2026-09-22).

With GRML's downloaded window loaded and its Level 2 open, ``GET
/api/ibkr/depth`` answered ``[]`` and a bot ``exit_pos`` was refused ``409
BOT_NO_DEPTH_LINE`` "open its Level 2 or record it" -- the historical panel
reads the recorded book from the snapshot and never reserved a slot, while a
capture replay's socket does.
"""
from __future__ import annotations

import pytest

from archive import db
from bot.eligibility import holds_depth_line
from ibkr.depth import state as depth_state
from sim import history_depth_line as line
from sim import history_playback as playback, history_store as store, session_clock as clock
from sim.mode import reset_for_tests as reset_venue, set_venue

DAY = "2026-09-18"


@pytest.fixture(autouse=True)
def replay_desk(tmp_path, monkeypatch):
    monkeypatch.setenv("NOVA_SIM_HISTORY_DIR", str(tmp_path / "history"))
    monkeypatch.setattr(db, "cache_dir", lambda: tmp_path)
    db.init_db()
    reset_venue()
    clock.reset_for_tests()
    playback.clear()
    depth_state.reset_all()
    set_venue("sim")
    spec = store.window("IMCC", DAY, "04:00", "09:30")
    job = store.create(spec, "trades")
    store.commit_page(job["id"], spec["start_ts"], [dict(ts=spec["start_ts"] + 10, price=10.0, size=100)],
                      spec["end_ts"], True)
    playback.select(spec)
    clock.set_paused(True)
    yield
    depth_state.reset_all()
    playback.clear()
    clock.reset_for_tests()
    reset_venue()


def test_the_open_historical_level2_holds_the_slot_a_bot_needs() -> None:
    assert holds_depth_line("IMCC") is False
    out = line.hold("imcc")
    assert out["ok"] and out["held"] and "IMCC" in out["symbols"]
    assert holds_depth_line("IMCC") is True
    assert depth_state.is_live("IMCC") is False  # a slot, never an IBKR line


def test_only_the_loaded_symbol_on_a_replay_desk_may_hold_one() -> None:
    assert line.hold("SPY")["ok"] is False and holds_depth_line("SPY") is False
    set_venue("paper")
    assert line.hold("IMCC") == {"ok": False, "held": False, "reason": "not a replay desk", "symbols": []}


def test_closing_the_panel_lets_go_unless_a_socket_still_watches() -> None:
    line.hold("IMCC")
    depth_state.ws_viewer_opened("IMCC")
    assert line.release("IMCC")["held"] is True
    depth_state.ws_viewer_closed("IMCC")
    assert line.release("IMCC")["held"] is False
    assert holds_depth_line("IMCC") is False
