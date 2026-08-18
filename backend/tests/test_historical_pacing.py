"""IBKR historical pacing budget (ADR 012)."""
from __future__ import annotations

from constants import (
    IBKR_HISTORICAL_IDENTICAL_COOLDOWN_SEC,
    IBKR_HISTORICAL_PACE_MAX,
    IBKR_HISTORICAL_PACE_WINDOW_SEC,
    IBKR_HISTORICAL_SAME_CONTRACT_MAX,
    IBKR_HISTORICAL_SAME_CONTRACT_WINDOW_SEC,
)
from ibkr.historical_pacing import HistoricalPacing


class _Clock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


def test_allows_sixty_then_blocks_until_window_rolls():
    clock = _Clock()
    pace = HistoricalPacing(now_fn=clock)
    for i in range(IBKR_HISTORICAL_PACE_MAX):
        sym = f"S{i}"
        assert pace.wait_seconds(sym, "1Min", "1 D") == 0.0
        pace.record(sym, "1Min", "1 D")
        clock.advance(0.01)
    wait = pace.wait_seconds("BBB", "1Min", "1 D")
    assert wait > 0
    clock.advance(IBKR_HISTORICAL_PACE_WINDOW_SEC)
    assert pace.wait_seconds("BBB", "1Min", "1 D") == 0.0


def test_same_contract_caps_at_five_inside_two_seconds():
    clock = _Clock()
    pace = HistoricalPacing(now_fn=clock)
    for i in range(IBKR_HISTORICAL_SAME_CONTRACT_MAX):
        assert pace.wait_seconds("AIXC", f"tf{i}", "1 D") == 0.0
        pace.record("AIXC", f"tf{i}", "1 D")
        clock.advance(0.01)
    wait = pace.wait_seconds("AIXC", "other", "1 D")
    assert wait > 0
    assert wait <= IBKR_HISTORICAL_SAME_CONTRACT_WINDOW_SEC
    clock.advance(IBKR_HISTORICAL_SAME_CONTRACT_WINDOW_SEC)
    assert pace.wait_seconds("AIXC", "other", "1 D") == 0.0


def test_identical_request_waits_fifteen_seconds():
    clock = _Clock()
    pace = HistoricalPacing(now_fn=clock)
    pace.record("AAPL", "1Min", "1 D")
    wait = pace.wait_seconds("AAPL", "1Min", "1 D")
    assert wait > 0
    assert wait <= IBKR_HISTORICAL_IDENTICAL_COOLDOWN_SEC
    clock.advance(IBKR_HISTORICAL_IDENTICAL_COOLDOWN_SEC)
    assert pace.wait_seconds("AAPL", "1Min", "1 D") == 0.0
