"""Unit tests for Nova OS decide() — mock candidates, no network, no orders."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from constants import (
    NOVA_OS_DECISION_BUY,
    NOVA_OS_DECISION_NO_BUY,
    NOVA_OS_DECISION_WAIT,
    NOVA_OS_MODE_AUTO_PAPER,
    NOVA_OS_MODE_CONFIRM,
    NOVA_OS_MODE_SIGNAL,
)
from nova_os.decide import decide, first_minute_volume
from nova_os.gates import GateResult, session_allows_trading
from strategy.risk import RiskState


def _candidate(**overrides) -> dict:
    base = {
        "symbol": "MOCK",
        "price": 5.50,
        "change_pct": 0.18,
        "rel_volume": 7.0,
        "has_news": True,
        "float": 6_000_000,
    }
    base.update(overrides)
    return base


def _eligible_setup_payload() -> dict:
    return {
        "symbol": "MOCK",
        "eligible_setups": ["gap_and_go"],
        "any_eligible": True,
        "gap_and_go": {
            "symbol": "MOCK",
            "eligible": True,
            "would_execute": False,
            "entry_price": 5.50,
            "stop_price": 5.30,
            "target_price": 5.90,
            "triggered": True,
            "in_time_window": True,
        },
        "bull_flag": {"eligible": False},
        "abcd": {"eligible": False},
    }


def _strong_catalyst_gate() -> GateResult:
    return GateResult(
        "catalyst",
        True,
        False,
        ["CATALYST_STRONG"],
        {"news_impact": {"impact_class": "moved_price", "confidence": 0.8}},
    )


def _weak_catalyst_gate() -> GateResult:
    return GateResult(
        "catalyst",
        False,
        False,
        ["CATALYST_WEAK"],
        {"news_impact": {"impact_class": "no_effect", "confidence": 0.4}},
    )


class TestFirstMinuteVolume:
    def test_reads_930_et_bar(self):
        bars = [
            {"t": "2026-07-10T13:29:00Z", "v": 10},
            {"t": "2026-07-10T13:30:00Z", "v": 150_000},
            {"t": "2026-07-10T13:31:00Z", "v": 20},
        ]
        assert first_minute_volume(bars) == 150_000

    def test_missing_bar_returns_none(self):
        assert first_minute_volume([{"t": "2026-07-10T13:31:00Z", "v": 50}]) is None


class TestSessionAllowsTrading:
    def test_weekday_rth_open(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        et = ZoneInfo("America/New_York")
        assert session_allows_trading(datetime(2026, 7, 10, 10, 0, tzinfo=et)) is True

    def test_weekend_closed(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        et = ZoneInfo("America/New_York")
        assert session_allows_trading(datetime(2026, 7, 11, 10, 0, tzinfo=et)) is False


class TestDecideGates:
    def test_pillars_fail_is_no_buy(self):
        with (
            patch("nova_os.gates.session_allows_trading", return_value=True),
            patch("nova_os.decide.risk_mod.get_state", return_value=RiskState()),
        ):
            d = decide(_candidate(price=1.0), bars=[], watchlist_rank=1, record=False)
        assert d.decision == NOVA_OS_DECISION_NO_BUY
        assert "PILLAR_PRICE_FAIL" in d.reason_codes
        assert d.would_execute is False
        assert d.receipt["executed"] is False

    def test_risk_halt_is_no_buy_and_halted_action(self):
        state = RiskState()
        state.halted = True
        state.halt_reason = "Daily max loss reached"
        with (
            patch("nova_os.gates.session_allows_trading", return_value=True),
            patch("nova_os.decide.risk_mod.get_state", return_value=state),
        ):
            d = decide(_candidate(), bars=[], watchlist_rank=1, record=False)
        assert d.decision == NOVA_OS_DECISION_NO_BUY
        assert "RISK_HALTED" in d.reason_codes
        assert d.receipt["action"] == "halted"

    def test_watchlist_rank_too_low(self):
        with (
            patch("nova_os.gates.session_allows_trading", return_value=True),
            patch("nova_os.decide.risk_mod.get_state", return_value=RiskState()),
            patch("nova_os.gates.evaluate_setups", return_value=_eligible_setup_payload()),
            patch("nova_os.gates.first_minute_volume", return_value=200_000),
        ):
            d = decide(_candidate(), bars=[{"t": "x"}], watchlist_rank=9, record=False)
        assert d.decision == NOVA_OS_DECISION_NO_BUY
        assert "WATCHLIST_RANK_TOO_LOW" in d.reason_codes

    def test_first_minute_volume_low(self):
        with (
            patch("nova_os.gates.session_allows_trading", return_value=True),
            patch("nova_os.decide.risk_mod.get_state", return_value=RiskState()),
            patch("nova_os.gates.evaluate_setups", return_value=_eligible_setup_payload()),
            patch("nova_os.gates.first_minute_volume", return_value=1_000),
        ):
            d = decide(_candidate(), bars=[{"t": "x"}], watchlist_rank=1, record=False)
        assert d.decision == NOVA_OS_DECISION_NO_BUY
        assert "FIRST_MINUTE_VOLUME_LOW" in d.reason_codes

    def test_buy_when_all_hard_and_catalyst_pass(self):
        with (
            patch("nova_os.gates.session_allows_trading", return_value=True),
            patch("nova_os.decide.risk_mod.get_state", return_value=RiskState()),
            patch("nova_os.gates.evaluate_setups", return_value=_eligible_setup_payload()),
            patch("nova_os.gates.first_minute_volume", return_value=200_000),
            patch("nova_os.decide.gate_catalyst", return_value=_strong_catalyst_gate()),
        ):
            d = decide(_candidate(), bars=[{"t": "x"}], watchlist_rank=1, record=False)
        assert d.decision == NOVA_OS_DECISION_BUY
        assert "ALL_GATES_PASS" in d.reason_codes
        assert "CATALYST_STRONG" in d.reason_codes
        assert d.ticket is not None
        assert d.ticket["shares"] > 0
        assert d.would_execute is False  # default requested mode is `signal` — display only
        assert d.receipt["action"] == "displayed"

    def test_would_execute_true_for_buy_at_confirm_mode(self):
        """would_execute answers "would something happen downstream", not
        "did decide() execute" (it never does) — a BUY at confirm WOULD stage
        a ticket if routed through executor.on_signal()."""
        with (
            patch("nova_os.gates.session_allows_trading", return_value=True),
            patch("nova_os.decide.risk_mod.get_state", return_value=RiskState()),
            patch("nova_os.gates.evaluate_setups", return_value=_eligible_setup_payload()),
            patch("nova_os.gates.first_minute_volume", return_value=200_000),
            patch("nova_os.decide.gate_catalyst", return_value=_strong_catalyst_gate()),
        ):
            d = decide(
                _candidate(), bars=[{"t": "x"}], watchlist_rank=1,
                mode=NOVA_OS_MODE_CONFIRM, record=False,
            )
        assert d.decision == NOVA_OS_DECISION_BUY
        assert d.would_execute is True

    def test_would_execute_true_for_buy_at_auto_paper_mode(self):
        with (
            patch("nova_os.gates.session_allows_trading", return_value=True),
            patch("nova_os.decide.risk_mod.get_state", return_value=RiskState()),
            patch("nova_os.gates.evaluate_setups", return_value=_eligible_setup_payload()),
            patch("nova_os.gates.first_minute_volume", return_value=200_000),
            patch("nova_os.decide.gate_catalyst", return_value=_strong_catalyst_gate()),
        ):
            d = decide(
                _candidate(), bars=[{"t": "x"}], watchlist_rank=1,
                mode=NOVA_OS_MODE_AUTO_PAPER, record=False,
            )
        assert d.decision == NOVA_OS_DECISION_BUY
        assert d.would_execute is True

    def test_wait_when_catalyst_weak(self):
        with (
            patch("nova_os.gates.session_allows_trading", return_value=True),
            patch("nova_os.decide.risk_mod.get_state", return_value=RiskState()),
            patch("nova_os.gates.evaluate_setups", return_value=_eligible_setup_payload()),
            patch("nova_os.gates.first_minute_volume", return_value=200_000),
            patch("nova_os.decide.gate_catalyst", return_value=_weak_catalyst_gate()),
        ):
            d = decide(_candidate(), bars=[{"t": "x"}], watchlist_rank=2, record=False)
        assert d.decision == NOVA_OS_DECISION_WAIT
        assert "CATALYST_WEAK" in d.reason_codes
        assert d.ticket is not None
        assert d.would_execute is False

    def test_loss_policy_downgrades_mode_on_receipt(self):
        state = RiskState()
        state.losses_today = 1
        with (
            patch("nova_os.gates.session_allows_trading", return_value=True),
            patch("nova_os.decide.risk_mod.get_state", return_value=state),
            patch("nova_os.gates.evaluate_setups", return_value=_eligible_setup_payload()),
            patch("nova_os.gates.first_minute_volume", return_value=200_000),
            patch("nova_os.decide.gate_catalyst", return_value=_strong_catalyst_gate()),
        ):
            d = decide(
                _candidate(),
                bars=[{"t": "x"}],
                watchlist_rank=1,
                mode=NOVA_OS_MODE_AUTO_PAPER,
                record=False,
            )
        assert d.decision == NOVA_OS_DECISION_BUY
        assert d.mode == NOVA_OS_MODE_CONFIRM
        assert d.requested_mode == NOVA_OS_MODE_AUTO_PAPER
        assert "LOSS_POLICY_DOWNGRADE" in d.reason_codes
        # would_execute answers "would something happen downstream at the
        # EFFECTIVE mode" — confirm still stages a ticket, so True even
        # though the loss policy capped auto_paper down to confirm.
        assert d.would_execute is True

    def test_records_receipt_when_record_true(self):
        fake_receipt = {
            "id": 42,
            "policy_version": "test",
            "kind": "decision",
            "symbol": "MOCK",
            "decision": "NO_BUY",
            "action": "declined",
            "mode": "signal",
            "reason_codes": ["PILLAR_PRICE_FAIL"],
            "would_execute": False,
            "executed": False,
            "payload": {},
        }
        with (
            patch("nova_os.gates.session_allows_trading", return_value=True),
            patch("nova_os.decide.risk_mod.get_state", return_value=RiskState()),
            patch("nova_os.decide.record_receipt", return_value=fake_receipt) as rec,
        ):
            d = decide(_candidate(price=1.0), bars=[], watchlist_rank=1, record=True)
        assert rec.called
        assert d.receipt["id"] == 42
        assert d.would_execute is False

    def test_unknown_mode_raises(self):
        try:
            decide(_candidate(), mode="yolo", record=False)
            assert False, "expected ValueError"
        except ValueError as exc:
            assert "unknown Nova OS mode" in str(exc)

    def test_to_dict_shape(self):
        with (
            patch("nova_os.gates.session_allows_trading", return_value=True),
            patch("nova_os.decide.risk_mod.get_state", return_value=RiskState()),
        ):
            d = decide(_candidate(price=1.0), record=False)
        payload = d.to_dict()
        assert payload["decision"] == NOVA_OS_DECISION_NO_BUY
        assert payload["would_execute"] is False
        assert payload["executed"] is False
        assert isinstance(payload["gates"], list)
        assert payload["mode"] == NOVA_OS_MODE_SIGNAL
