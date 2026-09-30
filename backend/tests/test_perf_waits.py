"""The Busiest handlers row lists waits apart from work (2026-09-30)."""
from __future__ import annotations


def test_waits_are_listed_apart_from_work_in_the_busiest_row():
    from diagnostics import collect_perf
    from metrics import op_metrics

    op_metrics.reset_for_tests()
    op_metrics.record("work.op", 1_000_000)
    op_metrics.record_since("wait.op", 0, wall=True)
    assert op_metrics.is_wall("wait.op") and not op_metrics.is_wall("work.op")
    from tests.test_perf_sample import _sample

    one = _sample(1.0, ops={"work.op": {"calls": 1, "busy_ms": 5.0}, "wait.op": {"calls": 1, "busy_ms": 900.0}})
    got = collect_perf._handlers_row([one], 60)
    assert [r["op"] for r in got["evidence"]["top"]] == ["work.op"]
    assert [r["op"] for r in got["evidence"]["waits"]] == ["wait.op"]
    assert "wait.op" not in got["detail"]
    op_metrics.reset_for_tests()
