"""Shared pytest fixtures for the HOD Momo test suite.

``reset_hod_engine_state`` is the canonical engine-reset recipe (previously
duplicated as ``_reset_engine`` in test_hod_momo_engine.py): fresh state
owner, disk configs reloaded, all session collections cleared, warmup grace
escaped, and the module-level metrics volume buffers purged so no state
leaks across tests.

Cache isolation: ``NOVA_CACHE_DIR`` is set *before* backend imports so modules
that snapshot the cache path at import (``cache._CACHE_DIR``,
``HOD_MOMO_CONFIG_FILE``) never point at the operator ``backend/.cache``.
An autouse fixture then re-pins per test and forces ``IBKR_GATEWAY_MODE=paper``.
"""
from __future__ import annotations

import os
import tempfile
import time
from collections import defaultdict
from pathlib import Path

_SESSION_CACHE = Path(tempfile.mkdtemp(prefix="nova_pytest_cache_"))
os.environ["NOVA_CACHE_DIR"] = str(_SESSION_CACHE)
os.environ["IBKR_GATEWAY_MODE"] = os.environ.get("IBKR_GATEWAY_MODE") or "paper"

import pytest

import cache as cache_mod
import constants_hod_momo as hod_const
import hod_momo as hm
import hod_momo_metrics as metrics
from hod_momo_state import HodMomoState


@pytest.fixture(autouse=True)
def _isolate_operator_state(tmp_path, monkeypatch):
    cache_root = tmp_path / "nova_cache"
    cache_root.mkdir()
    monkeypatch.setenv("NOVA_CACHE_DIR", str(cache_root))
    monkeypatch.setenv("IBKR_GATEWAY_MODE", "paper")
    monkeypatch.setattr(cache_mod, "_CACHE_DIR", str(cache_root), raising=False)
    monkeypatch.setattr(
        cache_mod,
        "_LEGACY_FILES",
        {
            "gappers": str(cache_root / "gappers.json"),
            "movers": str(cache_root / "movers.json"),
            "afterhours": str(cache_root / "afterhours.json"),
        },
        raising=False,
    )
    monkeypatch.setattr(
        hod_const,
        "HOD_MOMO_CONFIG_FILE",
        str(cache_root / "hod-momo-config.json"),
        raising=False,
    )
    monkeypatch.setattr(
        hod_const,
        "HOD_MOMO_BLOCKLIST_FILE",
        str(cache_root / "hod-momo-blocklist.json"),
        raising=False,
    )
    monkeypatch.setattr(
        cache_mod,
        "HOD_MOMO_CONFIG_FILE",
        str(cache_root / "hod-momo-config.json"),
        raising=False,
    )
    monkeypatch.setattr(
        cache_mod,
        "HOD_MOMO_BLOCKLIST_FILE",
        str(cache_root / "hod-momo-blocklist.json"),
        raising=False,
    )
    yield


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
