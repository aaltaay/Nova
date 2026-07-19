"""Regression: lifespan spawn must not abort before scanner_l1."""
from __future__ import annotations

from pathlib import Path

import strategy.executor as executor


def test_executor_fill_poll_loop_name() -> None:
    """app_lifespan must call fill_poll_loop (singular) — the old typo
    fills_poll_loop raised AttributeError mid-spawn and skipped scanner_l1,
    so HOD never got L1 and Squeeze stayed surge:None.
    """
    assert hasattr(executor, "fill_poll_loop")
    assert not hasattr(executor, "fills_poll_loop")
    src = Path(__file__).resolve().parents[1] / "app_lifespan.py"
    text = src.read_text(encoding="utf-8")
    assert "_executor.fill_poll_loop" in text
    assert "_executor.fills_poll_loop" not in text
