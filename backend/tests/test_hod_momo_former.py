"""Former Momo manual watchlist + gate helpers (REQ-HOD-005/006)."""
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


def test_former_momo_priority_symbols_manual_list_only(monkeypatch):
    """REQ-HOD-006: priority admission SHALL be the manual list only — no
    alert-history input, regardless of what fired today."""
    _reset(monkeypatch)
    state = hm.get_state()
    cfg = state.configs[HOD_MOMO_FORMER_MOMO_STRATEGY_ID]
    cfg.former_momo_list = ["SPRC", "lbgj"]
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
    priority = former.former_momo_priority_symbols()
    assert priority == ["SPRC", "LBGJ"]
    assert "NOISE" not in priority


def test_former_momo_priority_symbols_empty_when_no_config():
    hm.replace_state(HodMomoState())
    hm.load_state()
    hm.get_state().configs.pop(HOD_MOMO_FORMER_MOMO_STRATEGY_ID, None)
    assert former.former_momo_priority_symbols() == []
