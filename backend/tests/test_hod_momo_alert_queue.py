"""A burst's first HOD Momo alert is due at once; its repeats fold at the burst's end (2026-10-13, PFAI)."""
from __future__ import annotations

from types import SimpleNamespace

from hod_momo_alert_queue import queue_alert, take_due


def _state(window: float = 10.0) -> SimpleNamespace:
    return SimpleNamespace(
        master=SimpleNamespace(consolidation_sec=window),
        consolidation_bursts={},
        pending_consolidation={},
    )


def _alert(strategy_id: int, created: float) -> SimpleNamespace:
    return SimpleNamespace(
        id=f"{int(created * 1000)}-PFAI-{strategy_id}", strategy_id=strategy_id, created_ts=created,
        consolidation_count=1, consolidated_ids=[], consolidation_span_sec=None,
    )


def test_first_trigger_is_due_now_and_repeats_wait_for_the_burst_end():
    state = _state()
    assert queue_alert(state, "PFAI", _alert(11, 100.0), 100.0) == 100.0
    assert queue_alert(state, "PFAI", _alert(11, 103.0), 103.0) == 110.0
    assert queue_alert(state, "PFAI", _alert(11, 109.9), 109.9) == 110.0
    # The burst is over: the next trigger starts another and goes out at once.
    assert queue_alert(state, "PFAI", _alert(11, 110.0), 110.0) == 110.0


def test_one_evaluation_goes_out_together_and_equal_clocks_are_not_one_evaluation():
    state = _state()
    due = queue_alert(state, "PFAI", _alert(10, 100.0), 100.0)
    assert queue_alert(state, "PFAI", _alert(11, 100.0), 100.0, due) == 100.0
    # A replay's clock is the print's second: the next print in that second is a repeat.
    assert queue_alert(state, "PFAI", _alert(11, 100.0), 100.0) == 110.0


def test_take_due_sends_the_first_alone_and_folds_the_repeats_per_strategy():
    state = _state()
    due = queue_alert(state, "PFAI", _alert(10, 100.0), 100.0)
    queue_alert(state, "PFAI", _alert(11, 100.0), 100.0, due)
    for t in (101.0, 104.0, 105.0):
        queue_alert(state, "PFAI", _alert(11, t), t)

    first = take_due(state, 100.0)
    assert sorted(a.strategy_id for a in first) == [10, 11]
    assert all(a.consolidation_count == 1 for a in first)
    assert take_due(state, 109.0) == []

    folded = take_due(state, 110.0)
    assert len(folded) == 1
    row = folded[0]
    assert (row.strategy_id, row.consolidation_count, row.consolidation_span_sec) == (11, 3, 4)
    assert row.consolidated_ids == ["101000-PFAI-11", "104000-PFAI-11"]
    assert state.pending_consolidation["PFAI"] == []


def test_no_window_sends_every_trigger_at_once():
    state = _state(window=0.0)
    assert queue_alert(state, "PFAI", _alert(11, 100.0), 100.0) == 100.0
    assert queue_alert(state, "PFAI", _alert(11, 100.5), 100.5) == 100.5
