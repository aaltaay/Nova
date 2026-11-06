"""pytest keeps the priority it started with, through the whole run (#1244, #1079).

#1244: a test that booted the app in-process started the trading-path keeper (ADR 045) on pytest's own pid, which
raised pytest to Above Normal every 2 s -- and its main thread too -- for the rest of the run. The suite now runs every
app it boots with the keeper off, and its autouse guard (``conftest._hold_pytest_priority``) fails a test that moves
pytest's priority either way, after putting it back.
"""
from __future__ import annotations

import dataclasses
import sys
import threading

import pytest

import app_lifespan
from process_priority import trading_path
from tests import priority_guard
from winapi import priority as pr

windows_only = pytest.mark.skipif(sys.platform != "win32", reason="Windows scheduling priority")
_CLASSES = [pr.IDLE, pr.BELOW_NORMAL, pr.NORMAL, pr.ABOVE_NORMAL]   # never past Above Normal in a test


def _moved(start: priority_guard.Held, move: str) -> priority_guard.Held:
    """``start`` with one step of ``move`` applied; skips when there is no room for it."""
    if move == "main thread raised":
        if start.main_thread >= 1:
            pytest.skip(f"pytest's main thread already runs at {start.text()}")
        return dataclasses.replace(start, main_thread=1)            # Above Normal, as the socket-loop raise did
    if start.cpu_class not in _CLASSES:
        pytest.skip(f"pytest runs at an unusual class ({start.text()})")
    at = _CLASSES.index(start.cpu_class) + (1 if move == "class raised" else -1)
    if not 0 <= at < len(_CLASSES):
        pytest.skip(f"no class to move to from {start.text()}")
    return dataclasses.replace(start, cpu_class=_CLASSES[at])


@windows_only
@pytest.mark.parametrize("move", ["class raised", "class lowered", "main thread raised"])
def test_a_test_that_moves_pytest_s_priority_is_named_and_put_back(move):
    start = priority_guard.read()
    assert start is not None
    moved = _moved(start, move)
    assert priority_guard.move_to(moved)
    assert priority_guard.read() == moved
    said = priority_guard.put_back(start)
    assert said is not None
    assert f"from {start.text()} to {moved.text()}" in said and "put back" in said
    assert priority_guard.read() == start


def test_a_test_that_moves_nothing_passes():
    assert priority_guard.put_back(priority_guard.read()) is None


def test_off_windows_there_is_nothing_to_read_or_hold(monkeypatch):
    monkeypatch.setattr(priority_guard, "available", lambda: False)
    assert priority_guard.read() is None
    assert priority_guard.put_back(None) is None


def test_an_app_a_test_boots_leaves_pytest_s_priority_alone():
    """The keeper is off for the suite (``NOVA_PROCESS_PRIORITY=0`` in conftest): the bootstrap's priority step
    starts no keeper thread and raises neither pytest nor the thread that booted the app."""
    start = priority_guard.read()
    app_lifespan._trading_path_priority()
    assert trading_path.enabled() is False
    assert trading_path.view()["running"] is False
    assert not any(t.name == "nova-priority" for t in threading.enumerate())
    assert priority_guard.read() == start
