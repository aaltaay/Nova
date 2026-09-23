"""Regression: lifespan spawn must not abort before scanner_l1."""
from __future__ import annotations

from pathlib import Path


def test_runtime_task_targets_exist() -> None:
    """A spawn entry naming a missing attribute (the old ``fills_poll_loop``
    typo) raised AttributeError mid-list and skipped scanner_l1, so HOD never
    got L1. The Phase D executor's fill loop is gone (ADR 025); the loops that
    remain must still resolve.
    """
    src = Path(__file__).resolve().parents[1] / "app_runtime_tasks.py"
    text = src.read_text(encoding="utf-8")
    assert "_executor." not in text
    assert "nasdaq_halt_rss" in text
    assert "bot.ttl" in text
    assert "bot.breakers" in text
    assert hasattr(
        __import__("ibkr.nasdaq_halt_feed", fromlist=["poll_loop"]),
        "poll_loop",
    )
    bot_loops = __import__("bot.loops", fromlist=["ttl_loop", "breaker_loop"])
    assert hasattr(bot_loops, "ttl_loop")
    assert hasattr(bot_loops, "breaker_loop")
