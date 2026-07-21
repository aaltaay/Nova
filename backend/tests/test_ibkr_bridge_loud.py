"""Bridge failures must log type/repr and not silently wipe via []."""
from __future__ import annotations

import pytest

import ibkr_bridge as bridge
from runtime_state import ScannerRuntimeState, set_runtime_state_for_testing


@pytest.fixture
def state():
    current = ScannerRuntimeState()
    previous = set_runtime_state_for_testing(current)
    yield current
    set_runtime_state_for_testing(previous)


def test_run_ibkr_on_error_none_records_typed_error(monkeypatch, state):
    def boom(*_a, **_k):
        raise TimeoutError()

    monkeypatch.setattr(bridge._ibkr_client, "run_coro", boom)
    assert bridge.run_ibkr(object(), on_error="none", label="gappers") is None
    assert "TimeoutError" in state.ibkr_bridge_last_error
    assert state.ibkr_bridge_last_error.startswith("gappers:")


def test_run_ibkr_on_error_raise(monkeypatch, state):
    def boom(*_a, **_k):
        raise TimeoutError()

    monkeypatch.setattr(bridge._ibkr_client, "run_coro", boom)
    with pytest.raises(bridge.IbkrBridgeError):
        bridge.run_ibkr(object(), on_error="raise", label="losers")


def test_run_ibkr_default_is_none_not_empty_list(monkeypatch, state):
    """Default must not disguise transport failure as a successful empty scan."""

    def boom(*_a, **_k):
        raise TimeoutError()

    monkeypatch.setattr(bridge._ibkr_client, "run_coro", boom)
    assert bridge.run_ibkr(object(), label="default") is None
