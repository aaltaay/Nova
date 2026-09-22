"""A refused practice order is stamped with its venue, not the Gateway label (QA R38, 2026-09-22).

Every refusal on Sim and Paper -- ``SIM_NO_PRICE``, ``OVERSELL``,
``PRACTICE_NO_LIVE_PRINT`` -- was recorded and returned with ``mode:
"disconnected"`` (``live`` on a connected desk) while filled practice receipts
carried the venue, so any reader grouping executions by ``mode`` misfiled them.
"""
from __future__ import annotations

import pytest

from execution import desk_mode as desk_mode_mod
from execution import service
from execution.models import ExecutionCommand, StageTimings


def _cmd() -> ExecutionCommand:
    return ExecutionCommand(
        operation="place", idempotency_key="r38-1", source="manual",
        symbol="GRML", side="SELL", qty=1.0, order_type="MKT",
    )


@pytest.fixture
def captured(monkeypatch):
    writes: list[dict] = []
    monkeypatch.setattr(service.store, "update_stages", lambda _id, **kw: writes.append(kw))
    monkeypatch.setattr(desk_mode_mod._client, "account_mode", lambda: "disconnected")
    return writes


@pytest.mark.parametrize("venue", ["sim", "paper"])
def test_a_practice_refusal_carries_the_venue(monkeypatch, captured, venue) -> None:
    import sim.mode as mode

    monkeypatch.setattr(mode, "is_practice_venue", lambda: True)
    monkeypatch.setattr(mode, "venue", lambda: venue)
    receipt = service._reject("e-1", _cmd(), StageTimings(received_ns=1), "SELL qty 1.0 exceeds 0.0 available", "OVERSELL")
    assert receipt.mode == venue
    assert captured[-1]["mode"] == venue and captured[-1]["status"] == "rejected"


def test_live_keeps_the_gateway_label(monkeypatch, captured) -> None:
    import sim.mode as mode

    monkeypatch.setattr(mode, "is_practice_venue", lambda: False)
    receipt = service._reject("e-2", _cmd(), StageTimings(received_ns=1), "no", "NO_POSITION")
    assert receipt.mode == "disconnected"
    assert captured[-1]["mode"] == "disconnected"


def test_an_unreadable_venue_falls_back_to_the_gateway_label(monkeypatch, captured) -> None:
    import sim.mode as mode

    def boom() -> bool:
        raise RuntimeError("venue file unreadable")

    monkeypatch.setattr(mode, "is_practice_venue", boom)
    assert desk_mode_mod.desk_mode() == "disconnected"
