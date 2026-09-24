"""The pre-registered read-out that unlocks Strategy (Bot-Trading-Plan §2g, ADR 027)."""
from __future__ import annotations

import pytest

from setup_scanner import readout
from setup_scanner.readout import evaluate

_T0 = 1_790_000_000.0


def _row(i: int, tape: str, bar_r: float | None, *, kind: str = "first_pullback", triggered: bool = True,
         risk: float = 0.20) -> dict:
    return {"setup_id": f"S{i}", "kind": kind, "risk": risk, "bar_r": bar_r, "bar_exit_reason": "target",
            "triggered_at": _T0 + i * 60 if triggered else None, "trigger_tape": {"verdict": tape}}


def _go(n: int, r: float, start: int = 0) -> list[dict]:
    return [_row(start + i, "go", r) for i in range(n)]


def test_collects_until_fifty_go_setups_triggered():
    out = evaluate(_go(49, 1.0) + [_row(900, "blind", -0.5)])
    assert out["state"] == "collecting"
    assert out["passed"] is False
    assert out["go"]["triggered"] == 49
    assert "49 of 50" in out["reason"]


def test_passes_above_the_line_and_above_blind_wait():
    # net R = bar_r - 2 fills * 1c / 20c risk = bar_r - 0.10
    rows = _go(50, 0.45) + [_row(100 + i, "blind", -0.2) for i in range(10)] + [_row(200, "wait", 0.1)]
    out = evaluate(rows)
    assert out["state"] == "passed" and out["passed"] is True
    assert out["go"]["avg_net_r"] == pytest.approx(0.35)
    # blind and wait pooled over their rows, never an average of two averages
    assert out["control"]["triggered"] == 11
    assert out["control"]["avg_net_r"] == pytest.approx((10 * -0.3 + 0.0) / 11, abs=1e-3)


def test_below_the_line_is_not_passed_until_the_hundredth_go_setup():
    rows = _go(60, 0.25) + [_row(500, "blind", -0.5)]  # +0.15R net: under +0.2
    assert evaluate(rows)["state"] == "not_passed"
    rows = _go(100, 0.25) + [_row(500, "blind", -0.5)]
    assert evaluate(rows)["state"] == "failed"


def test_beating_the_line_but_not_blind_wait_is_not_a_pass():
    rows = _go(50, 0.45) + [_row(100, "wait", 0.9)]
    assert evaluate(rows)["state"] == "not_passed"


def test_no_scored_control_yet_keeps_collecting():
    out = evaluate(_go(50, 0.45))
    assert out["state"] == "collecting"
    assert "blind / wait" in out["reason"]


def test_judged_on_the_first_hundred_go_setups_only():
    """Pre-registered: waiting past 100 never turns a fail into a pass."""
    rows = _go(100, 0.2) + _go(200, 2.0, start=100) + [_row(10, "blind", -0.5)]
    out = evaluate(rows)
    assert out["go"]["triggered"] == 100
    assert out["state"] == "failed"


def test_only_triggered_first_pullbacks_count():
    rows = (_go(50, 0.45) + [_row(300 + i, "go", 5.0, kind="second_pullback") for i in range(20)]
            + [_row(400 + i, "go", 5.0, triggered=False) for i in range(20)] + [_row(10, "blind", -0.5)])
    out = evaluate(rows)
    assert out["go"]["triggered"] == 50
    assert out["go"]["avg_net_r"] == pytest.approx(0.35)


def test_current_is_unavailable_while_the_store_is_closed(monkeypatch):
    class Eng:
        store = None
        store_error = "setups.db refused: unknown schema"

    monkeypatch.setattr("setup_scanner.engine.get_engine", lambda: Eng())
    readout.reset_for_tests()
    out = readout.current(now=_T0)
    assert out["state"] == "unavailable" and out["passed"] is False
    assert "unknown schema" in out["reason"]


def test_current_reads_every_day_and_caches(monkeypatch):
    calls = []

    class Store:
        def rows(self, **kw):
            calls.append(kw)
            return _go(3, 1.0)

    class Eng:
        store = Store()
        store_error = None

    monkeypatch.setattr("setup_scanner.engine.get_engine", lambda: Eng())
    readout.reset_for_tests()
    assert readout.current(now=_T0)["go"]["triggered"] == 3
    readout.current(now=_T0 + 5)
    # every day of the template in play's rows (ADR 029), read once inside the cache window
    assert calls == [{"template_id": "default", "template_rev": 1}]
    readout.current(now=_T0 + 60)
    assert len(calls) == 2
