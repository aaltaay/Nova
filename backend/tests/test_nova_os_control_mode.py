"""Unit tests for Nova OS P4 control_mode — in-memory, restart → signal."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import nova_os.events_db as events_db
from constants import (
    NOVA_OS_DEFAULT_MODE,
    NOVA_OS_LOSS_POLICY_DOWNGRADE_AFTER_LOSSES,
    NOVA_OS_MODE_AUTO_LIVE,
    NOVA_OS_MODE_AUTO_PAPER,
    NOVA_OS_MODE_CONFIRM,
    NOVA_OS_MODE_SIGNAL,
)
from nova_os import control_mode
from strategy import risk as risk_mod


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(events_db, "cache_dir", lambda: tmp_path)
    events_db.init_db()
    control_mode.reset_for_tests()
    risk_mod.get_state().consecutive_losses = 0
    risk_mod.get_state().losses_today = 0
    yield
    control_mode.reset_for_tests()
    risk_mod.get_state().consecutive_losses = 0
    risk_mod.get_state().losses_today = 0


class TestControlMode:
    def test_default_is_signal_on_import(self):
        assert control_mode.get_mode() == NOVA_OS_DEFAULT_MODE
        assert control_mode.get_mode() == NOVA_OS_MODE_SIGNAL

    def test_set_mode_confirm_ok(self):
        assert control_mode.set_mode(NOVA_OS_MODE_CONFIRM) == NOVA_OS_MODE_CONFIRM
        assert control_mode.get_mode() == NOVA_OS_MODE_CONFIRM

    def test_set_mode_auto_live_raises(self):
        with pytest.raises(ValueError, match="auto_live is not enabled"):
            control_mode.set_mode(NOVA_OS_MODE_AUTO_LIVE)
        assert control_mode.get_mode() == NOVA_OS_MODE_SIGNAL

    def test_set_mode_auto_paper_requires_gates(self, monkeypatch):
        monkeypatch.setattr("nova_os.control_mode._ibkr_client.is_connected", lambda: False)
        with pytest.raises(ValueError, match="IBKR connected"):
            control_mode.set_mode(NOVA_OS_MODE_AUTO_PAPER)
        assert control_mode.get_mode() == NOVA_OS_MODE_SIGNAL

    def test_force_signal(self):
        control_mode.set_mode(NOVA_OS_MODE_CONFIRM)
        control_mode.force_signal("kill")
        assert control_mode.get_mode() == NOVA_OS_MODE_SIGNAL

    def test_loss_policy_caps_effective_mode(self):
        # Simulate requested auto_paper via direct assign (P5 path); loss policy caps.
        control_mode._mode = NOVA_OS_MODE_AUTO_PAPER
        risk_mod.get_state().losses_today = NOVA_OS_LOSS_POLICY_DOWNGRADE_AFTER_LOSSES
        assert control_mode.get_effective_mode() == NOVA_OS_MODE_CONFIRM
        effective, reason = control_mode.get_effective_mode_detail()
        assert effective == NOVA_OS_MODE_CONFIRM
        assert reason == "LOSS_POLICY_DOWNGRADE"
