"""Fill latency detective -- fake clocks only. No live IBKR."""
from __future__ import annotations

import json
import logging

import pytest

from execution.fill_audit import (
    classify_fill_audit,
    emit_fill_audit,
    reset_fill_audit_store_for_testing,
)


@pytest.fixture(autouse=True)
def _clean_fill_audit_store():
    reset_fill_audit_store_for_testing()
    yield
    reset_fill_audit_store_for_testing()


def _base(**kw) -> dict:
    row = dict(
        order_id=115728,
        symbol="SPCX",
        side="BUY",
        order_type="MKT",
        mode="paper",
        status="Filled",
        nova_placed_at="2026-09-16T14:05:00.000Z",
        submitted_at="2026-09-16T14:05:00.012Z",
        filled_at="2026-09-16T14:05:00.180Z",
        terminal_at="2026-09-16T14:05:00.180Z",
        has_fill=True,
        rth=True,
        status_history=("PendingSubmit", "PreSubmitted", "Filled"),
    )
    row.update(kw)
    return row


def test_quiet_ok_mkt_fill_under_2s():
    row = classify_fill_audit(**_base())
    assert row["place_to_submit_ms"] == 12
    assert row["place_to_fill_ms"] == 180
    assert "place_to_terminal_ms" not in row
    assert row["level"] == "ok"
    assert row["status"] == "Filled"
    assert row["schema_version"] == 1


def test_mkt_rth_warn_over_2s():
    row = classify_fill_audit(
        **_base(filled_at="2026-09-16T14:05:02.100Z", terminal_at="2026-09-16T14:05:02.100Z"),
    )
    assert row["place_to_fill_ms"] == 2100
    assert row["level"] == "warn"


def test_mkt_rth_danger_over_10s():
    row = classify_fill_audit(
        **_base(filled_at="2026-09-16T14:05:11.000Z", terminal_at="2026-09-16T14:05:11.000Z"),
    )
    assert row["place_to_fill_ms"] == 11000
    assert row["level"] == "danger"


def test_working_without_fill_is_danger():
    row = classify_fill_audit(
        **_base(
            status="Submitted",
            has_fill=False,
            filled_at=None,
            terminal_at="2026-09-16T14:05:03.000Z",
            status_history=("PendingSubmit", "Submitted"),
        ),
    )
    assert row["level"] == "danger"
    assert row["reason"] == "working_without_fill"
    assert row["place_to_terminal_ms"] == 3000
    assert "place_to_fill_ms" not in row


def test_return_to_working_is_danger():
    row = classify_fill_audit(
        **_base(
            status="Submitted",
            has_fill=False,
            filled_at=None,
            terminal_at="2026-09-16T14:05:04.000Z",
            status_history=("PendingSubmit", "Filled", "Submitted"),
        ),
    )
    assert row["level"] == "danger"
    assert row["reason"] == "return_to_working"


def test_lmt_working_is_not_mkt_danger():
    row = classify_fill_audit(
        **_base(
            order_type="LMT",
            status="Submitted",
            has_fill=False,
            filled_at=None,
            terminal_at="2026-09-16T14:05:20.000Z",
            status_history=("PendingSubmit", "Submitted"),
        ),
    )
    assert row["reason"] != "working_without_fill"
    assert row["level"] == "ok"


def test_emit_writes_jsonl_and_stays_quiet_on_ok(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr("execution.fill_audit.log_dir", lambda: tmp_path)
    row = classify_fill_audit(**_base())
    with caplog.at_level(logging.INFO, logger="execution.fill_audit"):
        emit_fill_audit(row)
    path = tmp_path / "fill-latency.jsonl"
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["order_id"] == 115728
    assert parsed["place_to_fill_ms"] == 180
    assert "IBKR_FILL_AUDIT" not in caplog.text


def test_emit_danger_is_loud(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr("execution.fill_audit.log_dir", lambda: tmp_path)
    row = classify_fill_audit(
        **_base(
            status="Submitted",
            has_fill=False,
            filled_at=None,
            terminal_at="2026-09-16T14:05:03.000Z",
            status_history=("PendingSubmit", "Submitted"),
        ),
    )
    with caplog.at_level(logging.ERROR, logger="execution.fill_audit"):
        emit_fill_audit(row)
    assert "IBKR_FILL_AUDIT" in caplog.text
    assert "working_without_fill" in json.loads(
        (tmp_path / "fill-latency.jsonl").read_text(encoding="utf-8").splitlines()[0],
    )["reason"]
