"""IBKR session readiness state machine — generation only ever increases."""
from __future__ import annotations

import pytest

from ibkr import session_state as session


@pytest.fixture(autouse=True)
def _isolate():
    session.reset_for_testing()
    yield
    session.reset_for_testing()


def test_starts_disconnected_generation_zero():
    assert session.state() == session.DISCONNECTED
    assert session.generation() == 0
    assert session.is_ready() is False


def test_full_transition_sequence_reaches_ready():
    session.set_connecting()
    assert session.state() == session.CONNECTING
    assert session.is_ready() is False

    session.set_synchronizing()
    assert session.state() == session.SYNCHRONIZING
    assert session.is_ready() is False

    gen = session.set_ready()
    assert session.state() == session.READY
    assert session.is_ready() is True
    assert gen == 1
    assert session.generation() == 1


def test_generation_increments_across_reconnects_never_resets():
    session.set_connecting()
    session.set_synchronizing()
    first = session.set_ready()

    session.set_degraded()
    assert session.is_ready() is False
    assert session.generation() == first  # degrade does not roll back generation

    session.set_connecting()
    session.set_synchronizing()
    second = session.set_ready()

    assert second == first + 1
    assert session.generation() == second


def test_disconnected_does_not_reset_generation():
    session.set_connecting()
    session.set_synchronizing()
    session.set_ready()
    session.set_disconnected()
    assert session.state() == session.DISCONNECTED
    assert session.generation() == 1  # only reset_for_testing() zeroes this
