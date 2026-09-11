"""Parent-loss and dark-port self-exit predicates (D-005)."""
from __future__ import annotations

import api_process_guard as guard


def test_parent_lost_when_launcher_dies():
    assert guard.parent_lost(100, 100, parent_alive=False) is True
    assert guard.parent_lost(100, 1, parent_alive=True) is True
    assert guard.parent_lost(100, 100, parent_alive=True) is False
    assert guard.parent_lost(1, 1, parent_alive=False) is False


def test_dark_port_exits_only_after_grace():
    assert guard.should_exit_for_dark_port(1.0, listening=False, grace_sec=10) is False
    assert guard.should_exit_for_dark_port(10.0, listening=False, grace_sec=10) is True
    assert guard.should_exit_for_dark_port(99.0, listening=True, grace_sec=10) is False