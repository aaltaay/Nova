"""A surge seed that found no stored bars is asked again while the bars land (2026-10-13: 181 names live-only)."""
from __future__ import annotations

import hod_momo as hm
from constants import HOD_MOMO_SURGE_SEED_RETRY_SEC, HOD_MOMO_SURGE_SEED_RETRY_WINDOW_SEC
from tests.conftest import reset_hod_engine_state


def test_a_live_only_seed_is_asked_again_after_the_retry_period(monkeypatch):
    reset_hod_engine_state()
    state = hm.get_state()
    clock = {"t": 1_000.0}
    monkeypatch.setattr("hod_momo_market.time.time", lambda: clock["t"])

    hm.mark_surge_seed_live("PFAI")
    hm.request_surge_seed("PFAI")
    assert "PFAI" not in state.pending_surge_seed  # not yet

    clock["t"] += HOD_MOMO_SURGE_SEED_RETRY_SEC
    hm.request_surge_seed("PFAI")
    assert "PFAI" in state.pending_surge_seed
    assert "PFAI" not in state.surge_seeded


def test_retries_stop_after_the_window_and_after_a_stored_seed(monkeypatch):
    reset_hod_engine_state()
    state = hm.get_state()
    hm.mark_surge_seed_live("OLD", now=0.0)
    hm.mark_surge_seed_live("OLD", now=HOD_MOMO_SURGE_SEED_RETRY_WINDOW_SEC + 1)
    assert "OLD" not in state.surge_seed_retry_at  # past the window: live for the day

    hm.mark_surge_seed_live("NEW", now=0.0)
    hm.mark_surge_seed_stored("NEW")
    assert "NEW" not in state.surge_seed_retry_at
    assert "NEW" not in state.surge_seed_live_since
