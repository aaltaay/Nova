"""Shared pytest fixtures for the HOD Momo test suite.

``reset_hod_engine_state`` is the canonical engine-reset recipe (previously
duplicated as ``_reset_engine`` in test_hod_momo_engine.py): fresh state
owner, disk configs reloaded, all session collections cleared, warmup grace
escaped, and the module-level metrics volume buffers purged so no state
leaks across tests.
"""
from __future__ import annotations

import time
from collections import defaultdict

import pytest

import hod_momo as hm
import hod_momo_metrics as metrics
from hod_momo_state import HodMomoState


def reset_hod_engine_state() -> None:
    hm.replace_state(HodMomoState())
    hm.load_state()
    state = hm.get_state()
    state.today_alerts = []
    state.pending_consolidation = {}
    state.cooldown = {}
    state.session_highs = {}
    state.session_high_seeded = set()
    state.day_highs = {}
    state.session_high_source = {}
    state.session_high_raised_ts = {}
    state.price_buffer = {}
    state.surge_seeded = set()
    state.pending_surge_seed = set()
    state.ticker_snaps = {}
    state.gate_counters = defaultdict(int)
    state.total_trades_seen = 0
    state.blocklist = set()
    state.startup_ts = time.monotonic() - 10_000
    metrics.clear_volume_buffers()


@pytest.fixture()
def hod_engine():
    """Function-scoped fresh HOD engine; yields the live state object."""
    reset_hod_engine_state()
    yield hm.get_state()
