"""Gateway Read-Only API (Error 321) is named, not guessed at (D-076).

With Configure > Settings > API > Read-Only API ticked, the session reaches
READY and looks tradeable, positions keep refreshing, and every order comes
back rejected. Before this the only hint was the amber completed-orders
warning (PROBLEM_LOG 2026-07-22).
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ibkr import session_errors as se

READ_ONLY_MSG = (
    "Error validating request.-'bW' : cause - The API interface is currently "
    "in Read-Only mode."
)


@pytest.fixture(autouse=True)
def _clean():
    se.reset_for_tests()
    yield
    se.reset_for_tests()


def test_read_only_rejection_is_classified():
    assert se.is_read_only_rejection(321, READ_ONLY_MSG) is True
    assert se.is_read_only_rejection(321, "Read-Only API is enabled") is True


def test_other_error_321_is_not_read_only():
    """321 is IB's generic validation error -- the message has to name it, or a
    malformed order would block the desk with the wrong reason."""
    assert se.is_read_only_rejection(321, "Error validating request: bad qty") is False
    assert se.is_read_only_rejection(321, "") is False
    assert se.is_read_only_rejection(201, READ_ONLY_MSG) is False


def test_error_hook_stamps_read_only_and_leaves_the_session_alone():
    ib = MagicMock()
    se.install_error_hook(ib)
    assert se.gateway_read_only() is False

    se._on_ib_error(7, 321, READ_ONLY_MSG)

    assert se.gateway_read_only() is True
    assert se.gateway_read_only_since() > 0
    # Read-only is not a connectivity fault: nothing may be marked unusable.
    assert se.unusable_since() is None
    assert se.last_connectivity_code() is None


def test_read_only_stamp_keeps_the_first_rejection():
    se.install_error_hook(MagicMock())
    se._on_ib_error(7, 321, READ_ONLY_MSG)
    first = se.gateway_read_only_since()
    se._on_ib_error(8, 321, READ_ONLY_MSG)
    assert se.gateway_read_only_since() == first


def test_a_new_connection_clears_the_read_only_verdict():
    """Untick the setting, reconnect, and the row must go away by itself."""
    first_ib = MagicMock()
    se.install_error_hook(first_ib)
    se._on_ib_error(7, 321, READ_ONLY_MSG)
    assert se.gateway_read_only() is True

    se.install_error_hook(MagicMock())  # fresh IB() == fresh API session
    assert se.gateway_read_only() is False


def test_generic_321_does_not_set_the_flag():
    se.install_error_hook(MagicMock())
    se._on_ib_error(7, 321, "Error validating request: order size too small")
    assert se.gateway_read_only() is False


def test_read_only_flag_survives_unrelated_errors():
    se.install_error_hook(MagicMock())
    se._on_ib_error(7, 321, READ_ONLY_MSG)
    se._on_ib_error(9, 2104, "Market data farm connection is OK")
    assert se.gateway_read_only() is True
