"""Session-focus sticky L1 — alerts + evaluated names stay on active set."""
from __future__ import annotations

import time
from collections import defaultdict

import hod_momo as hm
import hod_momo_active as active
import hod_momo_session_focus as focus
from constants import HOD_MOMO_FORMER_MOMO_STRATEGY_ID
from hod_momo_models import AlertObject
from hod_momo_state import HodMomoState


def _reset(monkeypatch, tmp_path):
    hm.replace_state(HodMomoState())
    hm.load_state()
    state = hm.get_state()
    state.today_alerts = []
    state.gate_counters = defaultdict(int)
    state.startup_ts = time.monotonic() - 10_000
    focus.clear_session_focus(persist=False)
    monkeypatch.setattr(focus, "_path", lambda: tmp_path / "sticky.json")
    monkeypatch.setattr("hod_momo_persist.save_configs", lambda: None)
    active.clear_session_state()


def test_remember_session_focus_pins_and_caps(monkeypatch, tmp_path):
    _reset(monkeypatch, tmp_path)
    assert focus.remember_session_focus("TRT") is True
    assert focus.remember_session_focus("trt") is False
    assert focus.sticky_symbols()[0] == "TRT"
    for i in range(50):
        focus.remember_session_focus(f"S{i:02d}")
    # Cap equals reserved session_focus L1 slots (not a larger disk backlog).
    assert len(focus.sticky_symbols()) <= 8


def test_priority_sticky_then_alerts_then_former(monkeypatch, tmp_path):
    _reset(monkeypatch, tmp_path)
    state = hm.get_state()
    state.configs[HOD_MOMO_FORMER_MOMO_STRATEGY_ID].former_momo_list = ["FORMER1"]
    state.today_alerts = [
        AlertObject(
            id="a",
            timestamp="",
            ticker="ALERT1",
            strategy_id=11,
            strategy_name="Squeeze",
            price=1.0,
            change_pct=1.0,
            rvol=None,
            float_shares=None,
            gap_pct=None,
            volume=None,
            momentum_pct=None,
        ),
    ]
    focus.remember_session_focus("TRT")
    ranked = focus.session_focus_active_priority()
    assert ranked[0] == "TRT"
    assert ranked.index("ALERT1") < ranked.index("FORMER1")


def test_cooled_sticky_outranks_hot_soft_block_flood(monkeypatch, tmp_path):
    """Flood of on-table soft-blocks must not keep cooled TRT off the 8 slots."""
    _reset(monkeypatch, tmp_path)
    gainers = [{"symbol": f"H{i:02d}", "price": 5.0, "change_pct": 0.4} for i in range(12)]
    monkeypatch.setattr(
        focus,
        "_mover_covered_symbols",
        lambda: {g["symbol"] for g in gainers},
    )
    # Disk/MRU order puts hot names first and TRT last (pre-fix flood shape).
    focus._sticky = [g["symbol"] for g in gainers] + ["TRT"]
    focus._sticky_date = "2099-01-01"
    monkeypatch.setattr("hod_momo_session.current_date_et", lambda: "2099-01-01")
    ranked = focus.sticky_symbols()
    assert ranked[0] == "TRT"
    assert "TRT" in ranked
    assert len(ranked) <= 8
    snap = active.build_active_set(
        gainer_rows=gainers,
        priority_symbols=focus.session_focus_active_priority(),
        capacity=40,
    )
    assert "TRT" in snap.active
    assert snap.reasons.get("TRT") == "former_momo"


def test_sticky_symbol_gets_session_focus_active_slot(monkeypatch, tmp_path):
    """TRT-class: off the gainer table but sticky → reserved L1 slot."""
    _reset(monkeypatch, tmp_path)
    focus.remember_session_focus("TRT")
    gainers = [{"symbol": f"G{i:02d}", "price": 5.0, "change_pct": 0.5 - i * 0.01} for i in range(30)]
    snap = active.build_active_set(
        gainer_rows=gainers,
        priority_symbols=focus.session_focus_active_priority(),
        capacity=40,
    )
    assert "TRT" in snap.active
    assert snap.reasons.get("TRT") == "former_momo"
