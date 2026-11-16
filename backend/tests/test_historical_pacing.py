"""IBKR historical pacing budget (ADR 012)."""
from __future__ import annotations

from constants import (
    IBKR_HISTORICAL_IDENTICAL_COOLDOWN_SEC,
    IBKR_HISTORICAL_PACE_MAX,
    IBKR_HISTORICAL_PACE_WINDOW_SEC,
    IBKR_HISTORICAL_SAME_CONTRACT_MAX,
    IBKR_HISTORICAL_SAME_CONTRACT_WINDOW_SEC,
    IBKR_HISTORICAL_SLOW_COUNT,
    IBKR_HISTORICAL_SLOW_OF,
    IBKR_HISTORICAL_SLOW_SEC,
    IBKR_HISTORICAL_SMALL_PACE_MAX,
)
from ibkr.historical_pacing import HistoricalPacing


class _Clock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


def _spent(key: str, count: int) -> tuple[HistoricalPacing, _Clock]:
    clock = _Clock()
    pace = HistoricalPacing(now_fn=clock)
    for i in range(count):
        pace.record(f"S{i}", key, "1 D")
        clock.advance(0.01)
    return pace, clock


def test_allows_the_whole_window_then_blocks_until_it_rolls():
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


def test_one_minute_bars_go_on_past_the_published_sixty():
    """IBKR's 60 is for bars of 30 seconds or less: 438 of them in 10 minutes answered at once (2026-11-04)."""
    pace, _clock = _spent("1Min", IBKR_HISTORICAL_SMALL_PACE_MAX + 1)
    assert pace.wait_seconds("AAPL", "1Min", "1 D") == 0.0
    assert pace.left("1Min") == IBKR_HISTORICAL_PACE_MAX - IBKR_HISTORICAL_SMALL_PACE_MAX - 1


def test_ten_second_bars_and_tick_reads_stop_at_the_published_sixty():
    pace, _clock = _spent("10Sec", IBKR_HISTORICAL_SMALL_PACE_MAX)
    assert pace.wait_seconds("AAPL", "10Sec", "1 D") > 0
    assert pace.wait_seconds("AAPL", "ticks:TRADES", "1 D") > 0
    assert pace.left("ticks:TRADES") == 0
    assert pace.wait_seconds("AAPL", "1Min", "1 D") == 0.0      # the bigger bars still have the rest of the window
    assert pace.left("1Min") == IBKR_HISTORICAL_PACE_MAX - IBKR_HISTORICAL_SMALL_PACE_MAX


def test_one_minute_bars_leave_the_sixty_alone():
    pace, _clock = _spent("1Min", IBKR_HISTORICAL_SMALL_PACE_MAX)
    assert pace.wait_seconds("AAPL", "10Sec", "1 D") == 0.0
    assert pace.left("10Sec") == IBKR_HISTORICAL_SMALL_PACE_MAX
    assert pace.snapshot()["small_used"] == 0


def test_a_hold_stops_everyone_but_an_open_chart_for_ten_minutes():
    pace, clock = _spent("1Min", IBKR_HISTORICAL_SMALL_PACE_MAX + 5)
    pace.hold()
    snap = pace.snapshot()
    assert snap["window_max"] == IBKR_HISTORICAL_SMALL_PACE_MAX and snap["held_sec"] == IBKR_HISTORICAL_PACE_WINDOW_SEC
    assert pace.left("1Min") == -5                              # every reserve is spent, so only an open chart sends
    assert pace.wait_seconds("AAPL", "1Min", "1 D") == 0.0      # and a hold is not a wait: an open chart still goes
    clock.advance(IBKR_HISTORICAL_PACE_WINDOW_SEC)
    assert pace.snapshot()["window_max"] == IBKR_HISTORICAL_PACE_MAX and pace.snapshot()["held_sec"] == 0


def test_only_ibkrs_word_counts_as_a_refusal():
    pace, _clock = _spent("1Min", 0)
    pace.hold()
    assert pace.refusals() == 0
    pace.hold(refused=True)
    assert pace.refusals() == 1


def test_slow_answers_show_ibkr_slowing_when_they_come_together():
    pace, _clock = _spent("1Min", 0)
    for _ in range(IBKR_HISTORICAL_SLOW_COUNT - 1):
        assert not pace.note_answer(IBKR_HISTORICAL_SLOW_SEC)
    assert pace.note_answer(IBKR_HISTORICAL_SLOW_SEC)
    pace.hold()                                                 # a hold starts the count again
    assert not pace.note_answer(IBKR_HISTORICAL_SLOW_SEC)


def test_slow_answers_spread_out_are_just_slow_answers():
    pace, _clock = _spent("1Min", 0)
    for _ in range(IBKR_HISTORICAL_SLOW_OF * 3):
        assert not pace.note_answer(IBKR_HISTORICAL_SLOW_SEC)
        for _ in range(IBKR_HISTORICAL_SLOW_OF - 1):
            assert not pace.note_answer(0.2)
