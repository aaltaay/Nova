"""Former Momo remember / gate helpers."""
from __future__ import annotations

import time
from collections import defaultdict

import hod_momo as hm
import hod_momo_former as former
from constants import HOD_MOMO_FORMER_MOMO_STRATEGY_ID
from hod_momo_models import AlertObject, StrategyConfig
from hod_momo_state import HodMomoState


def _reset(monkeypatch) -> None:
    hm.replace_state(HodMomoState())
    hm.load_state()
    state = hm.get_state()
    state.today_alerts = []
    state.gate_counters = defaultdict(int)
    state.startup_ts = time.monotonic() - 10_000
    monkeypatch.setattr("hod_momo_persist.save_configs", lambda: None)
    try:
        import hod_momo_session_focus as focus

        focus.clear_session_focus(persist=False)
    except Exception:
        pass


def test_former_momo_block_empty_list():
    cfg = StrategyConfig(
        strategy_id=1, name="Former Momo Stock", color="#fff", former_momo_list=[]
    )
    assert former.former_momo_block_reason(1, "BIYA", cfg) == "former_momo_list_empty"


def test_former_momo_block_not_on_list():
    cfg = StrategyConfig(
        strategy_id=1, name="Former Momo Stock", color="#fff", former_momo_list=["LBGJ"]
    )
    assert former.former_momo_block_reason(1, "BIYA", cfg) == "not_in_former_momo_list"
    assert former.former_momo_block_reason(1, "LBGJ", cfg) is None


def test_remember_former_momo_adds_once(monkeypatch):
    _reset(monkeypatch)
    state = hm.get_state()
    cfg = state.configs[HOD_MOMO_FORMER_MOMO_STRATEGY_ID]
    cfg.former_momo_list = []
    assert former.remember_former_momo("biya") is True
    assert former.remember_former_momo("BIYA") is False
    assert "BIYA" in cfg.former_momo_list


def test_bootstrap_from_alerts(monkeypatch):
    _reset(monkeypatch)
    state = hm.get_state()
    cfg = state.configs[HOD_MOMO_FORMER_MOMO_STRATEGY_ID]
    cfg.former_momo_list = []
    state.today_alerts = [
        AlertObject(
            id="1",
            timestamp="",
            ticker="BIYA",
            strategy_id=5,
            strategy_name="Low Float Volatility Hunter",
            price=5.0,
            change_pct=10.0,
            rvol=None,
            float_shares=None,
            gap_pct=None,
            volume=None,
            momentum_pct=None,
        ),
        AlertObject(
            id="2",
            timestamp="",
            ticker="BIYA",
            strategy_id=1,
            strategy_name="Former Momo Stock",
            price=5.0,
            change_pct=10.0,
            rvol=None,
            float_shares=None,
            gap_pct=None,
            volume=None,
            momentum_pct=None,
        ),
    ]
    monkeypatch.setattr("hod_momo_persist.save_configs", lambda: None)
    assert former.bootstrap_former_momo_from_alerts() == 1
    assert "BIYA" in cfg.former_momo_list


def test_session_focus_active_priority_alerts_before_former(monkeypatch):
    """Alerts win reserved L1; Former list is last (strategy off by default)."""
    _reset(monkeypatch)
    state = hm.get_state()
    cfg = state.configs[HOD_MOMO_FORMER_MOMO_STRATEGY_ID]
    cfg.former_momo_list = ["LBGJ", "BIYA"]
    state.today_alerts = [
        AlertObject(
            id="n",
            timestamp="",
            ticker="NOISE",
            strategy_id=7,
            strategy_name="Low Float - High Rel Vol",
            price=1.0,
            change_pct=1.0,
            rvol=None,
            float_shares=None,
            gap_pct=None,
            volume=None,
            momentum_pct=None,
        ),
    ]
    ranked = former.session_focus_active_priority()
    assert ranked[0] == "NOISE"
    assert ranked.index("NOISE") < ranked.index("LBGJ")
