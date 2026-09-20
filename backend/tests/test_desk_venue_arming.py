"""ADR 018 -- the desk venue persists across a restart, spend arming never does.

The regression this file exists for (#302): the localhost watchdog restarted the
API six times on 2026-09-19 and each restart silently returned a desk practising
in Sim to an armed live IBKR door. The property under test is not "Sim is
remembered" but the stronger one: *no* process start lands armed, whichever
venue it resolves.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from constants_sim import (
    DESK_VENUE_FILE,
    DESK_VENUE_SCHEMA_VERSION,
    NOVA_BROKER_ENV,
    NOVA_BROKER_SIM,
)
from execution.models import ExecutionCommand
from execution.validate import validate_command
from ibkr import safety as _safety
from sim import mode as _mode
from sim.mode import is_sim_mode, reset_for_tests, set_sim_mode


def setup_function() -> None:
    reset_for_tests()


def teardown_function() -> None:
    reset_for_tests()


def _simulate_process_restart() -> None:
    """Drop in-process state the way a fresh interpreter would -- keeping disk.

    ``reset_for_tests`` deliberately unlinks the venue file, which is the one
    thing a restart does *not* do, so these tests clear the module globals
    directly instead.
    """
    _mode._override = None
    _mode._venue_loaded = False
    _mode.os.environ.pop(NOVA_BROKER_ENV, None)
    _safety.set_armed(False, reason="simulated process start")


def _write_venue_file(payload: dict) -> None:
    path = Path(DESK_VENUE_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


# ── Decision 1: the settled venue survives a restart ──────────────────────────

def test_sim_venue_survives_a_process_restart() -> None:
    set_sim_mode(True)
    _simulate_process_restart()
    assert is_sim_mode() is True


def test_ibkr_venue_survives_a_process_restart() -> None:
    set_sim_mode(False)
    _simulate_process_restart()
    assert is_sim_mode() is False


# ── Decision 2: no process start is ever armed ────────────────────────────────

def test_restart_from_sim_never_lands_armed() -> None:
    """The #302 regression, stated as its property."""
    set_sim_mode(True)
    _safety.set_armed(True, reason="operator armed before the bounce")
    assert _safety.armed() is True

    _simulate_process_restart()

    assert is_sim_mode() is True, "the venue must come back"
    assert _safety.armed() is False, "the arming must not"


def test_restart_with_no_venue_file_lands_on_ibkr_but_disarmed() -> None:
    """Losing the cache costs the venue, never the spend gate."""
    set_sim_mode(True)
    _safety.set_armed(True, reason="operator")
    Path(DESK_VENUE_FILE).unlink(missing_ok=True)

    _simulate_process_restart()

    assert is_sim_mode() is False, "no file -> env bootstrap default"
    assert _safety.armed() is False, "and still not armed"


def test_restart_with_unknown_schema_version_refuses_and_stays_disarmed(caplog) -> None:
    set_sim_mode(True)
    _write_venue_file(
        {"schema_version": DESK_VENUE_SCHEMA_VERSION + 99, "venue": NOVA_BROKER_SIM}
    )

    _simulate_process_restart()
    with caplog.at_level("WARNING"):
        resolved = is_sim_mode()

    assert resolved is False, "an unknown version must not pick a venue"
    assert _safety.armed() is False
    assert any("schema_version" in r.message for r in caplog.records), (
        "an unknown version must refuse loud, not silently"
    )
    # The operator's file is left alone so a downgrade can still read it.
    assert Path(DESK_VENUE_FILE).exists()


def test_restart_with_unreadable_venue_file_stays_disarmed() -> None:
    _write_venue_file({"schema_version": DESK_VENUE_SCHEMA_VERSION, "venue": "nonsense"})
    _simulate_process_restart()
    assert is_sim_mode() is False
    assert _safety.armed() is False


# ── Arming is an explicit act, and a venue change revokes it ──────────────────

def test_changing_venue_disarms() -> None:
    set_sim_mode(True)
    _safety.set_armed(True, reason="operator")
    set_sim_mode(False)
    assert _safety.armed() is False, (
        "carrying an arm across a venue change hands the operator a different "
        "desk already armed"
    )


def test_arming_is_not_persisted_to_the_venue_file() -> None:
    set_sim_mode(True)
    _safety.set_armed(True, reason="operator")
    stored = json.loads(Path(DESK_VENUE_FILE).read_text(encoding="utf-8"))
    assert "armed" not in stored
    assert stored == {
        "schema_version": DESK_VENUE_SCHEMA_VERSION,
        "venue": NOVA_BROKER_SIM,
    }


# ── Decision 4: protective paths are never gated ──────────────────────────────

def _place(source: str) -> ExecutionCommand:
    return ExecutionCommand(
        operation="place",
        idempotency_key=f"adr018-{source}",
        source=source,
        symbol="SIM1",
        side="SELL",
        qty=1,
        order_type="MKT",
    )


@pytest.mark.parametrize("source", ["flatten", "kill", "cancel_working"])
def test_protective_sources_place_while_disarmed(source: str) -> None:
    set_sim_mode(True)
    assert _safety.armed() is False
    ok, detail, reason = validate_command(_place(source))
    assert ok is True, f"{source} must survive a disarm: {detail}"
    assert reason is None


@pytest.mark.parametrize("source", ["manual", "bot", "auto_paper", "approve"])
def test_opening_sources_are_refused_while_disarmed(source: str) -> None:
    set_sim_mode(True)
    ok, _detail, reason = validate_command(_place(source))
    assert ok is False
    assert reason == "DISARMED"


def test_opening_source_passes_once_armed() -> None:
    set_sim_mode(True)
    _safety.set_armed(True, reason="operator")
    ok, detail, reason = validate_command(_place("manual"))
    assert ok is True, detail
    assert reason is None


# ── Decision 5: venue and arm are separate fields on the wire ────────────────

def test_status_snapshot_names_permitted_and_armed_separately(monkeypatch) -> None:
    monkeypatch.setenv("IBKR_ORDERS_ENABLED", "true")
    monkeypatch.setenv("IBKR_GATEWAY_MODE", "live")
    monkeypatch.setenv("IBKR_LIVE_TRADING_CONFIRMED", "true")

    snap = _safety.status_snapshot("live")

    assert snap["spend_permitted"] is True, "the env still permits spending"
    assert snap["armed"] is False, "but this process is not armed"
    assert snap["spend_status"] == "locked_disarmed", (
        "the effective status must read locked so no surface can imply armed"
    )
    _safety.set_armed(True, reason="test")
    assert _safety.status_snapshot("live")["spend_status"] == "live_armed"
