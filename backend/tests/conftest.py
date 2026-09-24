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

Operator isolation (#293, #307): the same "before backend imports" rule covers
the operator's logs and ``.env``. ``main.py`` runs ``configure_logging()`` and
``load_dotenv(env_file_path())`` as *import* side effects, so without these
pins a plain ``pytest backend/`` appends fake broker lines (``account=DU123``)
to the production ``backend/logs/blast.log`` and reads the operator's real
``NOVA_API_KEY``, which flips the no-key route tests to 401. ``NOVA_LOG_DIR``
and ``NOVA_ENV_PATH`` move both under a throwaway temp dir, and ``NOVA_API_KEY``
is dropped so a test run means the same thing on every machine. Tests that want
a key set their own (see ``test_auth.py``).
"""
from __future__ import annotations

import os
import tempfile
import time
from collections import defaultdict
from pathlib import Path

_SESSION_CACHE = Path(tempfile.mkdtemp(prefix="nova_pytest_cache_"))
os.environ["NOVA_CACHE_DIR"] = str(_SESSION_CACHE)
_SESSION_LOGS = Path(tempfile.mkdtemp(prefix="nova_pytest_logs_"))
os.environ["NOVA_LOG_DIR"] = str(_SESSION_LOGS)
# Never created: load_dotenv on a missing path is a no-op, which is exactly the
# point -- importing main.py must not pull the operator's .env into os.environ.
os.environ["NOVA_ENV_PATH"] = str(_SESSION_CACHE / "pytest-never-written.env")
os.environ.pop("NOVA_API_KEY", None)
# The operator's data archives default to F:\Nova\... when F: is mounted. A
# test run on the desk machine resolved the live capture root there and its
# startup finalizer stamped the desk's live recordings "restart" (2026-09-23).
_OPERATOR_DATA_DIRS = {
    "NOVA_SIM_CAPTURE_DIR": "sim_capture",
    "NOVA_SIM_HISTORY_DIR": "sim_history",
    "NOVA_CATALYST_DIR": "catalysts",
    "NOVA_LEADERBOARD_DIR": "leaderboard",
    "NOVA_EYES_DIR": "eyes",
}
for _env, _name in _OPERATOR_DATA_DIRS.items():
    os.environ[_env] = str(_SESSION_CACHE / _name)
os.environ["IBKR_GATEWAY_MODE"] = os.environ.get("IBKR_GATEWAY_MODE") or "paper"
# ADR 026: a test that boots the app must not leave the performance recorder's
# watcher and writer threads running for the rest of the session; the perf
# tests drive those modules directly (and runtime.start under their own switch).
os.environ["NOVA_PERF"] = "0"
# ADR 028: an app a test boots must not poll IBKR's short-stock file; the borrow tests drive the feed directly.
os.environ["NOVA_BORROW_FEED"] = "0"
# ADR 029: an app a test boots must not start the eyes' journal writer; the journal tests drive it directly.
os.environ["NOVA_EYES_JOURNAL"] = "0"

import pytest

import cache as cache_mod
import constants_hod_momo as hod_const
import hod_momo as hm
import hod_momo_metrics as metrics
from hod_momo_state import HodMomoState


@pytest.fixture(autouse=True)
def _reset_bot_persist():
    from bot import entry_rules
    from bot.gates import set_readout_for_tests
    from bot.persist import reset_for_tests
    from setup_scanner import readout
    from tests.bot_helpers import open_entry_window, pass_readout, release_depth_lines

    reset_for_tests()
    readout.reset_for_tests()
    # ADR 027 baseline: the first-pullback read-out passed and the venue clock
    # inside the entry window, so bot tests exercise their own gate. The tests
    # about the read-out and the entry rules close them explicitly.
    pass_readout()
    open_entry_window()
    yield
    reset_for_tests()
    set_readout_for_tests(None)
    entry_rules.set_clock_for_tests(None)
    readout.reset_for_tests()
    # Depth lines a bot test held (ready_l2 / hold_depth_line) must not leak
    # into the next test's BOT_NO_DEPTH_LINE gate.
    release_depth_lines()


@pytest.fixture(autouse=True)
def _reset_kill_switch():
    # The latch is cached in memory; re-read it from each test's own cache dir.
    import kill_switch

    kill_switch.reset_for_tests()
    yield
    kill_switch.reset_for_tests()


class _EveryVenue(str):
    """A venue stamp equal to every venue -- the suite's default arm only."""

    def __eq__(self, other: object) -> bool:
        return isinstance(other, str)

    __hash__ = str.__hash__


@pytest.fixture(autouse=True)
def _isolate_operator_state(tmp_path, monkeypatch):
    cache_root = tmp_path / "nova_cache"
    cache_root.mkdir()
    log_root = tmp_path / "nova_logs"
    log_root.mkdir()
    monkeypatch.setenv("NOVA_CACHE_DIR", str(cache_root))
    # Re-pin per test so anything resolving paths lazily (fill_audit's
    # fill-latency.jsonl, hod_momo_trade) stays out of backend/logs/ even if an
    # earlier test wrote os.environ directly.
    monkeypatch.setenv("NOVA_LOG_DIR", str(log_root))
    monkeypatch.setenv("NOVA_ENV_PATH", str(tmp_path / "nova.env"))
    # The leaderboard store, the capture root, the historical downloads and the
    # catalyst stores default to F:\Nova\... when F: is mounted; a test must
    # never read or write the operator's archives (ADR 023, 2026-09-23).
    for env, name in _OPERATOR_DATA_DIRS.items():
        monkeypatch.setenv(env, str(tmp_path / name))
    monkeypatch.delenv("NOVA_API_KEY", raising=False)
    # A developer shell's Finnhub key would send the catalyst reads (catalysts/live_finnhub.py) to the network.
    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
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
    monkeypatch.setattr(
        cache_mod,
        "LARGE_CAP_CONFIG_FILE",
        str(cache_root / "large-cap-config.json"),
        raising=False,
    )
    monkeypatch.setattr(
        cache_mod,
        "CHART_DRAWINGS_FILE",
        str(cache_root / "chart-drawings.json"),
        raising=False,
    )
    import chart_drawings as _chart_drawings
    import execution.inflight as _inflight
    import large_cap_admin as _large_cap_admin
    import large_cap_alerts as _large_cap_alerts
    import large_cap_metrics as _large_cap_metrics
    from ibkr import halt_status as _halt_status
    from ibkr import nasdaq_halt_feed as _nasdaq_halt_feed

    # Position commitments are process-global; a working order left behind by
    # one module would refuse the next module's SELL (ADR 007 / D-011).
    _inflight.reset_for_tests()
    _chart_drawings.reset_for_testing()
    _large_cap_admin.reset_for_testing()
    _large_cap_alerts.reset_for_testing()
    _large_cap_metrics.reset_for_testing()
    _halt_status.reset()
    _nasdaq_halt_feed.reset()
    import bot as _bot

    _bot.reset_for_tests()
    # ADR 029: the template store and the eyes' journal are process singletons; each
    # test reads its own cache dir.
    from eyes import journal as _eyes_journal
    from eyes.sim_eyes import reset_for_tests as _reset_sim_eyes
    from setup_templates.store import set_store_for_tests as _reset_templates

    _reset_templates(None)
    _eyes_journal.reset_for_tests()
    _reset_sim_eyes()
    from sim.mode import reset_for_tests as _reset_sim
    import execution.flatten_exit as _flatten_exit
    import ibkr.trading_allowed as _trading_allowed

    _reset_sim()
    monkeypatch.delenv("NOVA_BROKER", raising=False)
    # Saturday CI / weekend agent runs must not flip existing flatten tests to EH.
    monkeypatch.setattr(_flatten_exit, "flatten_needs_extended_hours", lambda now=None: False)
    # Same reason for the market-order clock (execution/session_gate.py): the
    # suite places MKTs at arbitrary epochs. test_mkt_outside_rth.py restores both.
    import execution.session_gate as _session_gate
    import practice.order_rules as _order_rules

    monkeypatch.setattr(_session_gate, "regular_hours_now", lambda: True)
    monkeypatch.setattr(_order_rules, "mkt_outside_rth", lambda *a, **k: False)
    # The Sim live edge (ADR 020 amendment) is a fact of the wall clock: on a
    # weekday between 04:00 and 20:00 ET every "nothing loaded" Sim test would
    # otherwise become a live desk. Pinned off; test_sim_live_edge.py restores it.
    import sim.session_clock as _session_clock

    monkeypatch.setattr(_session_clock, "live_edge", lambda: False)
    # Bot session / fire tests assume spend+Gateway are allowed unless they opt out.
    monkeypatch.setattr(_trading_allowed, "places_allowed", lambda: (True, ""))
    # ADR 018 adds a runtime arm latch that is off on every process start. The
    # suite predates it and assumes a desk that can place, so arm by default for
    # the same reason places_allowed is pinned above. Tests that are *about* the
    # latch disarm explicitly (see test_desk_venue_arming.py).
    import ibkr.safety as _safety

    monkeypatch.setattr(_safety, "_armed", True)
    # The latch carries the venue it was armed on (ADR 018 amendment); this
    # default arm holds on whichever venue a test pins. A test that arms or
    # disarms through ``set_armed`` / ``arm`` gets the real venue binding.
    monkeypatch.setattr(_safety, "_armed_venue", _EveryVenue("any"))
    monkeypatch.setattr(
        _nasdaq_halt_feed,
        "_default_fetch",
        lambda: (_ for _ in ()).throw(
            RuntimeError("Nasdaq Trade Halt RSS blocked in pytest"),
        ),
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
